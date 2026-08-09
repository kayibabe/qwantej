from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_optional, get_current_user
from app.core.database import get_db
from app.models.fixture import Fixture
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.historical_fixture import HistoricalFixture
from app.models.user import User

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


# ── Output schemas ────────────────────────────────────────────────────────────

class ForecastOut(BaseModel):
    id: int
    fixture_id: Optional[int]
    historical_fixture_id: Optional[int]
    snapshot_at: datetime
    horizon: str
    market: str
    # Match metadata (from joined Fixture or HistoricalFixture)
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    league: Optional[str] = None
    country: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    fixture_status: Optional[str] = None
    # Model probabilities
    zinb_prob: Optional[float]
    bayesian_prob: Optional[float]
    elo_prob: Optional[float]
    ensemble_prob: float
    calibrated_prob: Optional[float]
    # Signal decision
    signal_type: str
    confidence: Optional[str]
    data_quality_score: Optional[float]
    # Odds
    fair_odds: Optional[float]
    market_odds: Optional[float]
    value_edge: Optional[float]
    is_value_bet: bool
    # Model inputs
    lambda_home: Optional[float]
    lambda_away: Optional[float]
    elo_home: Optional[float]
    elo_away: Optional[float]
    # Outcome
    outcome: Optional[str]
    actual_home_goals: Optional[int]
    actual_away_goals: Optional[int]
    brier_score: Optional[float]
    model_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class ArchivePage(BaseModel):
    items: list[ForecastOut]
    total: int
    page: int
    per_page: int
    pages: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today_str() -> str:
    return date.today().isoformat()


