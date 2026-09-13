"""GET /predictions — paginated, filterable prediction archive."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Prediction
from backend.schemas.predictions import PredictionOut, PredictionPage

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[RequireApiKey])

_MAX_LIMIT = 200

# Allowlist of client-sortable columns. Never interpolate a client-supplied
# column name into order_by — Literal + this map is what keeps `sort` from
# becoming an arbitrary-column (or SQL injection) vector.
_SORT_COLUMNS: dict[str, InstrumentedAttribute] = {
    "prediction_timestamp": Prediction.prediction_timestamp,
    "market": Prediction.market,
    "selection": Prediction.selection,
    "conservative_probability": Prediction.conservative_probability,
    "executable_odds": Prediction.executable_odds,
    "expected_value": Prediction.expected_value,
    "qss": Prediction.qss,
    "dqs": Prediction.dqs,
}
SortField = Literal[
    "prediction_timestamp",
    "market",
    "selection",
    "conservative_probability",
    "executable_odds",
    "expected_value",
    "qss",
    "dqs",
]
SortDir = Literal["asc", "desc"]


@router.get("", response_model=PredictionPage)
def list_predictions(
    db: DbDep,
    fixture_id: Annotated[uuid.UUID | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
    sort: Annotated[SortField | None, Query()] = None,
    direction: Annotated[SortDir, Query(alias="dir")] = "desc",
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PredictionPage:
    """Return a page of predictions, newest first by default.

    Optional filters:
    - ``fixture_id`` — restrict to one fixture
    - ``market`` — restrict to one market (case-sensitive; e.g. ``1X2``)

    Optional sort:
    - ``sort`` — one of the allowlisted columns in ``_SORT_COLUMNS``
    - ``dir`` — ``asc`` or ``desc`` (default ``desc``); ignored if ``sort`` is omitted
    """
    stmt = select(Prediction)
    if fixture_id is not None:
        stmt = stmt.where(Prediction.fixture_id == fixture_id)
    if market is not None:
        stmt = stmt.where(Prediction.market == market)

    total: int = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0

    sort_column = _SORT_COLUMNS[sort] if sort else Prediction.prediction_timestamp
    primary_order = sort_column.asc() if sort and direction == "asc" else sort_column.desc()
    # NULLS LAST regardless of direction: Postgres defaults DESC to NULLS
    # FIRST, which would put missing-odds/missing-probability rows at the
    # top of a "highest first" sort — the opposite of what a user asking to
    # sort descending actually wants to see.
    primary_order = primary_order.nulls_last()
    # id.desc() as a stable tiebreaker keeps pagination deterministic when the
    # sort column has ties (e.g. many rows with the same market or QSS).
    rows = list(
        db.scalars(
            stmt.order_by(primary_order, Prediction.id.desc())
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
