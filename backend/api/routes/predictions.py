"""GET /predictions — paginated, filterable prediction archive."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import ColumnElement, case, func, literal, select
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import Fixture, ModelRegistry, Prediction, Settlement
from backend.schemas.predictions import PredictionOut, PredictionPage

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[RequireApiKey])

_MAX_LIMIT = 200

_SUPERSEDED_SETTLEMENTS = (
    select(Settlement.supersedes_id).where(Settlement.supersedes_id.is_not(None))
)

# Allowlist of client-sortable columns. Never interpolate a client-supplied
# column name into order_by — Literal + this map is what keeps `sort` from
# becoming an arbitrary-column (or SQL injection) vector. The match kickoff
# and the effective settlement outcome are correlated subqueries so sorting
# by them never changes which rows (or how many) the page contains.
_SORT_COLUMNS: dict[str, InstrumentedAttribute | ColumnElement] = {
    "prediction_timestamp": Prediction.prediction_timestamp,
    "market": Prediction.market,
    "selection": Prediction.selection,
    # These two fields are rendered in the archive table from immutable
    # prediction/model metadata, so keep their sort semantics server-side too.
    "model_version": (
        select(ModelRegistry.name + literal(" ") + ModelRegistry.version)
        .where(ModelRegistry.id == Prediction.model_version_id)
        .scalar_subquery()
    ),
    "conservative_probability": Prediction.conservative_probability,
    "executable_odds": Prediction.executable_odds,
    "expected_value": Prediction.expected_value,
    "qss": Prediction.qss,
    "dqs": Prediction.dqs,
    "kickoff_utc": (
        select(Fixture.kickoff_utc)
        .where(Fixture.id == Prediction.fixture_id)
        .scalar_subquery()
    ),
    "outcome": (
        select(Settlement.outcome)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.subject_id == Prediction.id,
            Settlement.id.not_in(_SUPERSEDED_SETTLEMENTS),
        )
        .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
        .limit(1)
        .scalar_subquery()
    ),
    # Match the visible audit badges: production passed, production rejected,
    # research passed, research rejected.
    "audit": case(
        (Prediction.research_mode.is_(True) & Prediction.gate_passed.is_(False), 3),
        (Prediction.research_mode.is_(True), 2),
        (Prediction.gate_passed.is_(False), 1),
        else_=0,
    ),
}
SortField = Literal[
    "prediction_timestamp",
    "market",
    "selection",
    "model_version",
    "conservative_probability",
    "executable_odds",
    "expected_value",
    "qss",
    "dqs",
    "kickoff_utc",
    "outcome",
    "audit",
]
SortDir = Literal["asc", "desc"]
PredictionScope = Literal["all", "production", "research", "awaiting", "overdue"]


def _effective_settlement_exists() -> ColumnElement[bool]:
    """Correlated check for a non-superseded prediction settlement."""
    return select(Settlement.id).where(
        Settlement.subject_type == "prediction",
        Settlement.subject_id == Prediction.id,
        Settlement.id.not_in(_SUPERSEDED_SETTLEMENTS),
    ).exists()


def _serialize(rows: list[Prediction], db: DbDep) -> list[PredictionOut]:
    """Attach match context and each forecast's effective settlement outcome."""
    ids = [r.id for r in rows]
    outcomes: dict[uuid.UUID, str] = {}
    if ids:
        superseded = (
            select(Settlement.supersedes_id)
            .where(Settlement.supersedes_id.is_not(None))
            .scalar_subquery()
        )
        for subject_id, outcome in db.execute(
            select(Settlement.subject_id, Settlement.outcome)
            .where(
                Settlement.subject_type == "prediction",
                Settlement.subject_id.in_(ids),
                Settlement.id.not_in(superseded),
            )
            .order_by(Settlement.settled_at.desc())
        ):
            outcomes.setdefault(subject_id, outcome.value)
    now = datetime.now(UTC)
    items = []
    for r in rows:
        fixture = r.fixture
        items.append(
            PredictionOut.model_validate(r).model_copy(
                update={
                    "home_team": fixture.home_team.name if fixture and fixture.home_team else None,
                    "away_team": fixture.away_team.name if fixture and fixture.away_team else None,
                    "kickoff_utc": fixture.kickoff_utc if fixture else None,
                    "competition_name": (
                        fixture.competition.name if fixture and fixture.competition else None
                    ),
                    "outcome": outcomes.get(r.id),
                    "model_version_label": _model_version_label(r),
                    "settlement_overdue": _settlement_overdue(
                        fixture, outcomes.get(r.id), now
                    ),
                }
            )
        )
    return items


