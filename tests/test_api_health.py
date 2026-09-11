"""Tests for GET /health and GET /health/ready (Phase 10)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import Base


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealth:
    def test_liveness(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "no-referrer"

    def test_request_id_is_echoed_and_safe(self, client: TestClient) -> None:
        r = client.get("/health", headers={"X-Request-ID": "trace-123"})
        assert r.headers["X-Request-ID"] == "trace-123"

    def test_invalid_request_id_is_replaced(self, client: TestClient) -> None:
        r = client.get("/health", headers={"X-Request-ID": "bad\nvalue"})
        assert r.headers["X-Request-ID"] != "bad\nvalue"
        assert len(r.headers["X-Request-ID"]) == 36

    def test_readiness_with_db(self, client: TestClient) -> None:
        r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["db"] == "ok"
