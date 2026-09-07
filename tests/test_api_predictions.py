"""Tests for GET /predictions and GET /predictions/{id} (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import Base, Competition, Fixture, FixtureStatus, Prediction, Season, Team

NOW = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=3)


@pytest.fixture()
def seeded_client():
    """TestClient + seeded SQLite DB. Yields (client, session)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override

    with factory() as seed:
        comp = Competition(name="EPL")
        ssn = Season(competition=comp, label="2026/27")
        home, away = Team(name="Home FC"), Team(name="Away FC")
        fixture = Fixture(
            competition=comp,
            season=ssn,
            home_team=home,
            away_team=away,
            kickoff_utc=KICKOFF,
            status=FixtureStatus.FINISHED,
            home_goals=2,
            away_goals=0,
        )
        seed.add_all([comp, ssn, home, away, fixture])
        seed.flush()

        p1 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=KICKOFF - timedelta(hours=1),
            decision_as_of=KICKOFF - timedelta(hours=1),
            market="1X2",
            selection="home",
            conservative_probability=0.62,
            executable_odds=1.85,
        )
        p2 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=KICKOFF - timedelta(hours=2),
            decision_as_of=KICKOFF - timedelta(hours=2),
            market="BTTS",
            selection="yes",
            conservative_probability=0.55,
            executable_odds=1.72,
        )
        seed.add_all([p1, p2])
        seed.commit()
        fixture_id = fixture.id
        p1_id = p1.id

    with TestClient(app) as client:
        yield client, fixture_id, p1_id

    app.dependency_overrides.clear()


class TestListPredictions:
    def test_returns_all_when_no_filter(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_filter_by_fixture_id(self, seeded_client) -> None:
        client, fixture_id, _ = seeded_client
        r = client.get("/predictions", params={"fixture_id": str(fixture_id)})
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_market(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"market": "1X2"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["market"] == "1X2"

    def test_pagination_limit(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"limit": 1, "offset": 0})
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2

    def test_pagination_offset(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"limit": 1, "offset": 1})
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    def test_empty_result_when_no_match(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"market": "HANDICAP"})
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestGetPrediction:
    def test_returns_prediction_by_id(self, seeded_client) -> None:
        client, _, p1_id = seeded_client
        r = client.get(f"/predictions/{p1_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(p1_id)
        assert data["market"] == "1X2"
        assert data["selection"] == "home"

    def test_404_for_unknown_id(self, seeded_client) -> None:
        import uuid
        client, _, _ = seeded_client
        r = client.get(f"/predictions/{uuid.uuid4()}")
        assert r.status_code == 404
