"""Tests for GET /accumulators and GET /accumulators/{id} (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
)
from backend.models.settlements import TicketStatus

NOW = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


@pytest.fixture()
def seeded_client():
    """Client with one PENDING accumulator (2 legs) and one SETTLED accumulator."""
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
            status=FixtureStatus.SCHEDULED,
        )
        seed.add_all([comp, ssn, home, away, fixture])
        seed.flush()

        p1 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market="1X2",
            selection="home",
            conservative_probability=0.62,
            executable_odds=1.85,
        )
        p2 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market="BTTS",
            selection="yes",
            conservative_probability=0.55,
            executable_odds=1.72,
        )
        seed.add_all([p1, p2])
        seed.flush()

        acca1 = Accumulator(
            product="Core",
            optimiser_version="v1.0",
            policy_version="v1.0",
            combined_odds=3.19,
            conservative_joint_probability=0.34,
            stressed_joint_probability=0.28,
            objective_score=0.92,
            dependence_penalty_applied=0.0,
            published_at=NOW - timedelta(hours=1),
            status=TicketStatus.PENDING,
        )
        acca2 = Accumulator(
            product="Growth",
            optimiser_version="v1.0",
            policy_version="v1.0",
            combined_odds=5.80,
            conservative_joint_probability=0.18,
            stressed_joint_probability=0.14,
            objective_score=0.87,
            dependence_penalty_applied=0.01,
            published_at=NOW - timedelta(hours=2),
            status=TicketStatus.SETTLED,
        )
        seed.add_all([acca1, acca2])
        seed.flush()

        leg1 = AccumulatorLeg(
            accumulator_id=acca1.id,
            prediction_id=p1.id,
            leg_index=0,
            fixture_id=fixture.id,
            league_id="39",
            market_family="1X2",
            selection="home",
            decimal_odds=1.85,
            conservative_probability=0.62,
            edge=0.07,
            qss=88.0,
        )
        leg2 = AccumulatorLeg(
            accumulator_id=acca1.id,
            prediction_id=p2.id,
            leg_index=1,
            fixture_id=fixture.id,
            league_id="39",
            market_family="BTTS",
            selection="yes",
            decimal_odds=1.72,
            conservative_probability=0.55,
            edge=0.05,
            qss=85.0,
        )
        seed.add_all([leg1, leg2])
        seed.commit()
        acca1_id = acca1.id
        acca2_id = acca2.id

    with TestClient(app) as client:
        yield client, acca1_id, acca2_id

    app.dependency_overrides.clear()


class TestListAccumulators:
    def test_returns_all(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2

    def test_filter_by_status_pending(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "pending"

    def test_legs_included(self, seeded_client) -> None:
        client, acca1_id, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["id"] == str(acca1_id)
        assert len(item["legs"]) == 2

    def test_legs_ordered_by_leg_index(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/accumulators", params={"status": "pending"})
        legs = r.json()["items"][0]["legs"]
        indices = [leg["leg_index"] for leg in legs]
        assert indices == sorted(indices)


class TestGetAccumulator:
    def test_returns_by_id(self, seeded_client) -> None:
        client, acca1_id, _ = seeded_client
        r = client.get(f"/accumulators/{acca1_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(acca1_id)
        assert data["product"] == "Core"
        assert len(data["legs"]) == 2

    def test_404_for_unknown_id(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get(f"/accumulators/{uuid.uuid4()}")
        assert r.status_code == 404
