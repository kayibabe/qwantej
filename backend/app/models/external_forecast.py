"""
external_forecast.py — Predictions scraped from external benchmark sources.

Stores pre-match predictions from Forebet, BetMines, SoccerAiTips, SoccerOracle, etc.
After match settlement, Brier scores are computed and stored here so the Data Source
Performance dashboard can rank sources by market-specific accuracy.

This is the core of Layer B (External Benchmark Layer) in the Phase 1 architecture.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExternalForecast(Base):
    __tablename__ = "external_forecasts"
    __table_args__ = (
        UniqueConstraint("source", "home_team", "away_team", "match_date", name="uq_external_forecast"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source identifier: "forebet" | "betmines" | "socceraitips" | "socceroracle" | "nerdy_tips"
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Match identification — used for result lookup and fixture matching
    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)
    league: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Resolved fixture ID (set after matching against our fixtures table)
    fixture_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Predicted probabilities ──────────────────────────────────────────────
    # 1X2
    home_win_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    draw_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    away_win_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Goals Over/Under
    over_15_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    over_25_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    under_25_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    over_35_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    under_35_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # BTTS
    btts_yes_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    btts_no_prob: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Predicted score (source's score prediction, not a probability)
    pred_home_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pred_away_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Raw confidence label from source (e.g. "High", "Medium", "Low" or numeric)
    confidence_label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ── Actual outcome (filled after settlement) ──────────────────────────────
    actual_home_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_away_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Brier scores per market (filled at settlement) ─────────────────────────
    # Brier score = (prob - outcome)^2 per prediction. Lower = better.
    brier_1x2_home: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_1x2_draw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_1x2_away: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_o15: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_o25: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_u25: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brier_btts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
