"""GET /accumulators — paginated accumulator ticket archive with legs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.api.deps import DbDep
from backend.models import Accumulator
from backend.schemas.accumulators import AccumulatorOut, AccumulatorPage

router = APIRouter(prefix="/accumulators", tags=["accumulators"])

_MAX_LIMIT = 100


@router.get("", response_model=AccumulatorPage)
def list_accumulators(
    db: DbDep,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccumulatorPage:
    """Return a page of accumulator tickets (newest published first) with legs.

    Optional filter: ``status`` — ``pending``, ``locked``, ``settled``, ``void``
    """
    base_stmt = select(Accumulator)
    if status is not None:
        base_stmt = base_stmt.where(Accumulator.status == status)

    total: int = db.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    rows = list(
        db.scalars(
            base_stmt.options(selectinload(Accumulator.legs))
            .order_by(Accumulator.published_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return AccumulatorPage(
        items=[AccumulatorOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{accumulator_id}", response_model=AccumulatorOut)
def get_accumulator(
    accumulator_id: uuid.UUID,
    db: DbDep,
) -> AccumulatorOut:
    """Return a single accumulator ticket with its legs."""
    row = db.scalar(
        select(Accumulator)
        .where(Accumulator.id == accumulator_id)
        .options(selectinload(Accumulator.legs))
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Accumulator not found")
    return AccumulatorOut.model_validate(row)
