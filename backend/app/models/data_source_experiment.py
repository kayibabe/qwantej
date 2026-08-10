from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataSourceExperiment(Base):
    """
    A/B Brier-score comparison for a data source contribution.

    For each (source, market, optional league) combination, this table records
    whether adding that source's data improved Brier score vs. the baseline.
    Only accepted sources flow into the ensemble weights.
    """
    __tablename__ = "data_source_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # "football_data_co_uk" | "statsbomb" | "openfootball" | "api_football"
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # Market key matching config.MARKETS (e.g. "Over 2.5")
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    # None = all leagues; set to restrict comparison to one league
    league: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    experiment_start: Mapped[date] = mapped_column(Date, nullable=False)
    experiment_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Baseline: Qwantej ensemble without this source's features
    baseline_brier: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_n: Mapped[int] = mapped_column(Integer, nullable=False)

    # With source: ensemble retrained / enriched with this source's features
    source_brier: Mapped[float] = mapped_column(Float, nullable=False)
    source_n: Mapped[int] = mapped_column(Integer, nullable=False)

    # baseline_brier - source_brier (positive = improvement, lower Brier = better)
    brier_improvement: Mapped[float] = mapped_column(Float, nullable=False)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # True when improvement is statistically meaningful and the source is accepted
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Data Value Score (0-1) ────────────────────────────────────────────────
    # Composite score: Accuracy 30% + Calibration 20% + ROI 20% +
    #                  Coverage 15% + Timeliness 10% + Cost 5%
    # Updated by compute_data_value_scores() in data_source_service.py.
    accuracy_score:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calibration_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roi_score:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coverage_score:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timeliness_score:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_score:        Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_value_score:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
