from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func, cast, Date, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user_optional
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.calibration_record import CalibrationRecord
from app.models.user import User

router = APIRouter(prefix="/api/model-performance", tags=["model-performance"])


# ── Output schemas ────────────────────────────────────────────────────────────

class OverallStats(BaseModel):
    n: int
    signal_count: int
    settled_count: int
    win_count: int
    win_rate: Optional[float]
    avg_brier_ensemble: Optional[float]
    avg_brier_calibrated: Optional[float]

class ByMarketRow(BaseModel):
    market: str
    n: int
    avg_brier_ensemble: Optional[float]
    avg_brier_calibrated: Optional[float]
    avg_ensemble_prob: Optional[float]
    win_rate: Optional[float]

class ByHorizonRow(BaseModel):
    horizon: str
    n: int
    avg_brier_ensemble: Optional[float]
    avg_ensemble_prob: Optional[float]

class ByEngineRow(BaseModel):
    engine: str
    n_available: int
    avg_brier: Optional[float]

class BrierTrendRow(BaseModel):
    date: str
    n: int
    avg_brier: Optional[float]

class CalibrationRow(BaseModel):
    market: str
    model_version: str
    n_samples: int
    raw_brier: float
    calibrated_brier: float
    brier_improvement: float
    is_active: bool