def _model_version_label(prediction: Prediction) -> str | None:
    """Return the immutable registry identity stamped on this forecast."""
    model = prediction.model_version
    if model is None:
        return None
    return f"{model.name} {model.version}"


def _settlement_overdue(
    fixture: Fixture | None, outcome: str | None, now: datetime
) -> bool:
    """True only for an un-settled forecast whose kickoff has already passed."""
    if fixture is None or outcome is not None:
        return False
    kickoff = fixture.kickoff_utc
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        # SQLite test round-trips can lose offset data; project timestamps are UTC.
        kickoff = kickoff.replace(tzinfo=UTC)
    else:
        kickoff = kickoff.astimezone(UTC)
    return kickoff <= now


@router.get("/markets", response_model=list[str])
def list_priced_markets(db: DbDep) -> list[str]:
    """Distinct markets that have at least one forecast with a bookmaker price."""
    return list(
        db.scalars(
            select(Prediction.market)
            .where(Prediction.executable_odds.is_not(None))
            .distinct()
            .order_by(Prediction.market)
        )
    )


@router.get("", response_model=PredictionPage)
def list_predictions(
    db: DbDep,
    fixture_id: Annotated[uuid.UUID | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
    priced_only: Annotated[bool, Query()] = False,
    scope: Annotated[PredictionScope, Query()] = "all",
    sort: Annotated[SortField | None, Query()] = None,
    direction: Annotated[SortDir, Query(alias="dir")] = "desc",
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PredictionPage:
    """Return a page of predictions, newest first by default.

    Optional filters:
    - ``fixture_id`` — restrict to one fixture
    - ``market`` — restrict to one market (case-sensitive; e.g. ``1X2``)
    - ``priced_only`` — only forecasts with a bookmaker price (``executable_odds``)
    - ``scope`` — ``production``, ``research``, ``awaiting``, ``overdue``, or ``all``

    Optional sort:
    - ``sort`` — one of the allowlisted columns in ``_SORT_COLUMNS``
    - ``dir`` — ``asc`` or ``desc`` (default ``desc``); ignored if ``sort`` is omitted
    """
    stmt = select(Prediction)
    if fixture_id is not None:
        stmt = stmt.where(Prediction.fixture_id == fixture_id)
    if market is not None:
        stmt = stmt.where(Prediction.market == market)
    if priced_only:
        stmt = stmt.where(Prediction.executable_odds.is_not(None))
    if scope == "production":
        stmt = stmt.where(
            Prediction.research_mode.is_(False),
            Prediction.gate_passed.is_(True),
        )
    elif scope == "research":
        stmt = stmt.where(Prediction.research_mode.is_(True))
    elif scope in {"awaiting", "overdue"}:
        now = datetime.now(UTC)
        kickoff = select(Fixture.kickoff_utc).where(
            Fixture.id == Prediction.fixture_id
        ).scalar_subquery()
        stmt = stmt.where(~_effective_settlement_exists())
        stmt = stmt.where(kickoff > now if scope == "awaiting" else kickoff <= now)

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
            stmt.options(
                selectinload(Prediction.fixture).options(
                    selectinload(Fixture.home_team),
                    selectinload(Fixture.away_team),
                    selectinload(Fixture.competition),
                ),
                selectinload(Prediction.model_version),
            )
            .order_by(primary_order, Prediction.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return PredictionPage(
        items=_serialize(rows, db),
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
    return _serialize([row], db)[0]
