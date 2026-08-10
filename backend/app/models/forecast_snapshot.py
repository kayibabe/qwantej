from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ForecastSnapshot(Base):
    """
    Complete model-state snapshot for one fixture × market × point-in-time.

    Every time the ensemble runs for a fixture it writes one row per market.
    Multi-snapshot per fixture: D-7, D-3, D-1, D-12h, D-6h, D-3h, D-1h, live.
    After settlement, outcome + brier_score are filled in.
    """
    __tablename__ = "forecast_snapshots"
    __table_args__ = (
        Index("ix_forecast_snapshots_fixture_market", "fixture_id", "market"),
        Index("ix_forecast_snapshots_hist_market", "historical_fixture_id", "market"),
        Index("ix_forecast_snapshots_snapshot_at", "snapshot_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Exactly one of these should be set (live API-Football vs. backfill).
    fixture_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fixtures.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    historical_fixture_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("historical_fixtures.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # When the snapshot was captured
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # How far before kickoff: "D-7" | "D-3" | "D-1" | "D-12h" | "D-6h" | "D-3h" | "D-1h" | "live" | "backfill"
    horizon: Mapped[str] = mapped_column(String(20), nullable=False)

    # Market key matching MARKETS dict in config.py (e.g. "Over 2.5", "X2 (Draw or Away)")
    market: Mapped[str] = mapped_column(String(80), nullable=False)

    # --- Individual model probabilities (None if model not run / not applicable)
    zinb_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bayesian_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elo_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    xgb_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Weighted combination of available models
    ensemble_prob: Mapped[float] = mapped_column(Float, nullable=False)
    # Post-calibration (isotonic regression) — populated by calibration.py
    calibrated_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Signal decision
    # "SIGNAL" when value_edge > threshold; "NO_SIGNAL" otherwise.
    # NO_SIGNAL rows are still archived — absence-of-signal must be measurable.
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False, default="NO_SIGNAL")
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    data_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Odds at snapshot time
    fair_odds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 1 / ensemble_prob
    market_odds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # (market_odds * ensemble_prob) - 1; positive = value bet
    value_edge: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_value_bet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Raw model inputs (for post-hoc analysis and debugging)
    lambda_home: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lambda_away: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elo_home: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elo_away: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    form_home: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    form_away: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- Outcome (populated by settlement.py after the match)
    # "WIN" | "LOSS" | "VOID" | "PUSH" | None (pending)
    outcome: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    actual_home_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_away_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # (ensemble_prob - outcome_binary)^2 — Brier score component
    brier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Semver string of the ensemble engine that produced this row
    model_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0.0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
