"""Performance KPI service: query settled predictions and compute segment KPIs.

This is the database-reading entry-point for the performance framework (§39,
§40).  The pure computation lives in ``qwantej.performance.kpi``; this module
is responsible for building ``PerformanceObservation`` lists from the ORM.

Query strategy:
  - Join ``settlements`` → ``predictions`` (via subject_id where subject_type
    = "prediction") → ``fixtures`` → ``competitions`` for league context.
  - Exclude superseded rows (corrections): a row whose ``id`` appears in
    another row's ``supersedes_id`` is the original, now overridden record.
  - Model version comes from ``predictions.model_version_id`` →
    ``model_registry.version`` (outer-joined; may be NULL).

All functions here are read-only.  Nothing is written to the database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Competition,
    Fixture,
    Prediction,
    Season,
    Settlement,
)
from backend.models import SettlementOutcome as OrmOutcome
from backend.models.registry import ModelRegistry
from qwantej.performance.kpi import (
    KPIReport,
    PerformanceObservation,
    compute_kpis,
    segment_kpis,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_OUTCOME_MAP: dict[OrmOutcome, str] = {
    OrmOutcome.WIN: "win",
    OrmOutcome.LOSS: "loss",
    OrmOutcome.VOID: "void",
    OrmOutcome.PUSH: "push",
}


def _build_observation(
    row: Settlement,
    market: str | None,
    league: str | None,
    model_version: str | None,
) -> PerformanceObservation:
    return PerformanceObservation(
        outcome=_OUTCOME_MAP[row.outcome],
        taken_odds=float(row.taken_odds) if row.taken_odds is not None else None,
        stake=float(row.stake) if row.stake is not None else None,
        profit_loss=float(row.profit_loss) if row.profit_loss is not None else None,
        clv=float(row.clv) if row.clv is not None else None,
        brier_contribution=(
            float(row.brier_contribution) if row.brier_contribution is not None else None
        ),
        log_loss_contribution=(
            float(row.log_loss_contribution)
            if row.log_loss_contribution is not None
            else None
        ),
        market=market,
        league=league,
        model_version=model_version,
    )


# ---------------------------------------------------------------------------
# Primary query
# ---------------------------------------------------------------------------

def query_performance_observations(
    session: Session,
    *,
    subject_type: str = "prediction",
    since: datetime | None = None,
    market: str | None = None,
    limit: int = 2000,
) -> list[PerformanceObservation]:
    """Return settled observations as domain objects, ordered by ``settled_at``.

    Args:
        session: open SQLAlchemy session.
        subject_type: "prediction" (default) or "accumulator".
        since: if given, only include settlements on or after this timestamp.
        market: if given, restrict to predictions for this market.
        limit: maximum rows to return (default 2000).

    Superseded rows (original settlements that have been corrected) are
    excluded; only the effective (latest) settlement per subject is returned.

    For predictions the query joins Prediction, Fixture, Competition, and
    ModelRegistry to populate market, league, and model_version segments.
    For accumulators no join is attempted and those fields are left None.
    """
    # Rows that have been superseded by a correction.
    superseded_ids_subq = (
        select(Settlement.supersedes_id)
        .where(Settlement.supersedes_id.is_not(None))
        .scalar_subquery()
    )

    if subject_type == "prediction":
        stmt = (
            select(
                Settlement,
                Prediction.market.label("pred_market"),
                Competition.name.label("league_name"),
                ModelRegistry.version.label("model_ver"),
            )
            .join(
                Prediction,
                (Settlement.subject_id == Prediction.id)
                & (Settlement.subject_type == "prediction"),
            )
            .join(Fixture, Prediction.fixture_id == Fixture.id)
            .join(Season, Fixture.season_id == Season.id)
            .join(Competition, Season.competition_id == Competition.id)
            .outerjoin(
                ModelRegistry,
                Prediction.model_version_id == ModelRegistry.id,
            )
            .where(Settlement.id.not_in(superseded_ids_subq))
        )
        if since is not None:
            stmt = stmt.where(Settlement.settled_at >= since)
        if market is not None:
            stmt = stmt.where(Prediction.market == market)
        stmt = stmt.order_by(Settlement.settled_at).limit(limit)

        rows = session.execute(stmt).all()
        return [
            _build_observation(
                row.Settlement,
                market=row.pred_market,
                league=row.league_name,
                model_version=row.model_ver,
            )
            for row in rows
        ]

    # Accumulator path: no join to predictions/fixtures.
    stmt_acca = (
        select(Settlement)
        .where(
            Settlement.subject_type == subject_type,
            Settlement.id.not_in(superseded_ids_subq),
        )
        .order_by(Settlement.settled_at)
        .limit(limit)
    )
    if since is not None:
        stmt_acca = stmt_acca.where(Settlement.settled_at >= since)

    return [
        _build_observation(row, market=None, league=None, model_version=None)
        for row in session.scalars(stmt_acca)
    ]


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def performance_report(
    session: Session,
    *,
    subject_type: str = "prediction",
    since: datetime | None = None,
    market: str | None = None,
    limit: int = 2000,
) -> KPIReport:
    """Compute overall KPIs for settled predictions.

    Returns a single :class:`~qwantej.performance.kpi.KPIReport`.
    """
    observations = query_performance_observations(
        session,
        subject_type=subject_type,
        since=since,
        market=market,
        limit=limit,
    )
    return compute_kpis(observations)


def performance_by_segment(
    session: Session,
    *,
    by: str,
    subject_type: str = "prediction",
    since: datetime | None = None,
    limit: int = 2000,
) -> dict[str, KPIReport]:
    """Compute KPIs segmented by market, league, or model_version.

    Args:
        session: open SQLAlchemy session.
        by: one of ``"market"``, ``"league"``, or ``"model_version"``.
        subject_type: "prediction" or "accumulator".
        since: restrict to settlements on or after this timestamp.
        limit: maximum raw rows before segmentation.

    Returns a dict of segment → :class:`~qwantej.performance.kpi.KPIReport`.
    """
    observations = query_performance_observations(
        session,
        subject_type=subject_type,
        since=since,
        limit=limit,
    )
    return segment_kpis(observations, by=by)
