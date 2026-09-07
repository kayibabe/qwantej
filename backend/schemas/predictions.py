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


class PredictionPage(BaseModel):
    items: list[PredictionOut]
    total: int
    limit: int
    offset: int
