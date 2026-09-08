"""Tests for GET /audit (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import Base
from backend.models.audit import AuditActor, AuditEvent, AuditEventType

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
ENTITY_ID = uuid.uuid4()


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed_client():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override

    with factory() as seed:
        seed.add_all([
            AuditEvent(
                event_type=AuditEventType.MODEL_PROMOTED,
                actor=AuditActor.SYSTEM,
                action="promote_model",
                summary="poisson-baseline promoted to champion",
                entity_type="model_registry",
                entity_id=ENTITY_ID,
                occurred_at=NOW - timedelta(hours=2),
            ),
            AuditEvent(
                event_type=AuditEventType.POLICY_CHANGE,
                actor=AuditActor.HUMAN,
                actor_ref="cromwell",
                action="update_kelly_fraction",
                summary="Reduced Kelly fraction from 0.25 to 0.20",
                occurred_at=NOW - timedelta(hours=1),
            ),
            AuditEvent(
                event_type=AuditEventType.JOB_FAILURE,
                actor=AuditActor.SYSTEM,
                action="settlement_worker_error",
                summary="Settlement worker raised ValueError",
                occurred_at=NOW,
            ),
        ])
        seed.commit()

    return factory


def _client_from_factory(factory):
    def _override():
        with factory() as s:
            yield s
    app.dependency_overrides[get_db] = _override
    return TestClient(app)


class TestListAuditEvents:
    def setup_method(self):
        self._factory = _seed_client()

    def teardown_method(self):
        app.dependency_overrides.clear()

    @property
    def client(self):
        return _client_from_factory(self._factory)

    def test_returns_200(self) -> None:
        with self.client as c:
            r = c.get("/audit")
        assert r.status_code == 200

    def test_pagination_shape(self) -> None:
        with self.client as c:
            data = c.get("/audit").json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 3

    def test_ordered_most_recent_first(self) -> None:
        with self.client as c:
            items = c.get("/audit").json()["items"]
        assert items[0]["action"] == "settlement_worker_error"
        assert items[-1]["action"] == "promote_model"

    def test_filter_by_event_type(self) -> None:
        with self.client as c:
            data = c.get("/audit?event_type=model_promoted").json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "promote_model"

    def test_filter_by_entity_type(self) -> None:
        with self.client as c:
            data = c.get("/audit?entity_type=model_registry").json()
        assert data["total"] == 1

    def test_filter_by_entity_id(self) -> None:
        with self.client as c:
            data = c.get(f"/audit?entity_id={ENTITY_ID}").json()
        assert data["total"] == 1
        assert data["items"][0]["entity_id"] == str(ENTITY_ID)

    def test_since_filter(self) -> None:
        since = NOW - timedelta(minutes=90)
        with self.client as c:
            data = c.get("/audit", params={"since": since.isoformat()}).json()
        assert data["total"] == 2

    def test_until_filter(self) -> None:
        until = NOW - timedelta(minutes=90)
        with self.client as c:
            data = c.get("/audit", params={"until": until.isoformat()}).json()
        assert data["total"] == 1

    def test_invalid_event_type_422(self) -> None:
        with self.client as c:
            r = c.get("/audit?event_type=banana")
        assert r.status_code == 422

    def test_response_fields(self) -> None:
        with self.client as c:
            item = c.get("/audit").json()["items"][0]
        for field in ("id", "event_type", "actor", "action", "occurred_at", "created_at"):
            assert field in item

    def test_limit_and_offset(self) -> None:
        with self.client as c:
            data = c.get("/audit?limit=2&offset=0").json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
