"""Tests for GET /settlements and GET /settlements/summary (Phase 10)."""

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
    Settlement,
    Team,
)
from backend.models import SettlementOutcome as OrmOutcome

NOW = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=3)


@pytest.fixture()
def seeded_client():
    """Client with two WIN settlements and one LOSS settlement (all effective)."""
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

        def _pred(selection: str) -> Prediction:
            return Prediction(
                fixture_id=fixture.id,
                prediction_timestamp=KICKOFF - timedelta(hours=1),
                decision_as_of=KICKOFF - timedelta(hours=1),
                market="1X2",
                selection=selection,
                conservative_probability=0.60,
                executable_odds=1.85,
            )

        p1, p2, p3 = _pred("home"), _pred("draw"), _pred("away")
        seed.add_all([p1, p2, p3])
        seed.flush()

        seed.add_all([
            Settlement(
                subject_type="prediction",
                subject_id=p1.id,
                outcome=OrmOutcome.WIN,
                settled_at=NOW,
                clv=0.05,
                brier_contribution=0.15,
                reason_codes=[],
            ),
            Settlement(
                subject_type="prediction",
                subject_id=p2.id,
                outcome=OrmOutcome.LOSS,
                settled_at=NOW,
                clv=-0.03,
                brier_contribution=0.40,
                reason_codes=[],
            ),
            Settlement(
                subject_type="prediction",
                subject_id=p3.id,
                outcome=OrmOutcome.WIN,
                settled_at=NOW,
                clv=0.10,
                brier_contribution=0.12,
                reason_codes=[],
            ),
        ])
        seed.commit()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class TestListSettlements:
    def test_returns_all_effective(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_filter_by_outcome_win(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements", params={"outcome": "win"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert all(item["outcome"] == "win" for item in data["items"])

    def test_filter_by_outcome_loss(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements", params={"outcome": "loss"})
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_pagination(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements", params={"limit": 2, "offset": 0})
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


class TestSettlementSummary:
    def test_counts_correct(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["n_settled"] == 3
        assert data["n_wins"] == 2
        assert data["n_losses"] == 1
        assert data["n_voids"] == 0

    def test_win_rate(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements/summary")
        assert r.status_code == 200
        assert abs(r.json()["win_rate"] - 2 / 3) < 1e-6

    def test_avg_clv(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements/summary")
        assert r.status_code == 200
        expected = (0.05 + -0.03 + 0.10) / 3
        assert abs(r.json()["avg_clv"] - expected) < 1e-4

    def test_avg_brier(self, seeded_client: TestClient) -> None:
        r = seeded_client.get("/settlements/summary")
        assert r.status_code == 200
        expected = (0.15 + 0.40 + 0.12) / 3
        assert abs(r.json()["avg_brier"] - expected) < 1e-4

    def test_correction_excluded_from_summary(self) -> None:
        """A superseded original must not appear in the summary; only the correction counts."""
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
                    home_goals=1,
                    away_goals=0,
                )
                seed.add_all([comp, ssn, home, away, fixture])
                seed.flush()
                pred = Prediction(
                    fixture_id=fixture.id,
                    prediction_timestamp=KICKOFF - timedelta(hours=1),
                    decision_as_of=KICKOFF - timedelta(hours=1),
                    market="1X2",
                    selection="home",
                    conservative_probability=0.60,
                    executable_odds=1.85,
                )
                seed.add(pred)
                seed.flush()
                # Original settlement (WIN)
                original = Settlement(
                    subject_type="prediction",
                    subject_id=pred.id,
                    outcome=OrmOutcome.WIN,
                    settled_at=NOW,
                    reason_codes=[],
                )
                seed.add(original)
                seed.flush()
                # Correction row that supersedes the original (flipped to LOSS)
                correction = Settlement(
                    subject_type="prediction",
                    subject_id=pred.id,
                    outcome=OrmOutcome.LOSS,
                    settled_at=NOW + timedelta(seconds=1),
                    reason_codes=["CORRECTION"],
                    supersedes_id=original.id,
                )
                seed.add(correction)
                seed.commit()

            with TestClient(app) as client:
                r = client.get("/settlements/summary")
            assert r.status_code == 200
            data = r.json()
            # Only the correction (LOSS) is effective; the original (WIN) is superseded.
            assert data["n_settled"] == 1
            assert data["n_wins"] == 0
            assert data["n_losses"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_empty_when_no_settlements(self) -> None:
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
            with TestClient(app) as client:
                r = client.get("/settlements/summary")
            assert r.status_code == 200
            data = r.json()
            assert data["n_settled"] == 0
            assert data["win_rate"] is None
            assert data["avg_clv"] is None
        finally:
            app.dependency_overrides.clear()
