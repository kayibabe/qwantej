"""GET /daily-candidates — auditable Daily Pick candidate snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Competition, DailyCandidateSnapshot, Fixture, Settlement, Team
from backend.schemas.daily_candidates import DailyCandidateOut, DailyCandidatePage

router = APIRouter(
    prefix="/daily-candidates", tags=["daily-candidates"], dependencies=[RequireApiKey]
)
PRODUCT_DAY_ZONE = ZoneInfo("Africa/Blantyre")


def _score(fixture: Fixture) -> str | None:
    if fixture.home_goals is None or fixture.away_goals is None:
        return None
    return f"{fixture.home_goals}–{fixture.away_goals}"


@router.get("", response_model=DailyCandidatePage)
def list_daily_candidates(
    db: DbDep,
    date: Annotated[date | None, Query(description="Product day in Africa/Blantyre")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DailyCandidatePage:
    product_day = date or datetime.now(UTC).astimezone(PRODUCT_DAY_ZONE).date()
    latest_run = db.scalar(
        select(DailyCandidateSnapshot.run_id)
        .where(DailyCandidateSnapshot.product_day == product_day)
        .order_by(DailyCandidateSnapshot.captured_at_run.desc())
        .limit(1)
    )
    if latest_run is None:
        return DailyCandidatePage(
            product_day=product_day,
            run_id=None,
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    total = int(db.scalar(
        select(func.count()).select_from(DailyCandidateSnapshot).where(
            DailyCandidateSnapshot.run_id == latest_run
        )
    ) or 0)
    home = aliased(Team)
    away = aliased(Team)
    rows = db.execute(
        select(DailyCandidateSnapshot, Fixture, home, away, Competition)
        .join(Fixture, Fixture.id == DailyCandidateSnapshot.fixture_id)
        .join(home, home.id == Fixture.home_team_id)
        .join(away, away.id == Fixture.away_team_id)
        .join(Competition, Competition.id == Fixture.competition_id)
        .where(DailyCandidateSnapshot.run_id == latest_run)
        .order_by(DailyCandidateSnapshot.kickoff_utc, DailyCandidateSnapshot.id)
        .offset(offset)
        .limit(limit)
    ).all()

    prediction_ids = [snapshot.prediction_id for snapshot, *_ in rows]
    superseded = select(Settlement.supersedes_id).where(Settlement.supersedes_id.is_not(None))
    outcomes: dict[object, str] = {}
    if prediction_ids:
        for subject_id, outcome in db.execute(
            select(Settlement.subject_id, Settlement.outcome)
            .where(
                Settlement.subject_type == "prediction",
                Settlement.subject_id.in_(prediction_ids),
                Settlement.id.not_in(superseded),
            )
            .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
        ):
            outcomes.setdefault(subject_id, outcome.value)

    items = [DailyCandidateOut(
        id=snapshot.id,
        run_id=snapshot.run_id,
        product_day=snapshot.product_day,
        captured_at_run=snapshot.captured_at_run,
        prediction_id=snapshot.prediction_id,
        fixture_id=snapshot.fixture_id,
        home_team=home_team.name,
        away_team=away_team.name,
        competition_name=competition.name,
        kickoff_utc=fixture.kickoff_utc,
        market=snapshot.market,
        selection=snapshot.selection,
        model_probability=float(snapshot.model_probability),
        market_probability=float(snapshot.market_probability),
        decimal_odds=float(snapshot.decimal_odds),
        quote_captured_at=snapshot.quote_captured_at,
        dqs=float(snapshot.dqs),
        bookmaker=snapshot.bookmaker,
        candidate_status=snapshot.candidate_status,
        exclusion_reason=snapshot.exclusion_reason,
        selected_product=snapshot.selected_product,
        accumulator_id=snapshot.accumulator_id,
        fixture_status=fixture.status.value,
        score=_score(fixture),
        outcome=outcomes.get(snapshot.prediction_id),
    ) for snapshot, fixture, home_team, away_team, competition in rows]
    return DailyCandidatePage(
        product_day=product_day,
        run_id=latest_run,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
