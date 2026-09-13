"""Pydantic response schemas for the /accumulators endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccumulatorLegOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    leg_index: int
    prediction_id: uuid.UUID
    fixture_id: uuid.UUID
    league_id: str
    market_family: str
    selection: str
    decimal_odds: float
    conservative_probability: float
    edge: float
    qss: float
    bookmaker: str | None = None
    # Display fields populated from the eagerly-loaded fixture relationship.
    home_team: str | None = None
    away_team: str | None = None
    kickoff_utc: datetime | None = None
    competition_name: str | None = None
    # Price-freshness timestamp written at leg creation time.
    quote_captured_at: datetime | None = None


class AccumulatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product: str
    status: str
    combined_odds: float
    conservative_joint_probability: float
    stressed_joint_probability: float
    objective_score: float
    published_at: datetime
    locked_at: datetime | None
    stake: float | None
    risk_policy_version: str | None
    legs: list[AccumulatorLegOut]
    created_at: datetime


class AccumulatorPage(BaseModel):
    items: list[AccumulatorOut]
    total: int
    limit: int
    offset: int
