from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user_optional
from app.models.historical_fixture import HistoricalFixture
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.data_source_experiment import DataSourceExperiment
from app.models.user import User

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


# ── Output schemas ────────────────────────────────────────────────────────────

class LeagueCoverageRow(BaseModel):
    league: str
    country: str
    seasons: list[int]
    fixture_count: int
    with_goals: int
    with_odds: int
    with_shots: int
    with_xg: int
    completeness_pct: float
    calibration_snapshot_count: int


class SourceBreakdownRow(BaseModel):
    source: str
    fixture_count: int
    with_xg: int


class CoverageOut(BaseModel):
    total_fixtures: int
    total_leagues: int
    total_seasons: int
    leagues: list[LeagueCoverageRow]
    by_source: list[SourceBreakdownRow]


class ExperimentOut(BaseModel):
    id: int
    source: str
    market: str
    league: Optional[str]
    experiment_start: str
    experiment_end: str
    baseline_brier: float
    baseline_n: int
    source_brier: float
    source_n: int
    brier_improvement: float
    p_value: Optional[float]
    accepted: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


class SourceSummary(BaseModel):
    source: str
    experiment_count: int
    accepted_count: int
    latest_brier_improvement: Optional[float]
    experiments: list[ExperimentOut]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/coverage", response_model=CoverageOut)
async def data_source_coverage(
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Data warehouse coverage: leagues, seasons, field completeness."""

    # Per-league aggregates
    league_q = await db.execute(
        select(
            HistoricalFixture.league,
            HistoricalFixture.country,
            func.count().label("fixture_count"),
            func.sum(case((
                and_(
                    HistoricalFixture.home_goals.isnot(None),
                    HistoricalFixture.away_goals.isnot(None),
                ), 1), else_=0)).label("with_goals"),
            func.sum(case((HistoricalFixture.odds_over_2_5.isnot(None), 1), else_=0)).label("with_odds"),
            func.sum(case((HistoricalFixture.home_shots.isnot(None), 1), else_=0)).label("with_shots"),
            func.sum(case((HistoricalFixture.home_xg.isnot(None), 1), else_=0)).label("with_xg"),
        )
        .group_by(HistoricalFixture.league, HistoricalFixture.country)
        .order_by(func.count().desc())
    )

    # Per-league seasons list
    seasons_q = await db.execute(
        select(
            HistoricalFixture.league,
            HistoricalFixture.country,
            HistoricalFixture.season,
        ).distinct().order_by(
            HistoricalFixture.league,
            HistoricalFixture.season,
        )
    )
    seasons_map: dict[tuple[str, str], list[int]] = {}
    for row in seasons_q.all():
        seasons_map.setdefault((row.league, row.country), []).append(row.season)

    # ForecastSnapshot count per league (from historical_fixture join)
    snap_q = await db.execute(
        select(
            HistoricalFixture.league,
            HistoricalFixture.country,
            func.count(ForecastSnapshot.id).label("snap_count"),
        )
        .join(ForecastSnapshot, ForecastSnapshot.historical_fixture_id == HistoricalFixture.id)
        .group_by(HistoricalFixture.league, HistoricalFixture.country)
    )
    snap_map: dict[tuple[str, str], int] = {
        (r.league, r.country): r.snap_count for r in snap_q.all()
    }

    leagues: list[LeagueCoverageRow] = []
    total_fixtures = 0
    for r in league_q.all():
        key = (r.league, r.country)
        n = r.fixture_count
        total_fixtures += n
        completeness_numerator = r.with_goals + r.with_odds + r.with_shots
        completeness_denom = n * 3
        completeness = round(completeness_numerator / completeness_denom * 100, 1) if completeness_denom else 0.0
        leagues.append(LeagueCoverageRow(
            league=r.league,
            country=r.country,
            seasons=seasons_map.get(key, []),
            fixture_count=n,
            with_goals=r.with_goals,
            with_odds=r.with_odds,
            with_shots=r.with_shots,
            with_xg=r.with_xg,
            completeness_pct=completeness,
            calibration_snapshot_count=snap_map.get(key, 0),
        ))

    # By source breakdown
    source_q = await db.execute(
        select(
            HistoricalFixture.source,
            func.count().label("fixture_count"),
            func.sum(case((HistoricalFixture.home_xg.isnot(None), 1), else_=0)).label("with_xg"),
        )
        .group_by(HistoricalFixture.source)
        .order_by(func.count().desc())
    )
    by_source = [
        SourceBreakdownRow(source=r.source, fixture_count=r.fixture_count, with_xg=r.with_xg)
        for r in source_q.all()
    ]

    total_seasons = sum(len(v) for v in seasons_map.values())
    return CoverageOut(
        total_fixtures=total_fixtures,
        total_leagues=len(leagues),
        total_seasons=total_seasons,
        leagues=leagues,
        by_source=by_source,
    )


@router.get("", response_model=list[SourceSummary])
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """DataSourceExperiment results grouped by source (A/B tests against baseline)."""
    result = await db.execute(
        select(DataSourceExperiment).order_by(
            DataSourceExperiment.source,
            DataSourceExperiment.created_at.desc(),
        )
    )
    all_exps = result.scalars().all()

    groups: dict[str, list[DataSourceExperiment]] = {}
    for exp in all_exps:
        groups.setdefault(exp.source, []).append(exp)

    summaries: list[SourceSummary] = []
    for source, exps in groups.items():
        accepted = [e for e in exps if e.accepted]
        summaries.append(SourceSummary(
            source=source,
            experiment_count=len(exps),
            accepted_count=len(accepted),
            latest_brier_improvement=exps[0].brier_improvement if exps else None,
            experiments=[
                ExperimentOut(
                    id=e.id,
                    source=e.source,
                    market=e.market,
                    league=e.league,
                    experiment_start=str(e.experiment_start),
                    experiment_end=str(e.experiment_end),
                    baseline_brier=e.baseline_brier,
                    baseline_n=e.baseline_n,
                    source_brier=e.source_brier,
                    source_n=e.source_n,
                    brier_improvement=e.brier_improvement,
                    p_value=e.p_value,
                    accepted=e.accepted,
                    notes=e.notes,
                )
                for e in exps
            ],
        ))

    summaries.sort(key=lambda s: (-s.accepted_count, s.source))
    return summaries
