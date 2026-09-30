"""Append-only snapshots of the Daily Pick candidate pool."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class DailyCandidateSnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    """One candidate observed by one Daily Pick build run.

    The row is an audit snapshot, not a mutable view of current odds.  New
    scheduler runs append new rows; historical candidate pools are preserved.
    """

    __tablename__ = "daily_candidate_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "prediction_id", name="uq_daily_candidate_run_prediction"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    product_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    captured_at_run: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("predictions.id"), nullable=False, index=True)
    fixture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fixtures.id"), nullable=False, index=True)
    league_id: Mapped[str] = mapped_column(String(40), nullable=False)
    market: Mapped[str] = mapped_column(String(40), nullable=False)
    selection: Mapped[str] = mapped_column(String(80), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    model_probability: Mapped[float] = mapped_column(Numeric(7, 6), nullable=False)
    market_probability: Mapped[float] = mapped_column(Numeric(7, 6), nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    quote_captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dqs: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    bookmaker: Mapped[str | None] = mapped_column(String(80))
    candidate_status: Mapped[str] = mapped_column(String(32), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(120))
    selected_product: Mapped[str | None] = mapped_column(String(20))
    accumulator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accumulators.id"))
