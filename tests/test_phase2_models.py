"""Structural tests for the Phase 2 tables (model_registry, model_runs,
predictions, audit_events). Runs against in-memory SQLite — checks
constraints/relationships/enum round-tripping, not Postgres-specific
behaviour, which the Alembic migration exercises against a real Postgres.
See the same note in test_models.py.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    AuditActor,
    AuditEvent,
    AuditEventType,
    Base,
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
    Season,
    Team,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


@pytest.fixture()
def fixture(session: Session) -> Fixture:
    comp = Competition(name="Premier League", country="England", tier=1)
    season = Season(competition=comp, label="2025/2026")
    home = Team(name="Arsenal")
    away = Team(name="Chelsea")
    fx = Fixture(
        competition=comp, season=season, home_team=home, away_team=away,
        kickoff_utc=datetime.now(UTC), status=FixtureStatus.SCHEDULED,
    )
    session.add_all([comp, season, home, away, fx])
    session.flush()
    return fx


@pytest.fixture()
def model(session: Session) -> ModelRegistry:
    m = ModelRegistry(
        family=ModelFamily.POISSON, name="poisson-baseline", version="1.0.0",
        status=ModelStatus.CHAMPION, code_commit="abc123",
    )
    session.add(m)
    session.flush()
    return m


class TestModelRegistry:
    def test_round_trips_enums_as_lowercase_values(
        self, session: Session, model: ModelRegistry
    ) -> None:
        session.commit()
        session.expire_all()
        reloaded = session.get(ModelRegistry, model.id)
        assert reloaded is not None
        assert reloaded.family is ModelFamily.POISSON
        assert reloaded.status is ModelStatus.CHAMPION

    def test_rejects_duplicate_name_version(self, session: Session, model: ModelRegistry) -> None:
        session.add(
            ModelRegistry(
                family=ModelFamily.ENSEMBLE, name="poisson-baseline", version="1.0.0",
                status=ModelStatus.DEVELOPMENT,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    def test_same_name_different_version_is_allowed(
        self, session: Session, model: ModelRegistry
    ) -> None:
        session.add(
            ModelRegistry(
                family=ModelFamily.POISSON, name="poisson-baseline", version="1.1.0",
                status=ModelStatus.CHALLENGER,
            )
        )
        session.commit()
        assert session.query(ModelRegistry).count() == 2


class TestModelRun:
    def test_links_run_to_model(self, session: Session, model: ModelRegistry) -> None:
        run = ModelRun(
            model=model, kind=ModelRunKind.BACKTEST, status=ModelRunStatus.SUCCEEDED,
            started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
            metrics={"brier": 0.21, "log_loss": 0.62},
        )
        session.add(run)
        session.commit()
        session.expire_all()
        reloaded = session.query(ModelRun).one()
        assert reloaded.kind is ModelRunKind.BACKTEST
        assert reloaded.model.name == "poisson-baseline"
        assert reloaded.metrics["brier"] == 0.21

    def test_defaults_to_running(self, session: Session, model: ModelRegistry) -> None:
        run = ModelRun(model=model, kind=ModelRunKind.TRAINING, started_at=datetime.now(UTC))
        session.add(run)
        session.commit()
        assert run.status is ModelRunStatus.RUNNING


class TestPrediction:
    def _base_kwargs(self, fixture: Fixture) -> dict:
        now = datetime.now(UTC)
        return dict(
            fixture=fixture, prediction_timestamp=now, decision_as_of=now,
            market="1X2", selection="X2",
        )

    def test_stores_immutable_decision_record(
        self, session: Session, fixture: Fixture, model: ModelRegistry
    ) -> None:
        run = ModelRun(
            model=model, kind=ModelRunKind.INFERENCE, status=ModelRunStatus.SUCCEEDED,
            started_at=datetime.now(UTC),
        )
        session.add(run)
        session.flush()
        pred = Prediction(
            **self._base_kwargs(fixture),
            model_probabilities={"poisson": 0.55, "dixon_coles": 0.53},
            ensemble_probability=0.54, calibrated_probability=0.52,
            conservative_probability=0.50, expected_value=-0.03,
            model_version=model, model_run=run,
            input_snapshot_ref="snapshots/run/input.json",
            input_snapshot_hash="sha256:abc",
            feature_version="fs-1", calibration_version="cal-1",
        )
        session.add(pred)
        session.commit()
        session.expire_all()
        reloaded = session.query(Prediction).one()
        assert reloaded.conservative_probability == 0.50
        assert reloaded.model_probabilities["poisson"] == 0.55
        assert reloaded.model_version.name == "poisson-baseline"
        # Execution/input lineage links the prediction to the exact run + inputs.
        assert reloaded.model_run.kind is ModelRunKind.INFERENCE
        assert reloaded.input_snapshot_ref == "snapshots/run/input.json"
        assert reloaded.input_snapshot_hash == "sha256:abc"
        # Immutable table carries no updated_at.
        assert not hasattr(reloaded, "updated_at")

    @pytest.mark.parametrize(
        "column,value",
        [
            ("ensemble_probability", 1.5),
            ("calibrated_probability", -0.1),
            ("conservative_probability", 2.0),
            ("fair_market_probability", 1.01),
        ],
    )
    def test_rejects_probability_outside_unit_interval(
        self, session: Session, fixture: Fixture, column: str, value: float
    ) -> None:
        pred = Prediction(**self._base_kwargs(fixture), **{column: value})
        session.add(pred)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_allows_null_probabilities(self, session: Session, fixture: Fixture) -> None:
        # A no-price / early prediction may legitimately leave layers unset.
        pred = Prediction(**self._base_kwargs(fixture))
        session.add(pred)
        session.commit()
        assert session.query(Prediction).count() == 1


class TestAuditEvent:
    def test_records_a_material_action(self, session: Session, model: ModelRegistry) -> None:
        event = AuditEvent(
            event_type=AuditEventType.MODEL_PROMOTED, actor=AuditActor.HUMAN,
            actor_ref="cmhango", action="promote_model",
            summary="Promote poisson-baseline 1.0.0 to champion",
            entity_type="model_registry", entity_id=model.id,
            payload={"from": "challenger", "to": "champion"},
            occurred_at=datetime.now(UTC),
        )
        session.add(event)
        session.commit()
        session.expire_all()
        reloaded = session.query(AuditEvent).one()
        assert reloaded.event_type is AuditEventType.MODEL_PROMOTED
        assert reloaded.actor is AuditActor.HUMAN
        assert reloaded.entity_id == model.id
        assert not hasattr(reloaded, "updated_at")
