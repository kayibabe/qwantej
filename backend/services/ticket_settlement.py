"""Settle accumulator tickets from their legs' effective settlements.

A ticket is decided the moment its result is certain: any lost leg loses it
immediately; otherwise it is won (or void, when every leg is void/push) once
every leg is settled.  The decision rule is the pure
``qwantej.performance.accumulator_results.derive_ticket_result`` — the same
rule the results-by-period tally uses — so the two can never disagree.

On a decision this service appends one ``Settlement`` row
(``subject_type="accumulator"``) and moves the ticket's lifecycle status to
``settled``.  Settlements stay append-only: if a leg's settlement is later
corrected and the derived ticket result or price changes, a correction row
superseding the previous ticket settlement is appended instead.

If a correction makes the ticket undecided, a ``ticket_reopened`` audit
event withdraws the prior settlement from reporting and status returns to
``pending``. The settlement is retained unchanged; the next decision
supersedes it even if the outcome is again the same. Corrections have no
publication-age cutoff. Ticket row locks serialize concurrent worker runs.

``TicketStatus.VOID`` is reserved for tickets voided administratively; a
ticket whose legs all voided is ``settled`` with a ``void`` outcome, so a
later leg correction can still move it.

Session contract: flushes, never commits (the settlement worker owns the
commit boundary).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    Accumulator,
    AuditActor,
    AuditEvent,
    AuditEventType,
    Settlement,
    TicketSettlementQueue,
)
from backend.models import SettlementOutcome as OrmOutcome
from backend.models.settlements import TicketStatus
from backend.services.accumulator_results import effective_leg_outcomes
from backend.services.settlement_queries import TICKET_REOPENED
from qwantej.performance.accumulator_results import (
    derive_ticket_result,
    ticket_settlement_odds,
)
from qwantej.settlement.engine import settle as _settle_engine
from qwantej.settlement.types import SettlementOutcome as EngineOutcome

log = logging.getLogger(__name__)

RESULT_SOURCE = "derived:leg-settlements"
# settlements.taken_odds is NUMERIC(8, 3).
_MAX_STORABLE_ODDS = 99999.999
_PRICE_QUANTUM = Decimal("0.001")

_ENGINE_OUTCOME = {
    "won": EngineOutcome.WIN,
    "lost": EngineOutcome.LOSS,
    "void": EngineOutcome.VOID,
}
_ORM_OUTCOME = {
    EngineOutcome.WIN: OrmOutcome.WIN,
    EngineOutcome.LOSS: OrmOutcome.LOSS,
    EngineOutcome.VOID: OrmOutcome.VOID,
}
_UNIQUE_MARKERS = (
    "uq_settlements_active_subject",
    "uq_settlements_subject_settled_at",
    "settlements.subject_type",
)


@dataclass
class TicketSettlementRun:
    settled: int = 0
    corrected: int = 0
    reopened: int = 0
    still_pending: int = 0
    errors: list[str] = field(default_factory=list)


def _effective_ticket_settlements(
    session: Session, ticket_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Settlement]:
    """Map ticket id -> its current (not superseded) ticket settlement."""
    if not ticket_ids:
        return {}
    superseded = (
        select(Settlement.supersedes_id)
        .where(Settlement.supersedes_id.is_not(None))
        .scalar_subquery()
    )
    rows = session.scalars(
        select(Settlement)
        .where(
            Settlement.subject_type == "accumulator",
            Settlement.subject_id.in_(ticket_ids),
            Settlement.id.not_in(superseded),
        )
        .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
    ).all()
    current: dict[uuid.UUID, Settlement] = {}
    for row in rows:
        current.setdefault(row.subject_id, row)
    return current


def _storable_price(odds: float | None) -> Decimal | None:
    """Round once, exactly as stored (NUMERIC(8, 3), half-up).

    Rounding here — rather than letting the database round a float — keeps
    the stored value and the value it is later compared against identical.
    Otherwise a half-way product such as 1.05 × 1.05 = 1.1025 can round one
    way in Postgres and the other in Python, and every pass would append a
    spurious correction.
    """
    if odds is None:
        return None
    return Decimal(repr(odds)).quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _same_price(stored: object, price: Decimal | None) -> bool:
    if stored is None or price is None:
        return stored is None and price is None
    return Decimal(str(stored)).quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP) == price


def settle_decided_tickets(session: Session, *, now: datetime) -> TicketSettlementRun:
    """Settle every open ticket whose result is decided; correct drifted ones."""
    run = TicketSettlementRun()
    tickets = list(
        session.scalars(
            select(Accumulator)
            .join(
                TicketSettlementQueue,
                TicketSettlementQueue.accumulator_id == Accumulator.id,
            )
            .where(
                Accumulator.status.in_(
                    [TicketStatus.PENDING, TicketStatus.LOCKED, TicketStatus.SETTLED]
                )
            )
            .options(selectinload(Accumulator.legs))
            .order_by(Accumulator.published_at, Accumulator.id)
            .with_for_update(of=Accumulator)
            .execution_options(populate_existing=True)
        )
    )
    if not tickets:
        return run

    leg_outcomes = effective_leg_outcomes(
        session, {leg.prediction_id for t in tickets for leg in t.legs}
    )
    current = _effective_ticket_settlements(session, {t.id for t in tickets})

    def consume_queue(ticket_id: uuid.UUID) -> None:
        session.execute(
            delete(TicketSettlementQueue).where(
                TicketSettlementQueue.accumulator_id == ticket_id
            )
        )

    for ticket in tickets:
        legs = [
            (leg_outcomes.get(leg.prediction_id), float(leg.decimal_odds))
            for leg in sorted(ticket.legs, key=lambda leg: leg.leg_index)
        ]
        try:
            result = derive_ticket_result([outcome for outcome, _ in legs])
            if result == "pending":
                existing = current.get(ticket.id)
                if existing is not None and ticket.status == TicketStatus.SETTLED:
                    with session.begin_nested():
                        session.add(AuditEvent(
                            event_type=AuditEventType.DATA_REVISION,
                            actor=AuditActor.SYSTEM,
                            actor_ref=RESULT_SOURCE,
                            action=TICKET_REOPENED,
                            entity_type="settlement",
                            entity_id=existing.id,
                            occurred_at=now,
                            summary="Leg correction reopened an undecided ticket",
                            payload={
                                "ticket_id": str(ticket.id),
                                "previous_outcome": existing.outcome.value,
                                "reason_codes": ["LEG_SETTLEMENT_CORRECTED"],
                            },
                        ))
                        ticket.status = TicketStatus.PENDING
                        session.flush()
                    run.reopened += 1
                run.still_pending += 1
                continue
            odds = ticket_settlement_odds(legs, result)
        except ValueError as exc:
            run.errors.append(f"ticket {ticket.id}: {exc}")
            continue
        price = _storable_price(odds)
        if price is not None and price > Decimal(str(_MAX_STORABLE_ODDS)):
            run.errors.append(f"ticket {ticket.id}: settlement odds {price} exceed storage")
            continue

        outcome = _ENGINE_OUTCOME[result]
        existing = current.get(ticket.id)
        if (
            existing is not None
            and ticket.status == TicketStatus.SETTLED
            and existing.outcome == _ORM_OUTCOME[outcome]
            and _same_price(existing.taken_odds, price)
        ):
            consume_queue(ticket.id)
            continue

        metrics = _settle_engine(
            subject_type="accumulator",
            subject_id=str(ticket.id),
            outcome=outcome,
            settled_at=now,
            taken_probability=float(ticket.conservative_joint_probability),
            taken_odds=float(price) if price is not None else None,
            stake=float(ticket.stake) if ticket.stake is not None else None,
            result_source=RESULT_SOURCE,
            reason_codes=(
                ["DERIVED_FROM_LEGS", "LEG_SETTLEMENT_CORRECTED"]
                if existing is not None
                else ["DERIVED_FROM_LEGS"]
            ),
        )
        try:
            with session.begin_nested():
                session.add(
                    Settlement(
                        subject_type="accumulator",
                        subject_id=ticket.id,
                        outcome=_ORM_OUTCOME[metrics.outcome],
                        settled_at=metrics.settled_at,
                        result_source=metrics.result_source,
                        stake=metrics.stake,
                        gross_return=metrics.gross_return,
                        profit_loss=metrics.profit_loss,
                        taken_odds=price,
                        taken_probability=metrics.taken_probability,
                        brier_contribution=metrics.brier_contribution,
                        log_loss_contribution=metrics.log_loss_contribution,
                        calibration_bin=metrics.calibration_bin,
                        reason_codes=metrics.reason_codes,
                        supersedes_id=existing.id if existing is not None else None,
                    )
                )
                ticket.status = TicketStatus.SETTLED
                session.flush()
        except IntegrityError as exc:
            if not any(m in str(exc).lower() for m in _UNIQUE_MARKERS):
                raise
            log.debug("ticket_settlement: ticket %s settled concurrently", ticket.id)
            continue
        if existing is None:
            run.settled += 1
        else:
            run.corrected += 1
        consume_queue(ticket.id)

    log.info(
        "ticket_settlement: settled=%d corrected=%d reopened=%d pending=%d errors=%d",
        run.settled, run.corrected, run.reopened, run.still_pending, len(run.errors),
    )
    for err in run.errors:
        log.error("ticket_settlement: %s", err)
    return run