async def _enrich_with_fixture(
    rows: list[ForecastSnapshot],
    db: AsyncSession,
) -> list[ForecastOut]:
    """Join ForecastSnapshot rows with Fixture (live) or HistoricalFixture (backfill)."""
    live_ids = [r.fixture_id for r in rows if r.fixture_id is not None]
    hist_ids  = [r.historical_fixture_id for r in rows if r.historical_fixture_id is not None]

    fixtures: dict[int, Fixture] = {}
    if live_ids:
        res = await db.execute(select(Fixture).where(Fixture.id.in_(live_ids)))
        for f in res.scalars().all():
            fixtures[f.id] = f

    hist_fixtures: dict[int, HistoricalFixture] = {}
    if hist_ids:
        res = await db.execute(select(HistoricalFixture).where(HistoricalFixture.id.in_(hist_ids)))
        for hf in res.scalars().all():
            hist_fixtures[hf.id] = hf

    out: list[ForecastOut] = []
    for r in rows:
        f = fixtures.get(r.fixture_id) if r.fixture_id else None
        hf = hist_fixtures.get(r.historical_fixture_id) if r.historical_fixture_id else None

        if f:
            home_team    = f.home_team
            away_team    = f.away_team
            league       = f.league
            country      = f.country
            kickoff_at   = f.kickoff_at
            home_score   = f.home_score
            away_score   = f.away_score
            fixture_status = f.status
        elif hf:
            home_team    = hf.home_team
            away_team    = hf.away_team
            league       = hf.league
            country      = hf.country
            kickoff_at   = datetime.combine(hf.match_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            home_score   = hf.home_goals
            away_score   = hf.away_goals
            fixture_status = "FT" if hf.home_goals is not None else None
        else:
            home_team = away_team = league = country = None
            kickoff_at = home_score = away_score = fixture_status = None

        out.append(ForecastOut(
            id=r.id,
            fixture_id=r.fixture_id,
            historical_fixture_id=r.historical_fixture_id,
            snapshot_at=r.snapshot_at,
            horizon=r.horizon,
            market=r.market,
            home_team=home_team,
            away_team=away_team,
            league=league,
            country=country,
            kickoff_at=kickoff_at,
            home_score=home_score,
            away_score=away_score,
            fixture_status=fixture_status,
            zinb_prob=r.zinb_prob,
            bayesian_prob=r.bayesian_prob,
            elo_prob=r.elo_prob,
            ensemble_prob=r.ensemble_prob,
            calibrated_prob=r.calibrated_prob,
            signal_type=r.signal_type,
            confidence=r.confidence,
            data_quality_score=r.data_quality_score,
            fair_odds=r.fair_odds,
            market_odds=r.market_odds,
            value_edge=r.value_edge,
            is_value_bet=r.is_value_bet,
            lambda_home=r.lambda_home,
            lambda_away=r.lambda_away,
            elo_home=r.elo_home,
            elo_away=r.elo_away,
            outcome=r.outcome,
            actual_home_goals=r.actual_home_goals,
            actual_away_goals=r.actual_away_goals,
            brier_score=r.brier_score,
            model_version=r.model_version,
            created_at=r.created_at,
        ))

    return out


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ForecastOut])
async def list_forecasts(
    date_str: Optional[str] = Query(default=None, alias="date", description="YYYY-MM-DD, defaults to today"),
    market: Optional[str] = Query(default=None),
    signal_only: bool = Query(default=True, description="Only return SIGNAL rows (not NO_SIGNAL)"),
    horizon: Optional[str] = Query(default=None, description="e.g. D-1, D-3h"),
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Today's signals — SIGNAL-type ForecastSnapshot rows for the requested date."""
    target_date = date.fromisoformat(date_str) if date_str else date.today()

    # Build a subquery to get the latest snapshot per (fixture_id, market)
    # so we don't show duplicates when multiple horizons have run.
    latest_sq = (
        select(
            ForecastSnapshot.fixture_id,
            ForecastSnapshot.historical_fixture_id,
            ForecastSnapshot.market,
            func.max(ForecastSnapshot.snapshot_at).label("max_snap"),
        )
        .group_by(
            ForecastSnapshot.fixture_id,
            ForecastSnapshot.historical_fixture_id,
            ForecastSnapshot.market,
        )
        .subquery()
    )

    stmt = (
        select(ForecastSnapshot)
        .join(
            latest_sq,
            and_(
                ForecastSnapshot.fixture_id == latest_sq.c.fixture_id,
                ForecastSnapshot.historical_fixture_id == latest_sq.c.historical_fixture_id,
                ForecastSnapshot.market == latest_sq.c.market,
                ForecastSnapshot.snapshot_at == latest_sq.c.max_snap,
            ),
        )
    )

    # Filter to fixtures playing on the requested date via Fixture.event_date
    stmt = stmt.join(
        Fixture,
        Fixture.id == ForecastSnapshot.fixture_id,
        isouter=True,
    ).where(
        cast(Fixture.event_date, Date) == target_date
    )

    if signal_only:
        stmt = stmt.where(ForecastSnapshot.signal_type == "SIGNAL")
    if market:
        stmt = stmt.where(ForecastSnapshot.market == market)
    if horizon:
        stmt = stmt.where(ForecastSnapshot.horizon == horizon)

    stmt = stmt.order_by(ForecastSnapshot.ensemble_prob.desc())

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return await _enrich_with_fixture(rows, db)


@router.get("/archive", response_model=ArchivePage)
async def archive(
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    market: Optional[str] = Query(default=None),
    outcome: Optional[str] = Query(default=None, description="WIN | LOSS | VOID | PUSH"),
    signal_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Paginated Forecast Archive — all settled ForecastSnapshot rows."""
    conditions = []
    if signal_only:
        conditions.append(ForecastSnapshot.signal_type == "SIGNAL")
    if market:
        conditions.append(ForecastSnapshot.market == market)
    if outcome:
        conditions.append(ForecastSnapshot.outcome == outcome)
    if date_from:
        conditions.append(cast(ForecastSnapshot.snapshot_at, Date) >= date.fromisoformat(date_from))
    if date_to:
        conditions.append(cast(ForecastSnapshot.snapshot_at, Date) <= date.fromisoformat(date_to))

    count_stmt = select(func.count()).select_from(ForecastSnapshot)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(ForecastSnapshot)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(ForecastSnapshot.snapshot_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = await _enrich_with_fixture(rows, db)

    return ArchivePage(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@router.get("/{fixture_id}", response_model=list[ForecastOut])
async def fixture_forecasts(
    fixture_id: int,
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """All ForecastSnapshot rows for one fixture, all horizons, all markets."""
    stmt = (
        select(ForecastSnapshot)
        .where(ForecastSnapshot.fixture_id == fixture_id)
        .order_by(ForecastSnapshot.market, ForecastSnapshot.snapshot_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return await _enrich_with_fixture(rows, db)