class ModelPerformanceOut(BaseModel):
    overall: OverallStats
    by_market: list[ByMarketRow]
    by_horizon: list[ByHorizonRow]
    by_engine: list[ByEngineRow]
    brier_trend: list[BrierTrendRow]
    calibration_records: list[CalibrationRow]


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=ModelPerformanceOut)
async def model_performance(
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    signal_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    conditions = []
    if signal_only:
        conditions.append(ForecastSnapshot.signal_type == "SIGNAL")
    if date_from:
        conditions.append(cast(ForecastSnapshot.snapshot_at, Date) >= date_cls.fromisoformat(date_from))
    if date_to:
        conditions.append(cast(ForecastSnapshot.snapshot_at, Date) <= date_cls.fromisoformat(date_to))

    base = select(ForecastSnapshot)
    if conditions:
        base = base.where(and_(*conditions))

    # Settled only — for Brier score queries
    settled_conditions = conditions + [ForecastSnapshot.brier_score.isnot(None)]
    settled_base = select(ForecastSnapshot).where(and_(*settled_conditions))

    # ── Overall stats ─────────────────────────────────────────────────────────
    total_q = await db.execute(
        select(
            func.count().label("n"),
            func.sum(case((ForecastSnapshot.signal_type == "SIGNAL", 1), else_=0)).label("signal_count"),
            func.sum(case((ForecastSnapshot.brier_score.isnot(None), 1), else_=0)).label("settled_count"),
            func.sum(case((ForecastSnapshot.outcome == "WIN", 1), else_=0)).label("win_count"),
            func.avg(ForecastSnapshot.brier_score).label("avg_brier_ensemble"),
        ).select_from(ForecastSnapshot).where(and_(*conditions) if conditions else True)
    )
    row = total_q.one()
    n = row.n or 0
    signal_count = row.signal_count or 0
    settled_count = row.settled_count or 0
    win_count = row.win_count or 0
    avg_brier_ens = round(row.avg_brier_ensemble, 4) if row.avg_brier_ensemble is not None else None
    win_rate = round(win_count / settled_count * 100, 1) if settled_count > 0 else None

    # Calibrated brier average (only rows that have it)
    cal_q = await db.execute(
        select(func.avg(ForecastSnapshot.calibrated_prob)).select_from(ForecastSnapshot)
        .where(and_(*(conditions + [ForecastSnapshot.calibrated_prob.isnot(None)])) if conditions else ForecastSnapshot.calibrated_prob.isnot(None))
    )
    # We can't easily compute calibrated brier here without outcome; use ensemble avg as proxy
    avg_brier_cal = None  # populated by calibration_records below

    overall = OverallStats(
        n=n,
        signal_count=signal_count,
        settled_count=settled_count,
        win_count=win_count,
        win_rate=win_rate,
        avg_brier_ensemble=avg_brier_ens,
        avg_brier_calibrated=avg_brier_cal,
    )

    # ── By market ─────────────────────────────────────────────────────────────
    mkt_q = await db.execute(
        select(
            ForecastSnapshot.market,
            func.count().label("n"),
            func.avg(ForecastSnapshot.brier_score).label("avg_brier"),
            func.avg(ForecastSnapshot.ensemble_prob).label("avg_prob"),
            func.sum(case((ForecastSnapshot.outcome == "WIN", 1), else_=0)).label("wins"),
            func.sum(case((ForecastSnapshot.brier_score.isnot(None), 1), else_=0)).label("settled"),
        )
        .select_from(ForecastSnapshot)
        .where(and_(*conditions) if conditions else True)
        .group_by(ForecastSnapshot.market)
        .order_by(func.avg(ForecastSnapshot.brier_score))
    )
    by_market = []
    for r in mkt_q.all():
        wr = round(r.wins / r.settled * 100, 1) if r.settled else None
        by_market.append(ByMarketRow(
            market=r.market,
            n=r.n,
            avg_brier_ensemble=round(r.avg_brier, 4) if r.avg_brier is not None else None,
            avg_brier_calibrated=None,
            avg_ensemble_prob=round(r.avg_prob * 100, 1) if r.avg_prob is not None else None,
            win_rate=wr,
        ))

    # ── By horizon ────────────────────────────────────────────────────────────
    hor_q = await db.execute(
        select(
            ForecastSnapshot.horizon,
            func.count().label("n"),
            func.avg(ForecastSnapshot.brier_score).label("avg_brier"),
            func.avg(ForecastSnapshot.ensemble_prob).label("avg_prob"),
        )
        .select_from(ForecastSnapshot)
        .where(and_(*conditions) if conditions else True)
        .group_by(ForecastSnapshot.horizon)
        .order_by(func.count().desc())
    )
    by_horizon = [
        ByHorizonRow(
            horizon=r.horizon,
            n=r.n,
            avg_brier_ensemble=round(r.avg_brier, 4) if r.avg_brier is not None else None,
            avg_ensemble_prob=round(r.avg_prob * 100, 1) if r.avg_prob is not None else None,
        )
        for r in hor_q.all()
    ]

    # ── By engine (approximate from non-null columns) ─────────────────────────
    eng_q = await db.execute(
        select(
            func.sum(case((ForecastSnapshot.zinb_prob.isnot(None), 1), else_=0)).label("zinb_n"),
            func.sum(case((ForecastSnapshot.bayesian_prob.isnot(None), 1), else_=0)).label("bay_n"),
            func.sum(case((ForecastSnapshot.elo_prob.isnot(None), 1), else_=0)).label("elo_n"),
            func.count().label("ens_n"),
        )
        .select_from(ForecastSnapshot)
        .where(and_(*conditions) if conditions else True)
    )
    er = eng_q.one()
    by_engine = [
        ByEngineRow(engine="ZINB",     n_available=er.zinb_n or 0, avg_brier=None),
        ByEngineRow(engine="Bayesian", n_available=er.bay_n or 0,  avg_brier=None),
        ByEngineRow(engine="Elo",      n_available=er.elo_n or 0,  avg_brier=None),
        ByEngineRow(engine="Ensemble", n_available=er.ens_n or 0,  avg_brier=avg_brier_ens),
    ]

    # ── Brier trend (daily) ───────────────────────────────────────────────────
    trend_q = await db.execute(
        select(
            cast(ForecastSnapshot.snapshot_at, Date).label("dt"),
            func.count().label("n"),
            func.avg(ForecastSnapshot.brier_score).label("avg_brier"),
        )
        .select_from(ForecastSnapshot)
        .where(and_(*(conditions + [ForecastSnapshot.brier_score.isnot(None)])) if conditions else ForecastSnapshot.brier_score.isnot(None))
        .group_by(cast(ForecastSnapshot.snapshot_at, Date))
        .order_by(cast(ForecastSnapshot.snapshot_at, Date))
    )
    brier_trend = [
        BrierTrendRow(
            date=str(r.dt),
            n=r.n,
            avg_brier=round(r.avg_brier, 4) if r.avg_brier is not None else None,
        )
        for r in trend_q.all()
    ]

    # ── Calibration records ───────────────────────────────────────────────────
    cal_recs = await db.execute(
        select(CalibrationRecord).order_by(CalibrationRecord.computed_at.desc())
    )
    calibration_records = [
        CalibrationRow(
            market=r.market,
            model_version=r.model_version,
            n_samples=r.n_samples,
            raw_brier=r.raw_brier,
            calibrated_brier=r.calibrated_brier,
            brier_improvement=r.brier_improvement,
            is_active=r.is_active,
        )
        for r in cal_recs.scalars().all()
    ]

    return ModelPerformanceOut(
        overall=overall,
        by_market=by_market,
        by_horizon=by_horizon,
        by_engine=by_engine,
        brier_trend=brier_trend,
        calibration_records=calibration_records,
    )
