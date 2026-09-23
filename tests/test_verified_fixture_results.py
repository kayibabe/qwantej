"""Reviewed external fixture results follow the append-only settlement path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditEvent,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Settlement,
    SettlementOutcome,
    StatsSnapshot,
    Team,
)
from backend.services.verified_fixture_results import (
    VerifiedFixtureResultError,
    ingest_verified_fixture_result,
)
from backend.workers.settlement_worker import run_settlement

NOW = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=6)
SOURCE_URL = "https://sportdc.net/vest/prva-liga-rs/179062-drina-duboka-za-rudare-"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _pending_home_prediction(session: Session) -> tuple[Fixture, Prediction]:
    competition = Competition(name="1st League - RS")
    season = Season(competition=competition, label="2026/27")
    home, away = Team(name="Drina Zvornik"), Team(name="Rudar Prijedor")
    fixture = Fixture(
        competition=competition,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=KICKOFF,
        status=FixtureStatus.SCHEDULED,
    )
    session.add(fixture)
    session.flush()
    prediction = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=KICKOFF - timedelta(hours=1),
        decision_as_of=KICKOFF - timedelta(hours=1),
        market="1X2",
        selection="home",
        conservative_probability=0.604,
        executable_odds=1.47,
        bookmaker="1xBet",
    )
    session.add(prediction)
    session.flush()
    return fixture, prediction


def test_verified_result_is_audited_and_settled_through_worker(session: Session) -> None:
    fixture, prediction = _pending_home_prediction(session)

    changed = ingest_verified_fixture_result(
        session,
        fixture_id=fixture.id,
        home_goals=1,
        away_goals=0,
        source_url=SOURCE_URL,
        observed_at=NOW,
    )
    settlement_run = run_settlement(session, now=NOW)

    assert changed is True
    assert fixture.status is FixtureStatus.FINISHED
    assert (fixture.home_goals, fixture.away_goals) == (1, 0)
    assert settlement_run.total_settled == 1
    settlement = session.scalar(
        select(Settlement).where(
            Settlement.subject_id == prediction.id,
            Settlement.subject_type == "prediction",
        )
    )
    assert settlement is not None
    assert settlement.outcome is SettlementOutcome.WIN
    snapshot = session.scalar(
        select(StatsSnapshot).where(
            StatsSnapshot.fixture_id == fixture.id,
            StatsSnapshot.source == "verified-result:sportdc.net",
        )
    )
    assert snapshot is not None
    assert snapshot.payload["record"]["goals"] == {"home": 1, "away": 0}
    event = session.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == fixture.id)
    )
    assert event is not None
    assert event.payload["source_url"] == SOURCE_URL
    assert event.payload["after"]["status"] == "finished"


def test_verified_result_rejects_conflict_after_fixture_is_finished(session: Session) -> None:
    fixture, _ = _pending_home_prediction(session)
    ingest_verified_fixture_result(
        session,
        fixture_id=fixture.id,
        home_goals=1,
        away_goals=0,
        source_url=SOURCE_URL,
        observed_at=NOW,
    )

    with pytest.raises(VerifiedFixtureResultError, match="cannot be replaced"):
        ingest_verified_fixture_result(
            session,
            fixture_id=fixture.id,
            home_goals=2,
            away_goals=0,
            source_url=SOURCE_URL,
            observed_at=NOW + timedelta(minutes=1),
        )


def test_verified_result_requires_https_evidence(session: Session) -> None:
    fixture, _ = _pending_home_prediction(session)

    with pytest.raises(VerifiedFixtureResultError, match="public HTTPS URL"):
        ingest_verified_fixture_result(
            session,
            fixture_id=fixture.id,
            home_goals=1,
            away_goals=0,
            source_url="http://sportdc.net/match-report",
            observed_at=NOW,
        )
