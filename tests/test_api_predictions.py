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
from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    ModelFamily,
    ModelRegistry,
    ModelStatus,
    Prediction,
    Season,
    Team,
)
from backend.models.settlements import Settlement, SettlementOutcome

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
        model = ModelRegistry(
            family=ModelFamily.ENSEMBLE,
            name="test-ensemble",
            version="1.0.0",
            status=ModelStatus.CHAMPION,
        )
        seed.add(model)
        seed.flush()

        p1 = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=KICKOFF - timedelta(hours=1),
            decision_as_of=KICKOFF - timedelta(hours=1),
            market="1X2",
            selection="home",
            model_version_id=model.id,
            conservative_probability=0.62,
            executable_odds=1.85,
            research_mode=True,
            gate_passed=False,
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

    def test_exposes_archive_audit_context_and_overdue_settlement(self, seeded_client) -> None:
        client, _, _ = seeded_client
        item = client.get("/predictions").json()["items"][0]
        assert item["research_mode"] is True
        assert item["gate_passed"] is False
        assert item["settlement_overdue"] is True
        assert item["model_version_label"] == "test-ensemble 1.0.0"

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

    def test_scope_filters_preserve_production_research_and_overdue_boundaries(self, seeded_client) -> None:
        client, _, _ = seeded_client

        production = client.get("/predictions", params={"scope": "production"}).json()
        assert production["total"] == 1
        assert production["items"][0]["research_mode"] is False

        research = client.get("/predictions", params={"scope": "research"}).json()
        assert research["total"] == 1
        assert research["items"][0]["research_mode"] is True

        overdue = client.get("/predictions", params={"scope": "overdue"}).json()
        assert overdue["total"] == 2
        assert all(item["settlement_overdue"] for item in overdue["items"])

    def test_scope_awaiting_excludes_past_unsettled_forecasts(self, seeded_client) -> None:
        client, _, _ = seeded_client
        response = client.get("/predictions", params={"scope": "awaiting"})
        assert response.status_code == 200
        assert response.json()["total"] == 0

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


class TestSortPredictions:
    def test_sort_by_conservative_probability_ascending(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"sort": "conservative_probability", "dir": "asc"})
        assert r.status_code == 200
        probs = [item["conservative_probability"] for item in r.json()["items"]]
        assert probs == sorted(probs)

    def test_sort_by_market_descending(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"sort": "market", "dir": "desc"})
        assert r.status_code == 200
        markets = [item["market"] for item in r.json()["items"]]
        assert markets == ["BTTS", "1X2"]

    def test_default_order_unchanged_when_no_sort_given(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions")
        assert r.status_code == 200
        # Newest prediction_timestamp first, matching pre-existing behaviour.
        assert r.json()["items"][0]["market"] == "1X2"

    def test_unknown_sort_column_rejected(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get("/predictions", params={"sort": "not_a_real_column"})
        assert r.status_code == 422

    def test_invalid_dir_rejected(self, seeded_client) -> None:
        client, _, _ = seeded_client
        r = client.get(
            "/predictions", params={"sort": "conservative_probability", "dir": "sideways"}
        )
        assert r.status_code == 422

    def test_nulls_sort_last_even_when_descending(self, seeded_client) -> None:
        """A NULL executable_odds must never appear first in a 'highest first' sort.

        Postgres defaults DESC ordering to NULLS FIRST, which would otherwise
        put a prediction with no odds at all above one with the highest odds.
        """
        client, fixture_id, _ = seeded_client

        # Insert a third prediction with no odds via the same DB override
        # the fixture already wired up.
        gen = app.dependency_overrides[get_db]()
        db = next(gen)
        try:
            null_odds_pred = Prediction(
                fixture_id=fixture_id,
                prediction_timestamp=KICKOFF - timedelta(hours=3),
                decision_as_of=KICKOFF - timedelta(hours=3),
                market="OU",
                selection="over",
                conservative_probability=0.50,
                executable_odds=None,
            )
            db.add(null_odds_pred)
            db.commit()
        finally:
            gen.close()

        r = client.get("/predictions", params={"sort": "executable_odds", "dir": "desc"})
        assert r.status_code == 200
        odds = [item["executable_odds"] for item in r.json()["items"]]
        assert odds[-1] is None
        assert odds[0] == max(o for o in odds if o is not None)


    def test_sort_by_match_kickoff(self, seeded_client) -> None:
        """'Match' sorts by the fixture's kickoff, not the forecast timestamp."""
        client, fixture_id, _ = seeded_client
        gen = app.dependency_overrides[get_db]()
        db = next(gen)
        try:
            base = db.get(Fixture, fixture_id)
            later = Fixture(
                competition_id=base.competition_id,
                season_id=base.season_id,
                home_team_id=base.away_team_id,
                away_team_id=base.home_team_id,
                kickoff_utc=KICKOFF + timedelta(days=2),
                status=FixtureStatus.SCHEDULED,
            )
            db.add(later)
            db.flush()
            # Oldest forecast, but for the latest match.
            db.add(Prediction(
                fixture_id=later.id,
                prediction_timestamp=KICKOFF - timedelta(days=5),
                decision_as_of=KICKOFF - timedelta(days=5),
                market="OU",
                selection="over",
                conservative_probability=0.5,
                executable_odds=2.0,
            ))
            db.commit()
        finally:
            gen.close()

        desc = client.get("/predictions", params={"sort": "kickoff_utc", "dir": "desc"}).json()
        assert desc["items"][0]["market"] == "OU"
        asc = client.get("/predictions", params={"sort": "kickoff_utc", "dir": "asc"}).json()
        assert asc["items"][-1]["market"] == "OU"
        assert asc["total"] == 3  # sorting never changes the row count

    def test_sort_by_result_uses_effective_outcome_open_last(self, seeded_client) -> None:
        client, _, p1_id = seeded_client
        gen = app.dependency_overrides[get_db]()
        db = next(gen)
        try:
            p2 = db.query(Prediction).filter(Prediction.market == "BTTS").one()
            original = Settlement(
                subject_type="prediction", subject_id=p1_id,
                outcome=SettlementOutcome.LOSS, settled_at=NOW,
            )
            db.add(original)
            db.flush()
            # The correction is the effective result: p1 is a win.
            db.add(Settlement(
                subject_type="prediction", subject_id=p1_id,
                outcome=SettlementOutcome.WIN, settled_at=NOW + timedelta(minutes=5),
                supersedes_id=original.id,
            ))
            db.commit()
            p2_id = p2.id
        finally:
            gen.close()

        for direction in ("asc", "desc"):
            items = client.get(
                "/predictions", params={"sort": "outcome", "dir": direction}
            ).json()["items"]
            assert [i["id"] for i in items] == [str(p1_id), str(p2_id)]  # open (NULL) last
            assert items[0]["outcome"] == "win"


class TestGetPrediction:
    def test_returns_prediction_by_id(self, seeded_client) -> None:
        client, _, p1_id = seeded_client
        r = client.get(f"/predictions/{p1_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(p1_id)
        assert data["market"] == "1X2"
        assert data["selection"] == "home"
        assert data["research_mode"] is True
        assert data["settlement_overdue"] is True

    def test_404_for_unknown_id(self, seeded_client) -> None:
        import uuid
        client, _, _ = seeded_client
        r = client.get(f"/predictions/{uuid.uuid4()}")
        assert r.status_code == 404
