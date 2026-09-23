"""GET /accumulators — paginated accumulator ticket archive with legs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import (
    Accumulator,
    AccumulatorLeg,
    FixtureStatus,
    Settlement,
    SettlementOutcome,
    StatsSnapshot,
)
from backend.models.fixtures import Fixture
from backend.schemas.accumulators import AccumulatorLegOut, AccumulatorOut, AccumulatorPage

router = APIRouter(prefix="/accumulators", tags=["accumulators"], dependencies=[RequireApiKey])

_MAX_LIMIT = 100
_FIXTURE_SOURCE = "api-football:fixtures"


def _leg_display_data(
    db: DbDep, rows: list[Accumulator]
) -> dict[uuid.UUID, dict[str, object]]:
    legs = [leg for row in rows for leg in row.legs]
    if not legs:
        return {}
    fixture_ids = {leg.fixture_id for leg in legs}
    prediction_ids = {leg.prediction_id for leg in legs}
    snapshots = db.scalars(
        select(StatsSnapshot)
        .where(
            StatsSnapshot.fixture_id.in_(fixture_ids),
            StatsSnapshot.source == _FIXTURE_SOURCE,
        )
        .order_by(StatsSnapshot.as_of_timestamp.desc(), StatsSnapshot.id.desc())
    ).all()
    latest_snapshot: dict[uuid.UUID, StatsSnapshot] = {}
    for snap in snapshots:
        if snap.fixture_id is not None:
            latest_snapshot.setdefault(snap.fixture_id, snap)

    settlements = db.scalars(
        select(Settlement)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.subject_id.in_(prediction_ids),
        )
        .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
    ).all()
    latest_settlement: dict[uuid.UUID, Settlement] = {}
    for settlement in settlements:
        latest_settlement.setdefault(settlement.subject_id, settlement)

    result: dict[uuid.UUID, dict[str, object]] = {}
    for leg in legs:
        fixture = leg.fixture
        fixture_status = fixture.status.value if fixture else "scheduled"
        fixture_snapshot = latest_snapshot.get(leg.fixture_id)
        record = (fixture_snapshot.payload.get("record", {}) if fixture_snapshot else {})
        provider_status = (
            record.get("fixture", {}).get("status", {})
            if isinstance(record, dict)
            else {}
        )
        phase = provider_status.get("long") if isinstance(provider_status, dict) else None
        short_phase = provider_status.get("short") if isinstance(provider_status, dict) else None
        elapsed = provider_status.get("elapsed") if isinstance(provider_status, dict) else None
        if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0:
            elapsed = None
        outcome = latest_settlement.get(leg.prediction_id)
        outcome_value = outcome.outcome.value if outcome else None
        latest_status = short_phase.upper() if isinstance(short_phase, str) else None
        provider_result_is_stale = (
            fixture is not None
            and fixture_status == FixtureStatus.SCHEDULED.value
            and fixture_snapshot is not None
            and latest_status in {"NS", "TBD"}
            and _snapshot_is_overdue(fixture_snapshot, fixture.kickoff_utc)
        )

        if outcome_value == SettlementOutcome.WIN.value:
            match_state = "won"
        elif outcome_value == SettlementOutcome.LOSS.value:
            match_state = "lost"
        elif outcome_value in {SettlementOutcome.VOID.value, SettlementOutcome.PUSH.value}:
            match_state = "void"
        elif fixture_status == FixtureStatus.LIVE.value:
            match_state = "live"
        elif provider_result_is_stale:
            match_state = "awaiting_result"
        else:
            match_state = "pending"

        goals = record.get("goals", {}) if isinstance(record, dict) else {}
        home_goals = fixture.home_goals if fixture else None
        away_goals = fixture.away_goals if fixture else None
        if home_goals is None and isinstance(goals, dict):
            raw_home = goals.get("home")
            home_goals = (
                raw_home
                if isinstance(raw_home, int) and not isinstance(raw_home, bool)
                else None
            )
        if away_goals is None and isinstance(goals, dict):
            raw_away = goals.get("away")
            away_goals = (
                raw_away
                if isinstance(raw_away, int) and not isinstance(raw_away, bool)
                else None
            )
        score = (
            f"{home_goals}–{away_goals}"
            if home_goals is not None and away_goals is not None
            else None
        )
        if short_phase in {"1H", "HT", "2H", "ET", "BT"}:
            live_phase = {
                "1H": "1st half",
                "HT": "Half-time",
                "2H": "2nd half",
                "ET": "Extra time",
                "BT": "Extra-time break",
            }[short_phase]
        elif fixture_status == FixtureStatus.LIVE.value and isinstance(phase, str):
            live_phase = phase
        else:
            live_phase = None
        result[leg.id] = {
            "match_state": match_state,
            "fixture_status": fixture_status,
            "score": score,
            "live_phase": live_phase,
            "elapsed_minutes": elapsed,
            "settlement_outcome": outcome_value,
        }
    return result


def _snapshot_is_overdue(snapshot: StatsSnapshot, kickoff_utc: datetime) -> bool:
    """Whether a scheduled/not-started snapshot is at least three hours stale."""
    snapshot_at = snapshot.as_of_timestamp
    kickoff = kickoff_utc
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UTC)
    return snapshot_at.astimezone(UTC) - kickoff.astimezone(UTC) >= timedelta(hours=3)


@router.get("", response_model=AccumulatorPage)
def list_accumulators(
    db: DbDep,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccumulatorPage:
    """Return a page of accumulator tickets (newest published first) with legs.

    Optional filter: ``status`` — ``pending``, ``locked``, ``settled``, ``void``
    """
    base_stmt = select(Accumulator)
    if status is not None:
        base_stmt = base_stmt.where(Accumulator.status == status)

    total: int = db.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    _leg_load = selectinload(Accumulator.legs).options(
        selectinload(AccumulatorLeg.fixture).options(
            selectinload(Fixture.home_team),
            selectinload(Fixture.away_team),
            selectinload(Fixture.competition),
        )
    )
    rows = list(
        db.scalars(
            base_stmt.options(_leg_load)
            .order_by(Accumulator.published_at.desc(), Accumulator.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    # Sort legs by leg_index in Python — selectinload does not guarantee order.
    for row in rows:
        row.legs.sort(key=lambda leg: leg.leg_index)
    display_data = _leg_display_data(db, rows)
    return AccumulatorPage(
        items=[_serialize_accumulator(r, display_data) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{accumulator_id}", response_model=AccumulatorOut)
def get_accumulator(
    accumulator_id: uuid.UUID,
    db: DbDep,
) -> AccumulatorOut:
    """Return a single accumulator ticket with its legs."""
    _leg_load = selectinload(Accumulator.legs).options(
        selectinload(AccumulatorLeg.fixture).options(
            selectinload(Fixture.home_team),
            selectinload(Fixture.away_team),
            selectinload(Fixture.competition),
        )
    )
    row = db.scalar(
        select(Accumulator)
        .where(Accumulator.id == accumulator_id)
        .options(_leg_load)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Accumulator not found")
    row.legs.sort(key=lambda leg: leg.leg_index)
    display_data = _leg_display_data(db, [row])
    return _serialize_accumulator(row, display_data)


def _serialize_accumulator(
    row: Accumulator, display_data: dict[uuid.UUID, dict[str, object]]
) -> AccumulatorOut:
    archived = AccumulatorOut.model_validate(row)
    return AccumulatorOut(
        **{
            **archived.model_dump(exclude={"legs"}),
            "legs": [
                {
                    **AccumulatorLegOut.model_validate(leg, from_attributes=True).model_dump(),
                    **display_data[leg.id],
                }
                for leg in row.legs
            ],
        }
    )
