"""Pydantic response schemas for the /models endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    kind: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    data_as_of: datetime | None
    data_snapshot_ref: str | None
    code_commit: str | None
    parameters: dict | None
    metrics: dict | None
    log_uri: str | None
    created_at: datetime
    updated_at: datetime


class ModelRegistryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family: str
    name: str
    version: str
    status: str
    training_window_start: datetime | None
    training_window_end: datetime | None
    code_commit: str | None
    artefact_hash: str | None
    artefact_uri: str | None
    hyperparameters: dict | None
    description: str | None
    promoted_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelRegistryDetailOut(ModelRegistryOut):
    """Model registry entry with its full run history."""

    runs: list[ModelRunOut]


class ModelRegistryPage(BaseModel):
    items: list[ModelRegistryOut]
    total: int
    limit: int
    offset: int


class ModelRunPage(BaseModel):
    items: list[ModelRunOut]
    total: int
    limit: int
    offset: int
