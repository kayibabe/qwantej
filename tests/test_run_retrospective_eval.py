"""Tests for the run_retrospective_eval script helpers.

Exercises:
  - _run_calibration_backtest() boundary: training rows whose
    outcome_observed_at > test_from_utc must not inflate minimum_training_size.
  - _record_experiment(): data_snapshot_ref written to DB contains both hashes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Make the script importable without executing main()
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if str(_repo_root / "src") not in sys.path:
    sys.path.insert(0, str(_repo_root / "src"))

from backend.models import Base
from qwantej.performance.calibration_backtest import CalibrationObservationRow
from scripts.run_retrospective_eval import _record_experiment, _run_calibration_backtest

# ---------------------------------------------------------------------------
# SQLite session for _record_experiment tests
# ---------------------------------------------------------------------------

MODEL_VERSION = "poisson+elo-ensemble:1.0.0"
TEST_FROM = "2026-02-01"
TEST_FROM_DT = datetime(2026, 2, 1, tzinfo=UTC)
TRAIN_FROM = "2026-01-01"


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
# Helpers
# ---------------------------------------------------------------------------


def _make_train_obs(n: int, *, outcome_lag_hours: int = 3) -> list[CalibrationObservationRow]:
    """n training observations, outcomes available `outcome_lag_hours` after decision."""
    result = []
    for i in range(n):
        decision = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i)
        result.append(
            CalibrationObservationRow(
                observation_id=f"train-{i:04d}",
                decision_as_of=decision,
                feature_as_of=decision - timedelta(hours=2),
                outcome_observed_at=decision + timedelta(hours=outcome_lag_hours),
                model_version=MODEL_VERSION,
                raw_probability=0.35 + (i % 4) * 0.1,
                outcome=i % 2,
            )
        )
    return result


def _make_test_obs(n: int) -> list[CalibrationObservationRow]:
    result = []
    for i in range(n):
        decision = TEST_FROM_DT + timedelta(days=i)
        result.append(
            CalibrationObservationRow(
                observation_id=f"test-{i:04d}",
                decision_as_of=decision,
                feature_as_of=decision - timedelta(hours=2),
                outcome_observed_at=decision + timedelta(hours=3),
                model_version=MODEL_VERSION,
                raw_probability=0.4 + (i % 3) * 0.1,
                outcome=i % 2,
            )
        )
    return result


def _args(**overrides) -> argparse.Namespace:
    defaults = dict(
        train_from=TRAIN_FROM,
        train_to="2026-01-31",
        test_from=TEST_FROM,
        test_to="2026-02-28",
        league=39,
        season=2025,
        name="eval-test",
        n_recent=30,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# _run_calibration_backtest boundary test
# ---------------------------------------------------------------------------


class TestRunCalibrationBacktest:
    def test_late_outcome_training_rows_do_not_inflate_min_train(self) -> None:
        """When all 30 training rows have outcome_observed_at 48h after decision,
        the last ~2 days of training fall after test_from_utc.
        _run_calibration_backtest must count only the rows available at the
        first fold cutoff, not the full 30, so the walk-forward produces folds."""
        train = _make_train_obs(30, outcome_lag_hours=48)
        test = _make_test_obs(5)
        report, config = _run_calibration_backtest(train + test, _args())
        assert len(report.folds) >= 1
        assert report.pit_certified is False

    def test_no_train_raises(self) -> None:
        """No training observations (all rows are in test window) → ValueError."""
        test_only = _make_test_obs(5)
        with pytest.raises(ValueError, match="no training observations"):
            _run_calibration_backtest(test_only, _args())

    def test_no_test_raises(self) -> None:
        """No test observations → ValueError."""
        train_only = _make_train_obs(30)
        with pytest.raises(ValueError, match="no test observations"):
            _run_calibration_backtest(train_only, _args())

    def test_insufficient_available_training_raises(self) -> None:
        """Only 1 training row has its outcome available by test_from → ValueError."""
        train = [
            CalibrationObservationRow(
                observation_id="train-0000",
                decision_as_of=datetime(2026, 1, 31, tzinfo=UTC),
                feature_as_of=datetime(2026, 1, 31, tzinfo=UTC) - timedelta(hours=2),
                # outcome arrives well after test_from_utc (Feb 1)
                outcome_observed_at=datetime(2026, 2, 10, tzinfo=UTC),
                model_version=MODEL_VERSION,
                raw_probability=0.5,
                outcome=1,
            )
        ]
        test = _make_test_obs(3)
        with pytest.raises(ValueError, match="only"):
            _run_calibration_backtest(train + test, _args())


# ---------------------------------------------------------------------------
# _record_experiment: data_snapshot_ref contains both hashes
# ---------------------------------------------------------------------------


class TestRecordExperiment:
    def test_data_snapshot_ref_contains_both_hashes(self, session: Session) -> None:
        """data_snapshot_ref must embed both the dataset hash and the fixture
        training hash (two distinct sha256: prefixes)."""
        train = _make_train_obs(30)
        test = _make_test_obs(5)
        observations = train + test
        all_training_results: list = []  # empty for this test; hash will still be stored

        report, config = _run_calibration_backtest(observations, _args())
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        _record_experiment(
            session, report, config, observations, all_training_results, _args(), started_at
        )

        # The service commits changes; verify via ORM query
        from sqlalchemy import select

        from backend.models import Experiment

        exp = session.scalars(select(Experiment).where(Experiment.name == "eval-test")).first()
        assert exp is not None
        ref = exp.data_snapshot_ref
        # Must contain two sha256 fingerprints (dataset + training fixture hash)
        assert ref.count("sha256:") >= 2

    def test_configuration_always_has_research_flags(self, session: Session) -> None:
        train = _make_train_obs(30)
        test = _make_test_obs(5)
        observations = train + test
        report, config = _run_calibration_backtest(observations, _args(name="eval-flags"))
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        _record_experiment(
            session, report, config, observations, [], _args(name="eval-flags"), started_at
        )

        from sqlalchemy import select

        from backend.models import Experiment

        exp = session.scalars(
            select(Experiment).where(Experiment.name == "eval-flags")
        ).first()
        assert exp is not None
        assert exp.configuration["pit_certified"] is False
        assert exp.configuration["research_mode"] is True
