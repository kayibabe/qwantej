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
    total_wins: int
    total_losses: int
    avg_brier: Optional[float]
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

    # Filter to fixtures playing on the requested date — Fixture.event_date is
    # already a Date column so no cast needed. Inner join excludes backfill-only
    # rows (historical_fixture_id set, fixture_id NULL) from today's signals,
    # which is correct: today's signals come from live fixtures only.
    stmt = stmt.join(
        Fixture,
        Fixture.id == ForecastSnapshot.fixture_id,
    ).where(
        Fixture.event_date == target_date
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
    date_from: Optional[str] = Query(default=None, description="Match date from (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="Match date to (YYYY-MM-DD)"),
    market: Optional[str] = Query(default=None),
    league: Optional[str] = Query(default=None),
    outcome: Optional[str] = Query(default=None, description="WIN | LOSS | VOID | PUSH"),
    confidence: Optional[str] = Query(default=None, description="High | Medium | Low"),
    signal_only: bool = Query(default=True),
    exclude_backfill: bool = Query(default=False, description="Exclude horizon=backfill rows"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Paginated Forecast Archive — settled ForecastSnapshot rows.

    Date filters apply to settled_at (the match date) not snapshot_at, so
    backfill rows (all snapshot_at = backfill-run date) are correctly matched
    by the actual match date.
    """
    conditions = []
    if signal_only:
        conditions.append(ForecastSnapshot.signal_type == "SIGNAL")
    if market:
        conditions.append(ForecastSnapshot.market == market)
    if outcome:
        conditions.append(ForecastSnapshot.outcome == outcome)
    if confidence:
        conditions.append(ForecastSnapshot.confidence == confidence)
    if exclude_backfill:
        conditions.append(ForecastSnapshot.horizon != "backfill")

    # For date filtering: use settled_at (the match date) when available,
    # otherwise fall back to snapshot_at. Backfill rows have settled_at set
    # to midnight of the match date.
    match_date_col = func.coalesce(
        cast(ForecastSnapshot.settled_at, Date),
        cast(ForecastSnapshot.snapshot_at, Date),
    )
    if date_from:
        conditions.append(match_date_col >= date.fromisoformat(date_from))
    if date_to:
        conditions.append(match_date_col <= date.fromisoformat(date_to))

    # League filter requires a join to the fixture tables — we resolve this
    # post-fetch by enriching and re-filtering; for pagination correctness we
    # do it via a correlated subquery approach only when league is requested.
    # Simpler: join HistoricalFixture when league is filtered (backfill is the
    # main archive source anyway).
    base_stmt = select(ForecastSnapshot)
    if league:
        base_stmt = base_stmt.join(
            HistoricalFixture,
            HistoricalFixture.id == ForecastSnapshot.historical_fixture_id,
            isouter=True,
        ).join(
            Fixture,
            Fixture.id == ForecastSnapshot.fixture_id,
            isouter=True,
        ).where(
            and_(
                *conditions,
                func.coalesce(HistoricalFixture.league, Fixture.league) == league,
            )
        )
    else:
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))

    sq = base_stmt.subquery()
    count_stmt = select(func.count()).select_from(sq)
    total = (await db.execute(count_stmt)).scalar_one()

    agg_stmt = select(
        func.count().filter(sq.c.outcome == "WIN").label("wins"),
        func.count().filter(sq.c.outcome == "LOSS").label("losses"),
        func.avg(sq.c.brier_score).label("avg_brier"),
    ).select_from(sq)
    agg = (await db.execute(agg_stmt)).one()

    stmt = base_stmt.order_by(match_date_col.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = await _enrich_with_fixture(rows, db)

    return ArchivePage(
        items=items,
        total=total,
        total_wins=agg.wins or 0,
        total_losses=agg.losses or 0,
        avg_brier=float(agg.avg_brier) if agg.avg_brier is not None else None,
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
    """All ForecastSnapshot rows for one live fixture, all horizons, all markets."""
    stmt = (
        select(ForecastSnapshot)
        .where(ForecastSnapshot.fixture_id == fixture_id)
        .order_by(ForecastSnapshot.market, ForecastSnapshot.snapshot_at)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return await _enrich_with_fixture(rows, db)


# ── Match Intelligence ────────────────────────────────────────────────────────

class MatchIntelligenceOut(BaseModel):
    historical_fixture_id: int
    home_team: str
    away_team: str
    league: str
    country: str
    match_date: str
    home_goals: Optional[int]
    away_goals: Optional[int]
    result: Optional[str]
    # Model inputs
    lambda_home: Optional[float]
    lambda_away: Optional[float]
    elo_home: Optional[float]
    elo_away: Optional[float]
    # Per-market snapshot (most recent horizon)
    markets: list[ForecastOut]


@router.get("/historical/{hist_fixture_id}", response_model=MatchIntelligenceOut)
async def historical_match_intelligence(
    hist_fixture_id: int,
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Match Intelligence for one historical fixture: all markets + model inputs."""
    hf_result = await db.execute(
        select(HistoricalFixture).where(HistoricalFixture.id == hist_fixture_id)
    )
    hf = hf_result.scalar_one_or_none()
    if hf is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Historical fixture not found")

    snap_result = await db.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.historical_fixture_id == hist_fixture_id)
        .order_by(ForecastSnapshot.market, ForecastSnapshot.snapshot_at.desc())
    )
    all_snaps = snap_result.scalars().all()

    # One row per market: keep most-recent snapshot only
    seen: set[str] = set()
    latest_snaps = []
    for s in all_snaps:
        if s.market not in seen:
            seen.add(s.market)
            latest_snaps.append(s)

    market_outs = await _enrich_with_fixture(latest_snaps, db)

    # Pull model inputs from the first snapshot (same for all markets of this fixture)
    first = all_snaps[0] if all_snaps else None
    return MatchIntelligenceOut(
        historical_fixture_id=hf.id,
        home_team=hf.home_team,
        away_team=hf.away_team,
        league=hf.league,
        country=hf.country,
        match_date=hf.match_date.isoformat(),
        home_goals=hf.home_goals,
        away_goals=hf.away_goals,
        result=hf.result,
        lambda_home=first.lambda_home if first else None,
        lambda_away=first.lambda_away if first else None,
        elo_home=first.elo_home if first else None,
        elo_away=first.elo_away if first else None,
        markets=market_outs,
    )
