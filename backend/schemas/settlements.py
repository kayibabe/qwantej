"""Pydantic response schemas for the /settlements endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    outcome: str
    settled_at: datetime
    result_source: str | None
    taken_odds: float | None
    closing_odds: float | None
    clv: float | None
    taken_probability: float | None
    brier_contribution: float | None
    calibration_bin: str | None
    supersedes_id: uuid.UUID | None
    closing_quote_id: uuid.UUID | None
    created_at: datetime


class SettlementSummary(BaseModel):
    """Aggregate performance KPIs over effective (non-superseded) settlements."""

    n_settled: int
    n_wins: int
    n_losses: int
    n_voids: int
    # None when no win/loss rows exist.
    win_rate: float | None
    # None when no CLV data exists.
    avg_clv: float | None
    # None when no Brier contribution data exists.
    avg_brier: float | None


class SettlementPage(BaseModel):
    items: list[SettlementOut]
    total: int
    limit: int
    offset: int
