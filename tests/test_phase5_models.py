"""Structural persistence tests for Phase 5 experiments and gate decisions."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Experiment,
    ExperimentKind,
    ExperimentStatus,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    SelectionCandidate,
    Team,
)
from backend.services.experiments import (
    ExperimentIdentity,
    complete_walk_forward_experiment,
    start_walk_forward_experiment,
)
from qwantej.calibration import calibration_report
from qwantej.performance import BacktestFold, WalkForwardConfig, WalkForwardReport


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _experiment(now: datetime) -> Experiment:
    return Experiment(
        name="phase5-synthetic", version="v1",
        kind=ExperimentKind.WALK_FORWARD_BACKTEST,
        status=ExperimentStatus.RUNNING, model_version="model-v1",
        calibration_version="platt-v1", value_policy_version="value-gate-v1",
        conservative_policy_version="pcons-v1", code_commit="abc123",
        data_snapshot_ref="snapshot:test", baseline="devig-market",
        random_seed=7, configuration={"minimum_training_size": 30}, started_at=now,
        training_window_start=now - timedelta(days=90),
        training_window_end=now - timedelta(days=31),
        test_window_start=now - timedelta(days=30), test_window_end=now,
    )


def test_experiment_round_trips_configuration_and_metrics(session: Session) -> None:
    now = datetime.now(UTC)
    experiment = _experiment(now)
    experiment.status = ExperimentStatus.SUCCEEDED
    experiment.finished_at = now
    experiment.sample_size = 100
    experiment.metrics = {"brier": 0.2, "roi": -0.03}
    experiment.result_hash = "sha256:result"
    session.add(experiment)
    session.commit()
    session.expire_all()
    stored = session.query(Experiment).one()
    assert stored.status is ExperimentStatus.SUCCEEDED
    assert stored.configuration["minimum_training_size"] == 30
    assert stored.metrics["roi"] == -0.03


def test_experiment_rejects_reversed_windows(session: Session) -> None:
    experiment = _experiment(datetime.now(UTC))
    experiment.training_window_start = experiment.training_window_end + timedelta(days=1)
    session.add(experiment)
    with pytest.raises(IntegrityError):
        session.commit()


def test_experiment_service_archives_json_metrics_and_hash(session: Session) -> None:
    now = datetime.now(UTC)
    config = WalkForwardConfig(
        version="walk-v1", model_version="model-v1", minimum_training_size=2,
    )
    identity = ExperimentIdentity(
        name="archived-run", version="v1", calibration_version="platt-v1",
        code_commit="abc123", data_snapshot_ref="snapshot:test",
        training_window_start=now - timedelta(days=30),
        training_window_end=now - timedelta(days=2),
        test_window_start=now - timedelta(days=1), test_window_end=now,
    )
    experiment = start_walk_forward_experiment(
        session, identity=identity, config=config, started_at=now
    )
    metrics = calibration_report([0.4, 0.6], [0, 1])
    report = WalkForwardReport(
        config=config.as_dict(), sample_size=2, selected_count=1,
        start=now - timedelta(days=1), end=now,
        folds=(BacktestFold(now, 2, now, now, 2, 1),),
        leakage_rows_rejected=0, model_version_rows_rejected=0,
        unsettled_or_void_rows=0,
        missing_market_rows=0, missing_closing_odds_rows=0,
        raw_calibration=metrics, calibrated_calibration=metrics,
        market_calibration=metrics, roi=0.1,
        roi_confidence_interval=(-0.1, 0.2), hit_rate=0.5,
        average_odds=2.0, break_even_hit_rate=0.5, average_clv=0.01,
        maximum_drawdown_units=1.0,
    )
    complete_walk_forward_experiment(session, experiment, report, finished_at=now)
    assert experiment.status is ExperimentStatus.SUCCEEDED
    assert experiment.metrics["folds"][0]["training_sample_size"] == 2
    assert experiment.result_hash is not None
    assert experiment.result_hash.startswith("sha256:")


def test_selection_candidate_links_to_archived_prediction(session: Session) -> None:
    now = datetime.now(UTC)
    competition = Competition(name="Test League")
    season = Season(competition=competition, label="2025/26")
    home, away = Team(name="Home"), Team(name="Away")
    fixture = Fixture(
        competition=competition, season=season, home_team=home, away_team=away,
        kickoff_utc=now + timedelta(days=1), status=FixtureStatus.SCHEDULED,
    )
    prediction = Prediction(
        fixture=fixture, prediction_timestamp=now, decision_as_of=now,
        market="1X2", selection="home", conservative_probability=0.62,
    )
    candidate = SelectionCandidate(
        prediction=prediction, evaluated_at=now, policy_version="value-gate-v1",
        passed=False, edge=0.02, expected_value=-0.01,
        reason_codes=["EDGE_TOO_LOW", "EV_NON_POSITIVE"],
        gate_inputs={"dqs": 90},
    )
    session.add_all([competition, season, home, away, fixture, prediction, candidate])
    session.commit()
    stored = session.query(SelectionCandidate).one()
    assert stored.prediction.selection == "home"
    assert stored.reason_codes == ["EDGE_TOO_LOW", "EV_NON_POSITIVE"]
