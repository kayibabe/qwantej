"""Pydantic response schemas for the /performance endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class KPIReportOut(BaseModel):
    """Serialisable form of qwantej.performance.kpi.KPIReport."""

    # Counts
    n_total: int
    n_settled: int
    n_wins: int
    n_losses: int
    n_voids: int
    n_pushes: int

    # Betting
    hit_rate: float | None
    average_odds: float | None
    break_even_hit_rate: float | None

    # Predictive
    brier_score: float | None
    brier_skill_score: float | None
    log_loss: float | None
    ece: float | None
    calibration_slope: float | None
    calibration_intercept: float | None

    # Market quality
    mean_clv: float | None
    n_clv: int

    # Financial
    roi: float | None
    total_stake: float | None
    total_profit: float | None

    # Risk
    max_drawdown: float | None
    volatility: float | None


class PerformanceSegmentsOut(BaseModel):
    """KPI reports keyed by segment value."""

    by: str
    segments: dict[str, KPIReportOut]
