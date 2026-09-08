"""Tests for GET /models, /models/{id}, /models/{id}/runs (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import Base
from backend.models.registry import (
    ModelFamily,
    ModelRegistry,
    ModelRun,
    ModelRunKind,
    ModelRunStatus,
    ModelStatus,
)

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def client():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override

    with factory() as seed:
        m1 = ModelRegistry(
            family=ModelFamily.POISSON,
            name="poisson-baseline",
            version="1.0.0",
            status=ModelStatus.CHAMPION,
        )
        m2 = ModelRegistry(
            family=ModelFamily.ELO,
            name="elo-rating",
            version="1.0.0",
            status=ModelStatus.DEVELOPMENT,
        )
        seed.add_all([m1, m2])
        seed.flush()

        run1 = ModelRun(
            model_id=m1.id,
            kind=ModelRunKind.TRAINING,
            status=ModelRunStatus.SUCCEEDED,
            started_at=NOW - timedelta(hours=4),
            finished_at=NOW - timedelta(hours=3),
            metrics={"brier": 0.20},
        )
        run2 = ModelRun(
            model_id=m1.id,
            kind=ModelRunKind.EVALUATION,
            status=ModelRunStatus.SUCCEEDED,
            started_at=NOW - timedelta(hours=2),
            finished_at=NOW - timedelta(hours=1),
            metrics={"brier": 0.18, "log_loss": 0.52},
        )
        seed.add_all([run1, run2])
        seed.commit()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestListModels:
    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/models")
        assert r.status_code == 200

    def test_pagination_shape(self, client: TestClient) -> None:
        data = client.get("/models").json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 2

    def test_filter_by_status(self, client: TestClient) -> None:
        data = client.get("/models?status=champion").json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "poisson-baseline"

    def test_filter_by_family(self, client: TestClient) -> None:
        data = client.get("/models?family=elo").json()
        assert data["total"] == 1
        assert data["items"][0]["version"] == "1.0.0"

    def test_invalid_status_422(self, client: TestClient) -> None:
        r = client.get("/models?status=superstar")
        assert r.status_code == 422

    def test_invalid_family_422(self, client: TestClient) -> None:
        r = client.get("/models?family=sorcery")
        assert r.status_code == 422

    def test_response_fields(self, client: TestClient) -> None:
        item = client.get("/models").json()["items"][0]
        for field in ("id", "family", "name", "version", "status", "created_at"):
            assert field in item


class TestGetModel:
    def test_returns_model_with_runs(self, client: TestClient) -> None:
        models = client.get("/models?status=champion").json()["items"]
        model_id = models[0]["id"]
        data = client.get(f"/models/{model_id}").json()
        assert data["name"] == "poisson-baseline"
        assert "runs" in data
        assert len(data["runs"]) == 2

    def test_404_for_unknown_id(self, client: TestClient) -> None:
        r = client.get("/models/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_run_metrics_present(self, client: TestClient) -> None:
        model_id = client.get("/models?status=champion").json()["items"][0]["id"]
        run = client.get(f"/models/{model_id}").json()["runs"][0]
        assert run["metrics"]["brier"] == pytest.approx(0.18)

    def test_nested_runs_ordered_newest_first(self, client: TestClient) -> None:
        model_id = client.get("/models?status=champion").json()["items"][0]["id"]
        runs = client.get(f"/models/{model_id}").json()["runs"]
        # evaluation run started 2h ago; training run started 4h ago
        assert runs[0]["kind"] == "evaluation"
        assert runs[1]["kind"] == "training"


class TestListModelRuns:
    def test_returns_runs_page(self, client: TestClient) -> None:
        model_id = client.get("/models?status=champion").json()["items"][0]["id"]
        data = client.get(f"/models/{model_id}/runs").json()
        assert data["total"] == 2
        assert data["items"][0]["status"] == "succeeded"

    def test_filter_by_kind(self, client: TestClient) -> None:
        model_id = client.get("/models?status=champion").json()["items"][0]["id"]
        data = client.get(f"/models/{model_id}/runs?kind=evaluation").json()
        assert data["total"] == 1
        assert data["items"][0]["kind"] == "evaluation"

    def test_404_for_unknown_model(self, client: TestClient) -> None:
        r = client.get("/models/00000000-0000-0000-0000-000000000000/runs")
        assert r.status_code == 404

    def test_invalid_kind_422(self, client: TestClient) -> None:
        model_id = client.get("/models?status=champion").json()["items"][0]["id"]
        r = client.get(f"/models/{model_id}/runs?kind=wizardry")
        assert r.status_code == 422
