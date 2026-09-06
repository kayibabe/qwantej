"""Fail-closed prediction publication: complete record + frozen lineage or nothing."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    CalibrationMethod,
    CalibrationModel,
    CalibrationStatus,
    Competition,
    Fixture,
    FixtureStatus,
    ModelFamily,
    ModelRegistry,
    ModelRun,
    ModelRunKind,
    ModelRunStatus,
    ModelStatus,
    Prediction,
    ReliabilitySnapshot,
    ReliabilityState,
    Season,
    StatsSnapshot,
    StatsSubjectType,
    Team,
)
from backend.services.features import create_feature_snapshot
from backend.services.predictions import (
    MinimumPredictionRecord,
    PredictionLineage,
    PredictionPublicationError,
    publish_prediction,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _seed(session: Session):
    comp = Competition(name="EPL")
    season = Season(competition=comp, label="2026/27")
    home, away = Team(name="Home"), Team(name="Away")
    fixture = Fixture(
        competition=comp, season=season, home_team=home, away_team=away,
        kickoff_utc=NOW + timedelta(days=1), status=FixtureStatus.SCHEDULED,
    )
    model = ModelRegistry(
        family=ModelFamily.ENSEMBLE, name="ensemble-baseline", version="1.0.0",
        status=ModelStatus.CHAMPION, code_commit="abc123",
    )
    session.add_all([comp, season, home, away, fixture, model])
    session.flush()
    stats = StatsSnapshot(
        subject_type=StatsSubjectType.FIXTURE,
        fixture_id=fixture.id,
        as_of_timestamp=NOW,
        payload={"home_form": 0.6},
        source="test",
    )
    session.add(stats)
    session.flush()
    feature_snapshot = create_feature_snapshot(
        session,
        fixture_id=fixture.id,
        feature_version="feat-1",
        as_of_timestamp=NOW,
        features={"home_form": 0.6},
        stats_snapshot_ids=[stats.id],
        imputation_policy_version="none-v1",
        code_commit="abc123",
    )
    run = ModelRun(
        model=model, kind=ModelRunKind.INFERENCE, status=ModelRunStatus.SUCCEEDED,
        started_at=NOW, finished_at=NOW, data_as_of=NOW,
        data_snapshot_ref=feature_snapshot.snapshot_ref,
        code_commit="abc123",
        metrics={"ok": True},
    )
    calibrator = CalibrationModel(
        version="cal-1", method=CalibrationMethod.PLATT,
        status=CalibrationStatus.CHAMPION, trained_as_of=NOW,
        training_window_start=NOW - timedelta(days=30), training_window_end=NOW,
        sample_size=100, minimum_sample_size=30,
        parameters={"intercept": 0.0, "slope": 1.0},
        artefact_hash="sha256:cal", code_commit="abc123",
    )
    reliability = ReliabilitySnapshot(
        competition=comp, competition_class="tier-1", market_family="1X2",
        evaluated_as_of=NOW, window_start=NOW - timedelta(days=30), window_end=NOW,
        policy_version="reliability-v1", observation_count=100,
        effective_sample_size=80, shrinkage_weight=0.1,
        league_reliability=70, market_reliability=68, segment_reliability=69,
        posterior_standard_deviation=0.03, conservative_lower_bound=0.6,
        status=ReliabilityState.QUALIFIED, grade="B", components={}, diagnostics={},
        future_rows_excluded=0, input_snapshot_ref="snapshot:v1",
        input_snapshot_hash="sha256:inputs", code_commit="abc123",
    )
    session.add_all([run, calibrator, reliability])
    session.flush()
    return fixture, model, run, calibrator, reliability, feature_snapshot


def _valid(session: Session):
    fixture, model, run, calibrator, reliability, feature_snapshot = _seed(session)
    record = MinimumPredictionRecord(
        fixture_id=fixture.id, prediction_timestamp=NOW, decision_as_of=NOW,
        market="1X2", selection="home",
        model_probabilities={"poisson": 0.52, "elo": 0.50},
        ensemble_probability=0.51, calibrated_probability=0.53,
        conservative_probability=0.50, dqs=85.0, uncertainty_measure=0.04,
        lrs=70.0, mrs=68.0, dynamic_states={"reliability": "qualified"},
        bookmaker="bk", executable_odds=2.1, quote_timestamp=NOW - timedelta(hours=1),
        fair_market_probability=0.48, edge_pp=2.0, expected_value=0.05,
    )
    lineage = PredictionLineage(
        model_version_id=model.id, model_run_id=run.id,
        calibration_model_id=calibrator.id,
        reliability_snapshot_id=reliability.id, feature_version="feat-1",
        calibration_version="cal-1", risk_policy_version="risk-v1",
        optimiser_version="pre-optimiser-v1",
        code_commit="abc123",
        input_snapshot_ref=feature_snapshot.snapshot_ref,
        input_snapshot_hash=feature_snapshot.snapshot_hash,
    )
    return record, lineage


def test_complete_record_publishes(session: Session) -> None:
    record, lineage = _valid(session)
    prediction = publish_prediction(session, record=record, lineage=lineage)
    session.commit()
    session.expire_all()
    stored = session.query(Prediction).one()
    assert stored.id == prediction.id
    assert float(stored.conservative_probability) == pytest.approx(0.50)
    assert stored.input_snapshot_hash == lineage.input_snapshot_hash
    assert stored.model_run_id == lineage.model_run_id


def test_missing_conservative_probability_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    record = replace(record, conservative_probability=None)  # type: ignore[arg-type]
    with pytest.raises(PredictionPublicationError, match="conservative_probability"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_incomplete_price_block_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    record = replace(record, fair_market_probability=None)  # type: ignore[arg-type]
    with pytest.raises(PredictionPublicationError, match="price block"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_missing_input_hash_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    lineage = replace(lineage, input_snapshot_hash="")
    with pytest.raises(PredictionPublicationError, match="input_snapshot_hash"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_nonexistent_lineage_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    lineage = replace(lineage, model_version_id=uuid.uuid4())
    with pytest.raises(PredictionPublicationError, match="model_version_id does not exist"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_run_from_different_model_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    other = ModelRegistry(
        family=ModelFamily.POISSON, name="other", version="1.0.0",
        status=ModelStatus.DEVELOPMENT,
    )
    session.add(other)
    session.flush()
    lineage = replace(lineage, model_version_id=other.id)
    with pytest.raises(PredictionPublicationError, match="different model"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_future_quote_timestamp_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    record = replace(record, quote_timestamp=NOW + timedelta(hours=1))
    with pytest.raises(PredictionPublicationError, match="quote_timestamp"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_reliability_scores_require_snapshot(session: Session) -> None:
    record, lineage = _valid(session)
    lineage = replace(lineage, reliability_snapshot_id=None)
    with pytest.raises(PredictionPublicationError, match="reliability_snapshot_id"):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("edge_pp", 99.0, "edge_pp does not match"),
        ("expected_value", 99.0, "expected_value does not match"),
    ],
)
def test_inconsistent_value_fields_fail_closed(
    session: Session, field: str, value: float, message: str
) -> None:
    record, lineage = _valid(session)
    record = replace(record, **{field: value})
    with pytest.raises(PredictionPublicationError, match=message):
        publish_prediction(session, record=record, lineage=lineage)
    assert session.query(Prediction).count() == 0


def test_future_model_run_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    run = session.get(ModelRun, lineage.model_run_id)
    assert run is not None
    run.data_as_of = NOW + timedelta(hours=1)
    session.flush()
    with pytest.raises(PredictionPublicationError, match="model run.*decision_as_of"):
        publish_prediction(session, record=record, lineage=lineage)


def test_model_run_cutoff_must_match_feature_snapshot(session: Session) -> None:
    record, lineage = _valid(session)
    run = session.get(ModelRun, lineage.model_run_id)
    assert run is not None
    run.data_as_of = NOW - timedelta(minutes=1)
    session.flush()
    with pytest.raises(PredictionPublicationError, match="cutoff does not match"):
        publish_prediction(session, record=record, lineage=lineage)


def test_future_calibrator_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    calibrator = session.get(CalibrationModel, lineage.calibration_model_id)
    assert calibrator is not None
    calibrator.trained_as_of = NOW + timedelta(hours=1)
    calibrator.training_window_end = NOW + timedelta(hours=1)
    session.flush()
    with pytest.raises(PredictionPublicationError, match="calibrator.*decision_as_of"):
        publish_prediction(session, record=record, lineage=lineage)


def test_non_champion_model_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    model = session.get(ModelRegistry, lineage.model_version_id)
    assert model is not None
    model.status = ModelStatus.CHALLENGER
    session.flush()
    with pytest.raises(PredictionPublicationError, match="not the champion"):
        publish_prediction(session, record=record, lineage=lineage)


def test_feature_snapshot_hash_mismatch_fails_closed(session: Session) -> None:
    record, lineage = _valid(session)
    lineage = replace(lineage, input_snapshot_hash="sha256:wrong")
    with pytest.raises(PredictionPublicationError, match="does not match its snapshot"):
        publish_prediction(session, record=record, lineage=lineage)


def test_published_prediction_has_complete_version_spine(session: Session) -> None:
    record, lineage = _valid(session)
    prediction = publish_prediction(session, record=record, lineage=lineage)
    assert prediction.risk_policy_version == "risk-v1"
    assert prediction.optimiser_version == "pre-optimiser-v1"
