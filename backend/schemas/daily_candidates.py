"""API contracts for Daily Pick candidate-pool snapshots."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DailyCandidateOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    product_day: date
    captured_at_run: datetime
    prediction_id: uuid.UUID
    fixture_id: uuid.UUID
    home_team: str | None
    away_team: str | None
    competition_name: str | None
    kickoff_utc: datetime
    market: str
    selection: str
    model_probability: float
    market_probability: float
    decimal_odds: float
    quote_captured_at: datetime
    dqs: float
    bookmaker: str | None
    candidate_status: str
    exclusion_reason: str | None
    selected_product: str | None
    accumulator_id: uuid.UUID | None
    fixture_status: str
    score: str | None
    outcome: str | None


class DailyCandidatePage(BaseModel):
    product_day: date
    run_id: uuid.UUID | None
    items: list[DailyCandidateOut]
    total: int
    limit: int
    offset: int
