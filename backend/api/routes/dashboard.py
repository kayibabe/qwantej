"""Dashboard status endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import func, select

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Accumulator, Competition, Fixture, FixtureStatus, OddsQuote
from backend.schemas.dashboard import TodayStatusOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[RequireApiKey])
PRODUCT_DAY_ZONE = ZoneInfo("Africa/Blantyre")
PRICE_FRESHNESS_LIMIT = timedelta(hours=2)


@router.get("/today", response_model=TodayStatusOut)
def today_status(db: DbDep) -> TodayStatusOut:
    """Return an honest, data-backed summary for the user's current day."""
    now = datetime.now(UTC)
    local_now = now.astimezone(PRODUCT_DAY_ZONE)
    day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = day_start_local.astimezone(UTC)
    day_end = (day_start_local + timedelta(days=1)).astimezone(UTC)

    leagues = list(
        db.scalars(
            select(Competition.name)
            .where(Competition.validated.is_(True))
            .order_by(Competition.name)
        )
    )
    upcoming = int(
        db.scalar(
            select(func.count())
            .select_from(Fixture)
            .join(Competition, Fixture.competition_id == Competition.id)
            .where(
                Competition.validated.is_(True),
                Fixture.status == FixtureStatus.SCHEDULED,
                Fixture.kickoff_utc >= day_start,
                Fixture.kickoff_utc < day_end,
            )
        )
        or 0
    )
    tickets = int(
        db.scalar(
            select(func.count())
            .select_from(Accumulator)
            .where(
                Accumulator.paper_only.is_(True),
                Accumulator.published_at >= day_start,
                Accumulator.published_at < day_end,
            )
        )
        or 0
    )
    # Freshness is scoped to today's validated fixtures.  A quote from an old
    # finished match must not make a current day with no usable prices look
    # checked.
    freshness = db.scalar(
        select(func.max(OddsQuote.captured_at))
        .join(Fixture, OddsQuote.fixture_id == Fixture.id)
        .join(Competition, Fixture.competition_id == Competition.id)
        .where(
            Competition.validated.is_(True),
            Fixture.kickoff_utc >= day_start,
            Fixture.kickoff_utc < day_end,
        )
    )
    if freshness is not None:
        # SQLite drops timezone metadata while PostgreSQL preserves it.
        # Treat persisted quote timestamps as UTC in either backend.
        freshness = (
            freshness.astimezone(UTC)
            if freshness.tzinfo is not None and freshness.utcoffset() is not None
            else freshness.replace(tzinfo=UTC)
        )
    next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    freshness_age = now - freshness if freshness is not None else None
    if tickets:
        status, label, detail = (
            "qualified",
            "Ticket available",
            f"{tickets} paper ticket{'s' if tickets != 1 else ''} qualified today.",
        )
    elif upcoming and freshness is None:
        status, label, detail = (
            "collecting",
            "Collecting prices",
            f"{upcoming} scheduled fixture{'s' if upcoming != 1 else ''} found; "
            "waiting for a usable price observation before qualification.",
        )
    elif upcoming and freshness_age is not None and freshness_age > PRICE_FRESHNESS_LIMIT:
        status, label, detail = (
            "stale",
            "Prices need refreshing",
            f"The latest price observation is older than "
            f"{int(PRICE_FRESHNESS_LIMIT.total_seconds() // 3600)} "
            "hours; no ticket is presented until current prices are available.",
        )
    elif upcoming:
        status, label, detail = (
            "no_qualifying_combination",
            "No qualifying ticket yet",
            f"{upcoming} scheduled fixture{'s' if upcoming != 1 else ''} checked; "
            "none passed the current gates.",
        )
    elif freshness is None:
        status, label, detail = (
            "collecting",
            "Collecting data",
            "No current fixture or price observations are available yet.",
        )
    else:
        status, label, detail = (
            "no_upcoming_data",
            "No ticket found today",
            "No validated-league fixtures are scheduled for today.",
        )

    return TodayStatusOut(
        status=status,
        label=label,
        detail=detail,
        date=local_now.date().isoformat(),
        data_freshness_utc=freshness,
        checked_leagues=leagues,
        next_run_utc=next_run,
        tickets_available=tickets,
    )
