"""GET /predictions — paginated, filterable prediction archive."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Prediction
from backend.schemas.predictions import PredictionOut, PredictionPage

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[RequireApiKey])

_MAX_LIMIT = 200


@router.get("", response_model=PredictionPage)
def list_predictions(
    db: DbDep,
    fixture_id: Annotated[uuid.UUID | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PredictionPage:
    """Return a page of predictions, newest first.

    Optional filters:
    - ``fixture_id`` — restrict to one fixture
    - ``market`` — restrict to one market (case-sensitive; e.g. ``1X2``)
    """
    stmt = select(Prediction)
    if fixture_id is not None:
        stmt = stmt.where(Prediction.fixture_id == fixture_id)
    if market is not None:
        stmt = stmt.where(Prediction.market == market)

    total: int = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0

    rows = list(
        db.scalars(
            stmt.order_by(Prediction.prediction_timestamp.desc(), Prediction.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return PredictionPage(
        items=[PredictionOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{prediction_id}", response_model=PredictionOut)
def get_prediction(
    prediction_id: uuid.UUID,
    db: DbDep,
) -> PredictionOut:
    """Return a single prediction by id."""
    row = db.get(Prediction, prediction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return PredictionOut.model_validate(row)
