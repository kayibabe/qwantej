"""Pydantic response schemas for the /performance endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CalibrationBinOut(BaseModel):
    """Serialisable form of qwantej.performance.drift.CalibrationBin."""

    model_config = ConfigDict(from_attributes=True)

    predicted_probability: float
    observed_frequency: float
    count: int


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
    max_drawdown: float | None  # stake units (peak-to-trough of cumulative P/L), not a fraction
    volatility: float | None

    # Reliability diagram
    calibration_bins: list[CalibrationBinOut] | None = None

    # "real" (recorded stakes), "flat_unit" (one unit per priced bet) or None
    # when nothing priced has settled.  Tells the UI which unit P/L is in.
    stake_basis: str | None = None

    # Subjects whose matches have kicked off but which have no settlement yet
    # (open tickets / unsettled selections).  Only set on /performance/report.
    n_awaiting: int | None = None


class PerformanceSegmentsOut(BaseModel):
    """KPI reports keyed by segment value."""

    by: str
    segments: dict[str, KPIReportOut]


class AccumulatorProductResultOut(BaseModel):
    """Ticket result counts for one product within one period."""

    product: str
    daily_pick: bool
    won: int
    lost: int
    void: int
    pending: int
    total: int
    win_rate: float | None


class AccumulatorPeriodResultOut(BaseModel):
    """All products' ticket results for one UTC calendar period."""

    period: str
    products: list[AccumulatorProductResultOut]


class AccumulatorResultsOut(BaseModel):
    """Accumulator ticket results grouped by year, month or day (UTC)."""

    granularity: str
    periods: list[AccumulatorPeriodResultOut]
    total_periods: int
