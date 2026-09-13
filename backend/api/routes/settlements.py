"""GET /settlements — paginated settlement archive + aggregate summary."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Settlement
from backend.models import SettlementOutcome as OrmOutcome
from backend.schemas.settlements import SettlementOut, SettlementPage, SettlementSummary

router = APIRouter(prefix="/settlements", tags=["settlements"], dependencies=[RequireApiKey])

_MAX_LIMIT = 200

# Allowlist of client-sortable columns — see predictions.py for why this
# can't be a raw client-supplied column name.
_SORT_COLUMNS: dict[str, InstrumentedAttribute] = {
    "settled_at": Settlement.settled_at,
    "outcome": Settlement.outcome,
    "taken_odds": Settlement.taken_odds,
    "closing_odds": Settlement.closing_odds,
    "clv": Settlement.clv,
    "brier_contribution": Settlement.brier_contribution,
    "calibration_bin": Settlement.calibration_bin,
}
SortField = Literal[
    "settled_at",
    "outcome",
    "taken_odds",
    "closing_odds",
    "clv",
    "brier_contribution",
    "calibration_bin",
]
SortDir = Literal["asc", "desc"]


def _effective_stmt(subject_type: str):
    """Base statement for effective (non-superseded) settlements of *subject_type*.

    A row is "effective" when its id has not been named in another row's
    supersedes_id, i.e. it has not been replaced by a correction.
    """
    superseded_ids = select(Settlement.supersedes_id).where(
        Settlement.supersedes_id.is_not(None)
    )
    return (
        select(Settlement)
        .where(
            Settlement.subject_type == subject_type,
            Settlement.id.not_in(superseded_ids),
        )
    )


@router.get("/summary", response_model=SettlementSummary)
def get_settlement_summary(
    db: DbDep,
    subject_type: Annotated[str, Query(max_length=20)] = "prediction",
) -> SettlementSummary:
    """Aggregate KPIs over effective settlements: win rate, avg CLV, avg Brier."""
    base = _effective_stmt(subject_type).subquery()

    row = db.execute(
        select(
            func.count().label("n_settled"),
            func.count().filter(base.c.outcome == OrmOutcome.WIN).label("n_wins"),
            func.count().filter(base.c.outcome == OrmOutcome.LOSS).label("n_losses"),
            func.count().filter(base.c.outcome == OrmOutcome.VOID).label("n_voids"),
            func.avg(base.c.clv).label("avg_clv"),
            func.avg(base.c.brier_contribution).label("avg_brier"),
        ).select_from(base)
    ).one()

    n_decided = row.n_wins + row.n_losses
    win_rate = row.n_wins / n_decided if n_decided > 0 else None
    avg_clv = float(row.avg_clv) if row.avg_clv is not None else None
    avg_brier = float(row.avg_brier) if row.avg_brier is not None else None

    return SettlementSummary(
        n_settled=row.n_settled,
        n_wins=row.n_wins,
        n_losses=row.n_losses,
        n_voids=row.n_voids,
        win_rate=win_rate,
        avg_clv=avg_clv,
        avg_brier=avg_brier,
    )


@router.get("", response_model=SettlementPage)
def list_settlements(
    db: DbDep,
    subject_type: Annotated[str, Query(max_length=20)] = "prediction",
    outcome: Annotated[str | None, Query(max_length=10)] = None,
    sort: Annotated[SortField | None, Query()] = None,
    direction: Annotated[SortDir, Query(alias="dir")] = "desc",
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SettlementPage:
    """Return a page of effective settlements, most-recently-settled first by default.

    Optional filters:
    - ``subject_type`` — ``prediction`` (default) or ``accumulator``
    - ``outcome`` — ``win``, ``loss``, ``void``, or ``push``

    Optional sort:
    - ``sort`` — one of the allowlisted columns in ``_SORT_COLUMNS``
    - ``dir`` — ``asc`` or ``desc`` (default ``desc``); ignored if ``sort`` is omitted
    """
    stmt = _effective_stmt(subject_type)
    if outcome is not None:
        stmt = stmt.where(Settlement.outcome == outcome)

    total: int = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0

    sort_column = _SORT_COLUMNS[sort] if sort else Settlement.settled_at
    primary_order = sort_column.asc() if sort and direction == "asc" else sort_column.desc()
    # NULLS LAST regardless of direction — see predictions.py for rationale.
    primary_order = primary_order.nulls_last()
    rows = list(
        db.scalars(
            stmt.order_by(primary_order, Settlement.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return SettlementPage(
        items=[SettlementOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
