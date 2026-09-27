"""Accumulator results service: which ticket products won, by year/month/day.

Reads accumulator tickets and their legs' *effective* prediction settlements
(superseded corrections excluded, as in ``backend.services.performance``)
and hands them to the pure tally in
``qwantej.performance.accumulator_results``.

Read-only: nothing is written to the database.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Accumulator, Settlement
from backend.models.settlements import TicketStatus
from qwantej.performance.accumulator_results import (
    Granularity,
    PeriodTally,
    TicketRecord,
    derive_ticket_result,
    tally_by_period,
)


def effective_leg_outcomes(
    session: Session, prediction_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Map prediction id -> outcome of its effective (latest, uncorrected) settlement."""
    if not prediction_ids:
        return {}
    superseded_ids = (
        select(Settlement.supersedes_id)
        .where(Settlement.supersedes_id.is_not(None))
        .scalar_subquery()
    )
    rows = session.execute(
        select(Settlement.subject_id, Settlement.outcome)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.subject_id.in_(prediction_ids),
            Settlement.id.not_in(superseded_ids),
        )
        .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
    ).all()
    outcomes: dict[uuid.UUID, str] = {}
    for subject_id, outcome in rows:
        outcomes.setdefault(subject_id, outcome.value)
    return outcomes


def accumulator_ticket_records(
    session: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    product: str | None = None,
) -> list[TicketRecord]:
    """Return every ticket published in ``[since, until)`` with its derived result."""
    stmt = select(Accumulator).options(selectinload(Accumulator.legs))
    if since is not None:
        stmt = stmt.where(Accumulator.published_at >= since)
    if until is not None:
        stmt = stmt.where(Accumulator.published_at < until)
    if product is not None:
        stmt = stmt.where(Accumulator.product == product)
    tickets = list(session.scalars(stmt))

    leg_outcomes = effective_leg_outcomes(
        session, {leg.prediction_id for t in tickets for leg in t.legs}
    )
    return [
        TicketRecord(
            product=t.product,
            published_at=t.published_at,
            result=derive_ticket_result(
                [leg_outcomes.get(leg.prediction_id) for leg in t.legs],
                ticket_voided=t.status == TicketStatus.VOID,
            ),
        )
        for t in tickets
    ]


def accumulator_results_by_period(
    session: Session,
    *,
    granularity: Granularity,
    since: datetime | None = None,
    until: datetime | None = None,
    product: str | None = None,
) -> list[PeriodTally]:
    """Ticket results per product, grouped by UTC publication year/month/day."""
    records = accumulator_ticket_records(
        session, since=since, until=until, product=product
    )
    return tally_by_period(records, granularity)
