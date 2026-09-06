"""Postgres regression coverage for the append-only archive (finding 1).

Immutability of `predictions` and `audit_events` is enforced by database
triggers (migration da3a07d4e74e), which the SQLite structural tests cannot
exercise. These tests run against the dev Postgres container and are skipped
when it is unreachable or not migrated to head.

Everything runs inside one transaction that is rolled back at the end, so no
rows persist — and because DELETE is itself blocked, each expected-failure
operation is wrapped in a SAVEPOINT (`begin_nested`) so the raised error does
not abort the surrounding transaction.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import (
    AuditActor,
    AuditEvent,
    AuditEventType,
    CalibrationMethod,
    CalibrationModel,
    CalibrationSnapshot,
    CalibrationStatus,
    Competition,
    Experiment,
    ExperimentKind,
    ExperimentStatus,
    Fixture,
    FixtureStatus,
    ModelFamily,
    ModelRegistry,
    ModelRun,
    ModelRunKind,
    ModelStatus,
    Prediction,
    ReliabilitySnapshot,
    ReliabilityState,
    Season,
    SelectionCandidate,
    Team,
)

DATABASE_URL = get_settings().database_url


@pytest.fixture(scope="module")
def engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("append-only triggers are Postgres-only")
    eng = create_engine(DATABASE_URL)
    try:
        with eng.connect() as conn:
            present = conn.execute(
                text(
                    "select count(*) from pg_trigger "
                    "where tgname in "
                    "('trg_audit_events_no_row_mutation', "
                    "'trg_selection_candidates_no_update')"
                )
            ).scalar_one()
    except OperationalError:
        pytest.skip("dev Postgres not reachable (docker compose up -d db)")
    if present != 2:
        pytest.skip("append-only triggers absent; run: alembic upgrade head")
    return eng


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    outer = conn.begin()
    sess = Session(bind=conn)
    try:
        yield sess
    finally:
        sess.close()
        outer.rollback()
        conn.close()


def _new_audit_event(session: Session) -> AuditEvent:
    event = AuditEvent(
        event_type=AuditEventType.GOVERNANCE, actor=AuditActor.SYSTEM,
        action="test", occurred_at=datetime.now(UTC),
    )
    session.add(event)
    session.flush()
    return event


def _new_prediction(
    session: Session, *, model_version_id=None, model_run_id=None
) -> Prediction:
    comp = Competition(name="Immutable League")
    season = Season(competition=comp, label="2025/2026")
    home, away = Team(name="Home FC"), Team(name="Away FC")
    fx = Fixture(
        competition=comp, season=season, home_team=home, away_team=away,
        kickoff_utc=datetime.now(UTC), status=FixtureStatus.SCHEDULED,
    )
    now = datetime.now(UTC)
    pred = Prediction(
        fixture=fx, prediction_timestamp=now, decision_as_of=now,
        market="1X2", selection="home", conservative_probability=0.5,
        model_version_id=model_version_id, model_run_id=model_run_id,
    )
    session.add_all([comp, season, home, away, fx, pred])
    session.flush()
    return pred


def _assert_blocked(
    session: Session, sql: str, params: dict | None = None, *, message: str = "append-only"
) -> None:
    with pytest.raises(DBAPIError) as exc_info:
        with session.begin_nested():
            session.execute(text(sql), params or {})
    assert message in str(exc_info.value.orig)


class TestAuditEventsImmutable:
    def test_update_is_blocked(self, session: Session) -> None:
        event = _new_audit_event(session)
        _assert_blocked(
            session, "UPDATE audit_events SET action = 'tampered' WHERE id = :id",
            {"id": str(event.id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        event = _new_audit_event(session)
        _assert_blocked(
            session, "DELETE FROM audit_events WHERE id = :id", {"id": str(event.id)}
        )


class TestPredictionsImmutable:
    def test_update_is_blocked(self, session: Session) -> None:
        pred = _new_prediction(session)
        _assert_blocked(
            session,
            "UPDATE predictions SET conservative_probability = 0.9 WHERE id = :id",
            {"id": str(pred.id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        pred = _new_prediction(session)
        _assert_blocked(
            session, "DELETE FROM predictions WHERE id = :id", {"id": str(pred.id)}
        )


def _new_calibration_snapshot(session: Session) -> CalibrationSnapshot:
    now = datetime.now(UTC)
    calibrator = CalibrationModel(
        version=f"immutability-{now.timestamp()}", method=CalibrationMethod.PLATT,
        status=CalibrationStatus.DEVELOPMENT, trained_as_of=now,
        training_window_start=now, training_window_end=now, sample_size=30,
        minimum_sample_size=30, parameters={"intercept": 0.0, "slope": 1.0},
        artefact_hash="sha256:test", code_commit="test",
    )
    snapshot = CalibrationSnapshot(
        calibration_model=calibrator, evaluated_as_of=now, window_start=now,
        window_end=now, sample_size=30, brier_score=0.2, log_loss=0.6,
        expected_calibration_error=0.05, reliability_curve=[],
    )
    session.add(snapshot)
    session.flush()
    return snapshot


class TestCalibrationSnapshotsImmutable:
    def test_update_is_blocked(self, session: Session) -> None:
        snapshot = _new_calibration_snapshot(session)
        _assert_blocked(
            session,
            "UPDATE calibration_snapshots SET brier_score = 0.9 WHERE id = :id",
            {"id": str(snapshot.id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        snapshot = _new_calibration_snapshot(session)
        _assert_blocked(
            session, "DELETE FROM calibration_snapshots WHERE id = :id",
            {"id": str(snapshot.id)},
        )


class TestCalibrationModelArtifactImmutable:
    def test_artifact_parameters_are_frozen(self, session: Session) -> None:
        snapshot = _new_calibration_snapshot(session)
        _assert_blocked(
            session,
            "UPDATE calibration_models SET parameters = '{\"slope\": 9}' WHERE id = :id",
            {"id": str(snapshot.calibration_model_id)},
            message="artifact fields are immutable",
        )

    def test_lifecycle_status_can_change(self, session: Session) -> None:
        snapshot = _new_calibration_snapshot(session)
        session.execute(
            text("UPDATE calibration_models SET status = 'challenger' WHERE id = :id"),
            {"id": str(snapshot.calibration_model_id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        snapshot = _new_calibration_snapshot(session)
        _assert_blocked(
            session, "DELETE FROM calibration_models WHERE id = :id",
            {"id": str(snapshot.calibration_model_id)},
        )

@pytest.mark.parametrize(
    "statement",
    [
        "TRUNCATE predictions CASCADE",
        "TRUNCATE audit_events",
        "TRUNCATE calibration_models CASCADE",
        "TRUNCATE calibration_snapshots",
        "TRUNCATE experiments",
        "TRUNCATE selection_candidates",
        "TRUNCATE reliability_snapshots CASCADE",
    ],
)
def test_append_only_tables_block_truncate(session: Session, statement: str) -> None:
    _assert_blocked(session, statement)


def test_mutable_lifecycle_table_still_updatable(session: Session) -> None:
    # Control: model_registry is a mutable lifecycle entity — the triggers must
    # not touch it. A status change must succeed.
    model = ModelRegistry(
        family=ModelFamily.POISSON, name="ctrl", version="1.0.0",
        status=ModelStatus.CHALLENGER,
    )
    session.add(model)
    session.flush()
    model.status = ModelStatus.CHAMPION
    session.flush()  # must not raise
    assert model.status is ModelStatus.CHAMPION


def test_prediction_run_must_belong_to_named_model(session: Session) -> None:
    first = ModelRegistry(
        family=ModelFamily.POISSON, name="lineage-first", version="1.0.0",
        status=ModelStatus.DEVELOPMENT,
    )
    second = ModelRegistry(
        family=ModelFamily.ELO, name="lineage-second", version="1.0.0",
        status=ModelStatus.DEVELOPMENT,
    )
    run = ModelRun(
        model=second, kind=ModelRunKind.INFERENCE, started_at=datetime.now(UTC)
    )
    session.add_all([first, second, run])
    session.flush()
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            _new_prediction(
                session, model_version_id=first.id, model_run_id=run.id
            )


def _new_experiment(session: Session) -> Experiment:
    now = datetime.now(UTC)
    experiment = Experiment(
        name=f"immutability-{now.timestamp()}", version="v1",
        kind=ExperimentKind.WALK_FORWARD_BACKTEST,
        status=ExperimentStatus.RUNNING, model_version="model-v1",
        calibration_version="cal-v1", value_policy_version="gate-v1",
        conservative_policy_version="pcons-v1", code_commit="test",
        data_snapshot_ref="snapshot:test", baseline="devig-market", random_seed=7,
        configuration={"minimum_training_size": 30}, started_at=now,
        training_window_start=now, training_window_end=now,
        test_window_start=now, test_window_end=now,
    )
    session.add(experiment)
    session.flush()
    return experiment


class TestExperimentRegistryImmutable:
    def test_running_experiment_can_complete(self, session: Session) -> None:
        experiment = _new_experiment(session)
        session.execute(
            text(
                "UPDATE experiments SET status = 'succeeded', finished_at = :now, "
                "sample_size = 10, metrics = '{\"roi\": 0.1}', "
                "result_hash = 'sha256:test' WHERE id = :id"
            ),
            {"id": str(experiment.id), "now": datetime.now(UTC)},
        )

    def test_configuration_update_is_blocked(self, session: Session) -> None:
        experiment = _new_experiment(session)
        _assert_blocked(
            session, "UPDATE experiments SET random_seed = 8 WHERE id = :id",
            {"id": str(experiment.id)}, message="configuration is immutable",
        )

    def test_completed_result_update_is_blocked(self, session: Session) -> None:
        experiment = _new_experiment(session)
        session.execute(
            text(
                "UPDATE experiments SET status = 'succeeded', finished_at = :now, "
                "sample_size = 10, metrics = '{\"roi\": 0.1}', "
                "result_hash = 'sha256:test' WHERE id = :id"
            ),
            {"id": str(experiment.id), "now": datetime.now(UTC)},
        )
        _assert_blocked(
            session, "UPDATE experiments SET sample_size = 99 WHERE id = :id",
            {"id": str(experiment.id)}, message="completed experiment",
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        experiment = _new_experiment(session)
        _assert_blocked(
            session, "DELETE FROM experiments WHERE id = :id",
            {"id": str(experiment.id)},
        )


def _new_selection_candidate(session: Session) -> SelectionCandidate:
    prediction = _new_prediction(session)
    candidate = SelectionCandidate(
        prediction=prediction, evaluated_at=datetime.now(UTC),
        policy_version="gate-v1", passed=False, reason_codes=["EDGE_TOO_LOW"],
        gate_inputs={"minimum_edge": 0.03},
    )
    session.add(candidate)
    session.flush()
    return candidate


class TestSelectionCandidatesImmutable:
    def test_update_is_blocked(self, session: Session) -> None:
        candidate = _new_selection_candidate(session)
        _assert_blocked(
            session, "UPDATE selection_candidates SET passed = true WHERE id = :id",
            {"id": str(candidate.id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        candidate = _new_selection_candidate(session)
        _assert_blocked(
            session, "DELETE FROM selection_candidates WHERE id = :id",
            {"id": str(candidate.id)},
        )


def _new_reliability_snapshot(session: Session) -> ReliabilitySnapshot:
    now = datetime.now(UTC)
    competition = Competition(name=f"Reliability League {now.timestamp()}")
    snapshot = ReliabilitySnapshot(
        competition=competition, competition_class="tier-1", market_family="O2.5",
        evaluated_as_of=now, window_start=now, window_end=now,
        policy_version="reliability-v1", observation_count=10,
        effective_sample_size=9, shrinkage_weight=0.08,
        league_reliability=55, market_reliability=56, segment_reliability=54,
        posterior_standard_deviation=0.04, conservative_lower_bound=0.46,
        status=ReliabilityState.RESTRICTED, grade="Reject",
        components={"calibration": 0.7}, diagnostics={}, future_rows_excluded=0,
        input_snapshot_ref="snapshot:test", input_snapshot_hash="sha256:test",
        code_commit="test",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


class TestReliabilitySnapshotsImmutable:
    def test_update_is_blocked(self, session: Session) -> None:
        snapshot = _new_reliability_snapshot(session)
        _assert_blocked(
            session,
            "UPDATE reliability_snapshots SET segment_reliability = 99 WHERE id = :id",
            {"id": str(snapshot.id)},
        )

    def test_delete_is_blocked(self, session: Session) -> None:
        snapshot = _new_reliability_snapshot(session)
        _assert_blocked(
            session, "DELETE FROM reliability_snapshots WHERE id = :id",
            {"id": str(snapshot.id)},
        )
