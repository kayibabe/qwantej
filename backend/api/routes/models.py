"""GET /models — model registry and run history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models.registry import ModelRegistry, ModelRun, ModelStatus
from backend.schemas.models import (
    ModelRegistryDetailOut,
    ModelRegistryOut,
    ModelRegistryPage,
    ModelRunOut,
    ModelRunPage,
)

router = APIRouter(prefix="/models", tags=["models"], dependencies=[RequireApiKey])

_MAX_LIMIT = 100


@router.get("", response_model=ModelRegistryPage)
def list_models(
    db: DbDep,
    status: Annotated[str | None, Query()] = None,
    family: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ModelRegistryPage:
    """Return a page of model registry entries, newest first.

    Optional filters:
    - ``status`` — ``development``, ``challenger``, ``champion``, or ``retired``
    - ``family`` — model family (e.g. ``poisson``, ``dixon_coles``, ``ensemble``)
    """
    stmt = select(ModelRegistry)
    if status is not None:
        try:
            stmt = stmt.where(ModelRegistry.status == ModelStatus(status))
        except ValueError:
            valid = [s.value for s in ModelStatus]
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of {valid}",
            ) from None
    if family is not None:
        stmt = stmt.where(ModelRegistry.family == family)

    total: int = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(ModelRegistry.created_at.desc(), ModelRegistry.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return ModelRegistryPage(
        items=[ModelRegistryOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{model_id}", response_model=ModelRegistryDetailOut)
def get_model(
    model_id: uuid.UUID,
    db: DbDep,
) -> ModelRegistryDetailOut:
    """Return a single model registry entry with its complete run history."""
    row = db.get(ModelRegistry, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelRegistryDetailOut.model_validate(row)


@router.get("/{model_id}/runs", response_model=ModelRunPage)
def list_model_runs(
    model_id: uuid.UUID,
    db: DbDep,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ModelRunPage:
    """Return paginated run history for a model, newest first.

    Optional filter:
    - ``kind`` — ``training``, ``backtest``, ``inference``, or ``evaluation``
    """
    if db.get(ModelRegistry, model_id) is None:
        raise HTTPException(status_code=404, detail="Model not found")

    stmt = select(ModelRun).where(ModelRun.model_id == model_id)
    if kind is not None:
        stmt = stmt.where(ModelRun.kind == kind)

    total: int = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(ModelRun.started_at.desc(), ModelRun.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return ModelRunPage(
        items=[ModelRunOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
