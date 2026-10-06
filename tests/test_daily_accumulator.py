"""Tests for the persisted Daily Pick merge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

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
    TicketStatus,
)
from backend.services.daily_accumulator import ensure_daily_accumulator


NOW = datetime(2026, 10, 6, 8, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _fixture(session: Session, index: int) -> tuple[Fixture, Prediction]:
    competition = Competition(name=f"League {index}")
    season = Season(competition=competition, label="2026")
    home = Team(name=f"Home {index}")
    away = Team(name=f"Away {index}")
    fixture = Fixture(
        competition=competition,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=NOW + timedelta(hours=8),
        status=FixtureStatus.SCHEDULED,
    )
    prediction = Prediction(
        fixture=fixture,
        prediction_timestamp=NOW - timedelta(hours=1),
        decision_as_of=NOW - timedelta(hours=1),
        market="1X2",
        selection="home",
        conservative_probability=0.60,
        calibrated_probability=0.65,
        dqs=80,
        qss=80,
    )
    session.add(prediction)
    session.flush()
    return fixture, prediction


def _source_ticket(
    session: Session,
    product: str,
    legs: list[tuple[Fixture, Prediction, str]],
) -> Accumulator:
    ticket = Accumulator(
        product=product,
        optimiser_version="daily-test",
        policy_version="daily-test",
        combined_odds=2.0,
        conservative_joint_probability=0.4,
        stressed_joint_probability=0.38,
        objective_score=0.8,
        dependence_penalty_applied=0.0,
        published_at=NOW - timedelta(minutes=30),
        status=TicketStatus.PENDING,
        paper_only=True,
    )
    session.add(ticket)
    session.flush()
    for index, (fixture, prediction, selection) in enumerate(legs):
        session.add(
            AccumulatorLeg(
                accumulator_id=ticket.id,
                prediction_id=prediction.id,
                leg_index=index,
                fixture_id=fixture.id,
                league_id="test",
                market_family="1X2",
                selection=selection,
                decimal_odds=Decimal("1.80"),
                conservative_probability=Decimal("0.60"),
                edge=Decimal("0.05"),
                qss=80,
                bookmaker="Book",
            )
        )
        prediction.accumulator_id = ticket.id
    session.flush()
    return ticket


def test_merge_waits_for_both_source_tickets() -> None:
    with _session() as session:
        result = ensure_daily_accumulator(session, now=NOW)
        assert result.waiting_for_sources is True
        assert result.name == "Accu-2026-10-06"


def test_merge_uses_union_and_conservative_conflict_priority() -> None:
    with _session() as session:
        fixture_a, prediction_a = _fixture(session, 1)
        fixture_conflict, prediction_conservative = _fixture(session, 2)
        fixture_only_balanced, prediction_balanced = _fixture(session, 3)
        prediction_balanced_conflict = Prediction(
            fixture=fixture_conflict,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market="1X2",
            selection="away",
            conservative_probability=0.55,
            calibrated_probability=0.60,
            dqs=80,
            qss=80,
        )
        session.add(prediction_balanced_conflict)
        session.flush()

        conservative = _source_ticket(
            session,
            "daily_safe",
            [
                (fixture_a, prediction_a, "home"),
                (fixture_conflict, prediction_conservative, "home"),
            ],
        )
        balanced = _source_ticket(
            session,
            "daily_balanced",
            [
                (fixture_conflict, prediction_balanced_conflict, "away"),
                (fixture_only_balanced, prediction_balanced, "draw"),
            ],
        )

        result = ensure_daily_accumulator(session, now=NOW)
        assert result.created is not None
        assert result.created.product == "Accu-2026-10-06"
        merged_legs = session.scalars(
            select(AccumulatorLeg).where(
                AccumulatorLeg.accumulator_id == result.created.id
            )
        ).all()
        assert len(merged_legs) == 3
        by_fixture = {leg.fixture_id: leg for leg in merged_legs}
        assert by_fixture[fixture_conflict.id].selection == "home"
        assert by_fixture[fixture_conflict.id].source_accumulator_id == conservative.id
        assert by_fixture[fixture_only_balanced.id].source_accumulator_id == balanced.id
        assert {leg.fixture_id for leg in merged_legs} == {
            fixture_a.id,
            fixture_conflict.id,
            fixture_only_balanced.id,
        }

        rerun = ensure_daily_accumulator(session, now=NOW + timedelta(hours=1))
        assert rerun.created is None
        assert rerun.existing is not None
        assert rerun.existing.id == result.created.id
