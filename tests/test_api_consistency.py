"""The API's numbers agree with each other once a ticket is settled.

One finished match, one priced forecast on it, one ticket published late at
night UTC (already the next day in Africa/Blantyre).  After a settlement run
the forecast archive, the ticket archive, the performance report and the
results-by-period calendar must all tell the same story.
"""

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
from backend.workers.settlement_worker import run_settlement

# 23:30 UTC on 6 Sep is 01:30 on 7 Sep in Africa/Blantyre (UTC+2).
PUBLISHED = datetime(2026, 9, 6, 23, 30, tzinfo=UTC)
KICKOFF = PUBLISHED + timedelta(hours=14)
SETTLED_AT = KICKOFF + timedelta(hours=3)


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
        home, away = Team(name="Home FC"), Team(name="Away FC")
        fixture = Fixture(
            competition=comp, season=ssn, home_team=home, away_team=away,
            kickoff_utc=KICKOFF, status=FixtureStatus.FINISHED, home_goals=2, away_goals=0,
        )
        seed.add_all([comp, ssn, home, away, fixture])
        seed.flush()
        priced = Prediction(
            fixture_id=fixture.id, prediction_timestamp=PUBLISHED, decision_as_of=PUBLISHED,
            market="1X2", selection="home", conservative_probability=0.62,
            executable_odds=1.85,
        )
        unpriced = Prediction(
            fixture_id=fixture.id, prediction_timestamp=PUBLISHED, decision_as_of=PUBLISHED,
            market="BTTS", selection="yes", conservative_probability=0.55,
        )
        seed.add_all([priced, unpriced])
        seed.flush()
        ticket = Accumulator(
            product="daily_safe", optimiser_version="v1", policy_version="v1",
            combined_odds=1.85, conservative_joint_probability=0.62,
            stressed_joint_probability=0.55, objective_score=0.9,
            dependence_penalty_applied=0.0, published_at=PUBLISHED,
        )
        seed.add(ticket)
        seed.flush()
        seed.add(AccumulatorLeg(
            accumulator_id=ticket.id, prediction_id=priced.id, leg_index=0,
            fixture_id=fixture.id, league_id="39", market_family="1X2", selection="home",
            decimal_odds=1.85, conservative_probability=0.62, edge=0.03, qss=85.0,
        ))
        seed.flush()
        run_settlement(seed, now=SETTLED_AT)
        seed.commit()

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_forecasts_can_be_limited_to_priced_markets_with_match_context(client) -> None:
    body = client.get("/predictions", params={"priced_only": "true"}).json()
    assert body["total"] == 1
    [item] = body["items"]
    assert (item["home_team"], item["away_team"]) == ("Home FC", "Away FC")
    assert item["competition_name"] == "EPL"
    assert item["outcome"] == "win"
    assert client.get("/predictions").json()["total"] == 2  # default unchanged
    assert client.get("/predictions/markets").json() == ["1X2"]


def test_ticket_archive_reports_the_settled_result(client) -> None:
    [ticket] = client.get("/accumulators").json()["items"]
    assert ticket["status"] == "settled"
    assert ticket["result"] == "won"
    assert ticket["settlement_odds"] == pytest.approx(1.85)
    assert ticket["profit_units"] == pytest.approx(0.85)


def test_performance_report_matches_the_ticket(client) -> None:
    report = client.get("/performance/report", params={"subject_type": "accumulator"}).json()
    assert (report["n_wins"], report["n_losses"]) == (1, 0)
    assert report["stake_basis"] == "flat_unit"
    assert report["total_profit"] == pytest.approx(0.85)
    assert report["roi"] == pytest.approx(0.85)
    assert report["n_awaiting"] == 0

    segments = client.get(
        "/performance/segments", params={"by": "product", "subject_type": "accumulator"}
    ).json()["segments"]
    assert segments["daily_safe"]["roi"] == pytest.approx(0.85)


def test_calendar_and_day_archive_use_the_same_product_day(client) -> None:
    results = client.get("/performance/accumulator-results", params={"granularity": "day"}).json()
    [period] = results["periods"]
    assert period["period"] == "2026-09-07"
    assert period["products"][0]["won"] == 1
    assert client.get("/accumulators", params={"date": "2026-09-07"}).json()["total"] == 1
    assert client.get("/accumulators", params={"date": "2026-09-06"}).json()["total"] == 0
