"""Pydantic response schemas for the /audit endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor: str
    actor_ref: str | None
    action: str
    summary: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    payload: dict | None
    occurred_at: datetime
    created_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int
