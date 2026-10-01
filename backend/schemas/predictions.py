"""Pydantic response schemas for the /predictions endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fixture_id: uuid.UUID
    prediction_timestamp: datetime
    decision_as_of: datetime
    market: str
    selection: str
    line: float | None
    conservative_probability: float | None
    executable_odds: float | None
    edge_pp: float | None
    expected_value: float | None
    qss: float | None
    dqs: float | None
    created_at: datetime
    bookmaker: str | None = None
    # Match context, from the prediction's fixture.
    home_team: str | None = None
    away_team: str | None = None
    kickoff_utc: datetime | None = None
    competition_name: str | None = None
    # Effective settlement outcome (win/loss/void/push) once settled.
    outcome: str | None = None
    # Audit context displayed by the Forecasts archive. These are decision-time
    # fields, not a claim about the model's current lifecycle state.
    research_mode: bool = False
    gate_passed: bool = True
    model_version_label: str | None = None
    # An unset result after kickoff needs investigation; it is not an upcoming
    # forecast merely because the fixture status has not yet been refreshed.
    settlement_overdue: bool = False


class PredictionPage(BaseModel):
    items: list[PredictionOut]
    total: int
    limit: int
    offset: int


class PredictionMarketSummary(BaseModel):
    market: str
    total: int
    won: int
    lost: int
    void: int
    push: int
    unsettled: int
