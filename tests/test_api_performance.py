"""Tests for GET /performance/report and GET /performance/segments (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.main import app
from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
)
from backend.models.settlements import Settlement, SettlementOutcome

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=3)


@pytest.fixture()
def client():
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
        home, away = Team(name="H"), Team(name="A")
        fixture = Fixture(
            competition=comp,
            season=ssn,
            home_team=home,
            away_team=away,
            kickoff_utc=KICKOFF,
            status=FixtureStatus.FINISHED,
            home_goals=2,
            away_goals=1,
        )
        seed.add_all([comp, ssn, home, away, fixture])
        seed.flush()

        p1 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=KICKOFF - timedelta(hours=1),
            decision_as_of=KICKOFF - timedelta(hours=1),
            market="1X2",
            selection="home",
            conservative_probability=0.60,
            executable_odds=1.80,
        )
        p2 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=KICKOFF - timedelta(hours=1),
            decision_as_of=KICKOFF - timedelta(hours=1),
            market="BTTS",
            selection="yes",
            conservative_probability=0.45,
            executable_odds=2.10,
        )
        seed.add_all([p1, p2])
        seed.flush()

        seed.add_all([
            Settlement(
                subject_type="prediction",
                subject_id=p1.id,
                outcome=SettlementOutcome.WIN,
                settled_at=NOW,
                taken_odds=1.80,
                taken_probability=0.60,
                brier_contribution=0.16,
                log_loss_contribution=0.51,
                clv=0.04,
            ),
            Settlement(
                subject_type="prediction",
                subject_id=p2.id,
                outcome=SettlementOutcome.LOSS,
                settled_at=NOW,
                taken_odds=2.10,
                taken_probability=0.45,
                brier_contribution=0.20,
                log_loss_contribution=0.80,
                clv=-0.02,
            ),
        ])
        seed.commit()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestPerformanceReport:
    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/performance/report")
        assert r.status_code == 200

    def test_shape_has_all_kpi_fields(self, client: TestClient) -> None:
        data = client.get("/performance/report").json()
        for field in (
            "n_total", "n_settled", "n_wins", "n_losses", "n_voids", "n_pushes",
            "hit_rate", "average_odds", "break_even_hit_rate",
            "brier_score", "brier_skill_score", "log_loss", "ece",
            "calibration_slope", "calibration_intercept",
            "mean_clv", "n_clv", "roi", "total_stake", "total_profit",
            "max_drawdown", "volatility",
        ):
            assert field in data, f"missing field: {field}"

    def test_counts_correct(self, client: TestClient) -> None:
        data = client.get("/performance/report").json()
        assert data["n_total"] == 2
        assert data["n_wins"] == 1
        assert data["n_losses"] == 1
        assert data["hit_rate"] == pytest.approx(0.5)

    def test_mean_clv(self, client: TestClient) -> None:
        data = client.get("/performance/report").json()
        assert data["mean_clv"] == pytest.approx(0.01)

    def test_since_filter(self, client: TestClient) -> None:
        future = NOW + timedelta(days=1)
        data = client.get("/performance/report", params={"since": future.isoformat()}).json()
        assert data["n_total"] == 0

    def test_invalid_subject_type_422(self, client: TestClient) -> None:
        r = client.get("/performance/report?subject_type=unknown")
        assert r.status_code == 422

    def test_empty_db_returns_zero_counts(self) -> None:
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
        try:
            with TestClient(app) as c:
                data = c.get("/performance/report").json()
                assert data["n_total"] == 0
                assert data["hit_rate"] is None
        finally:
            app.dependency_overrides.clear()


class TestPerformanceSegments:
    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/performance/segments")
        assert r.status_code == 200

    def test_shape(self, client: TestClient) -> None:
        data = client.get("/performance/segments").json()
        assert "by" in data
        assert "segments" in data
        assert data["by"] == "market"

    def test_segments_by_market(self, client: TestClient) -> None:
        data = client.get("/performance/segments?by=market").json()
        assert "1X2" in data["segments"]
        assert "BTTS" in data["segments"]
        assert data["segments"]["1X2"]["n_wins"] == 1
        assert data["segments"]["BTTS"]["n_losses"] == 1

    def test_segments_by_league(self, client: TestClient) -> None:
        data = client.get("/performance/segments?by=league").json()
        assert "EPL" in data["segments"]
        assert data["segments"]["EPL"]["n_total"] == 2

    def test_segments_by_model_version(self, client: TestClient) -> None:
        data = client.get("/performance/segments?by=model_version").json()
        assert "(unknown)" in data["segments"]

    def test_invalid_by_422(self, client: TestClient) -> None:
        r = client.get("/performance/segments?by=bookmaker")
        assert r.status_code == 422

    def test_invalid_subject_type_422(self, client: TestClient) -> None:
        r = client.get("/performance/segments?subject_type=bad")
        assert r.status_code == 422
