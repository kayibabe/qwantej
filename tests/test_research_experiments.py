"""Persistence tests for start_research_experiment / complete_research_experiment.

Verifies that the research-specific persistence path in experiments.py writes
exactly the sentinel values that distinguish a non-PIT-certified research run
from a production walk-forward:
  - value_policy_version == "not-applicable"
  - conservative_policy_version == "not-applicable"
  - baseline == "retrospective-research"
  - random_seed == 0
  - leakage_rows_rejected == 0  (NOT temporal_order_rejections)
  - result_hash starts with "sha256:"
  - configuration["pit_certified"] is False
  - configuration["research_mode"] is True
  - temporal_order_rejections preserved inside metrics JSON

Uses a seeded SQLite in-memory session to avoid any dependency on a real
Postgres instance.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import Base, ExperimentStatus
from backend.services.experiments import (
    ExperimentIdentity,
    complete_research_experiment,
    start_research_experiment,
)
from qwantej.calibration import CalibrationMethod
from qwantej.performance.calibration_backtest import (
    CalibrationObservationRow,
    CalibrationOnlyConfig,
    calibration_only_walk_forward,
)

# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

BASE = datetime(2026, 1, 1, tzinfo=UTC)
MODEL_VERSION = "poisson+elo-ensemble:1.0.0"
CONFIG_VERSION = "research-test:1.0.0"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    tx = conn.begin()
    sess = Session(bind=conn)
    try:
        yield sess
    finally:
        sess.close()
        tx.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _identity(
    name: str = "test-research-run",
    train_start: datetime | None = None,
    train_end: datetime | None = None,
    test_start: datetime | None = None,
    test_end: datetime | None = None,
) -> ExperimentIdentity:
    ts = train_start or BASE
    te = train_end or BASE + timedelta(days=90)
    ss = test_start or BASE + timedelta(days=91)
    se = test_end or BASE + timedelta(days=180)
    return ExperimentIdentity(
        name=name,
        version="1.0.0",
        calibration_version="isotonic:1.0.0",
        code_commit="abcdef1",
        data_snapshot_ref="retrospective:league=39:season=2025:sha256:aaaa:sha256:bbbb",
        training_window_start=ts,
        training_window_end=te,
        test_window_start=ss,
        test_window_end=se,
    )


def _config() -> CalibrationOnlyConfig:
    return CalibrationOnlyConfig(
        version=CONFIG_VERSION,
        model_version=MODEL_VERSION,
        calibration_method=CalibrationMethod.ISOTONIC,
        minimum_training_size=20,
        test_window_size=5,
    )


def _obs(idx: int) -> CalibrationObservationRow:
    decision = BASE + timedelta(days=idx)
    return CalibrationObservationRow(
        observation_id=f"obs-{idx:04d}",
        decision_as_of=decision,
        feature_as_of=decision - timedelta(hours=2),
        outcome_observed_at=decision + timedelta(hours=3),
        model_version=MODEL_VERSION,
        raw_probability=0.45 + (idx % 3) * 0.1,
        outcome=idx % 2,
    )


def _build_report(n: int = 60):
    observations = [_obs(i) for i in range(n)]
    cfg = _config()
    return calibration_only_walk_forward(observations, cfg), cfg


# ---------------------------------------------------------------------------
# start_research_experiment
# ---------------------------------------------------------------------------


class TestStartResearchExperiment:
    def test_sentinel_value_policy(self, session: Session) -> None:
        identity = _identity()
        experiment = start_research_experiment(
            session, identity=identity, config=_config(), started_at=BASE
        )
        assert experiment.value_policy_version == "not-applicable"

    def test_sentinel_conservative_policy(self, session: Session) -> None:
        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.conservative_policy_version == "not-applicable"

    def test_sentinel_baseline(self, session: Session) -> None:
        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.baseline == "retrospective-research"

    def test_random_seed_zero(self, session: Session) -> None:
        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.random_seed == 0

    def test_configuration_pit_certified_false(self, session: Session) -> None:
        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.configuration["pit_certified"] is False

    def test_configuration_research_mode_true(self, session: Session) -> None:
        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.configuration["research_mode"] is True

    def test_status_running(self, session: Session) -> None:
        from backend.models import ExperimentStatus

        experiment = start_research_experiment(
            session, identity=_identity(), config=_config(), started_at=BASE
        )
        assert experiment.status is ExperimentStatus.RUNNING

    def test_naive_started_at_raises(self, session: Session) -> None:
        with pytest.raises(ValueError, match="started_at"):
            start_research_experiment(
                session,
                identity=_identity(),
                config=_config(),
                started_at=datetime(2026, 1, 1),
            )


# ---------------------------------------------------------------------------
# complete_research_experiment
# ---------------------------------------------------------------------------


class TestCompleteResearchExperiment:
    def test_leakage_rows_rejected_is_always_zero(self, session: Session) -> None:
        report, cfg = _build_report(60)
        # Even if there were temporal rejections the column must stay 0
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        assert experiment.leakage_rows_rejected == 0

    def test_result_hash_starts_with_sha256(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        assert experiment.result_hash.startswith("sha256:")

    def test_result_hash_full_length(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        # "sha256:" + 64 hex chars
        assert len(experiment.result_hash) == len("sha256:") + 64

    def test_status_set_to_succeeded(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        assert experiment.status is ExperimentStatus.SUCCEEDED

    def test_temporal_order_rejections_in_metrics_json(self, session: Session) -> None:
        """temporal_order_rejections must be preserved in metrics even though
        leakage_rows_rejected is always 0."""
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        metrics = experiment.metrics
        assert "temporal_order_rejections" in metrics

    def test_sample_size_populated(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, experiment, report, finished_at=BASE + timedelta(hours=1)
        )
        assert experiment.sample_size > 0

    def test_completing_non_running_raises(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        finish = BASE + timedelta(hours=1)
        complete_research_experiment(session, experiment, report, finished_at=finish)
        with pytest.raises(ValueError, match="running"):
            complete_research_experiment(session, experiment, report, finished_at=finish)

    def test_finished_at_before_started_at_raises(self, session: Session) -> None:
        report, cfg = _build_report(60)
        experiment = start_research_experiment(
            session, identity=_identity(), config=cfg, started_at=BASE
        )
        with pytest.raises(ValueError, match="finished_at"):
            complete_research_experiment(
                session, experiment, report, finished_at=BASE - timedelta(hours=1)
            )

    def test_result_hash_deterministic(self, session: Session) -> None:
        report, cfg = _build_report(60)
        exp_a = start_research_experiment(
            session, identity=_identity("run-a"), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, exp_a, report, finished_at=BASE + timedelta(hours=1)
        )
        exp_b = start_research_experiment(
            session, identity=_identity("run-b"), config=cfg, started_at=BASE
        )
        complete_research_experiment(
            session, exp_b, report, finished_at=BASE + timedelta(hours=1)
        )
        # Same report → same hash regardless of experiment name
        assert exp_a.result_hash == exp_b.result_hash
