"""Fail-closed persistence of AccumulatorDecision to the database (Phase 8).

Responsibility: translate a domain AccumulatorDecision into one Accumulator
row and one or more AccumulatorLeg rows per product tier that found a ticket,
then link each prediction back via predictions.accumulator_id.

Design rules (mirror predictions.py):
- Fail closed — validate everything before writing anything.  Either all rows
  for a product land atomically (within the caller's transaction) or none do.
- Paper-only gate — Phase 8 enforces paper_only=True on every decision; this
  service refuses to persist a non-paper record until that gate is lifted.
- One accumulator_id per prediction — a prediction cannot belong to two live
  accumulators; a second attempt raises AccumulatorPersistenceError rather
  than silently overwriting.
- Caller owns the Session — flush is called after each product's batch so the
  caller can inspect the rows or roll back; the caller is responsible for
  commit/rollback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import Accumulator, AccumulatorLeg, Prediction, TicketStatus
from qwantej.accumulator.decision import OPTIMISER_VERSION, AccumulatorDecision


class AccumulatorPersistenceError(ValueError):
    """Raised when an AccumulatorDecision cannot be persisted; nothing is written."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("cannot persist accumulator decision: " + "; ".join(problems))


@dataclass(frozen=True)
class PersistedAccumulatorDecision:
    """Summary of what was written for one AccumulatorDecision run."""

    accumulators: list[Accumulator]
    legs_written: int


def persist_accumulator_decision(
    session: Session,
    decision: AccumulatorDecision,
    *,
    fixture_to_prediction: dict[str, uuid.UUID],
    published_at: datetime,
) -> PersistedAccumulatorDecision:
    """Validate and persist all tickets found in *decision*.

    Parameters
    ----------
    session:
        SQLAlchemy session.  The caller owns commit/rollback.
    decision:
        The AccumulatorDecision returned by build_accumulator_decision.
        Must have paper_only=True (Phase 8 invariant).
    fixture_to_prediction:
        Maps each fixture_id (str, as carried by AccumulatorLeg) to the
        prediction UUID that qualified it.  Must cover every fixture_id
        that appears in any ticket leg.
    published_at:
        Timezone-aware timestamp to record as the publication time.
    """
    problems = _validate(decision, fixture_to_prediction, published_at, session)
    if problems:
        raise AccumulatorPersistenceError(problems)

    written: list[Accumulator] = []
    legs_written = 0

    for pd in decision.products:
        if pd.result.ticket is None:
            continue

        ticket = pd.result.ticket
        stake_val: float | None = None
        risk_policy_version: str | None = None
        if pd.stake_decision is not None and pd.stake_decision.approved:
            stake_val = pd.stake_decision.recommended_stake
            risk_policy_version = pd.stake_decision.policy_version

        accumulator = Accumulator(
            product=pd.product.value,
            optimiser_version=OPTIMISER_VERSION,
            policy_version=pd.result.policy_version,
            combined_odds=float(ticket.combined_odds),
            conservative_joint_probability=ticket.conservative_joint_probability,
            stressed_joint_probability=ticket.stressed_joint_probability,
            objective_score=ticket.objective_score,
            dependence_penalty_applied=ticket.dependence_penalty_applied,
            published_at=published_at,
            stake=stake_val,
            risk_policy_version=risk_policy_version,
            status=TicketStatus.PENDING,
            input_manifest_hash=decision.input_manifest_hash,
            risk_state=decision.operating_state.value,
            decision_cutoff=decision.as_of,
            paper_only=decision.paper_only,
        )
        session.add(accumulator)
        session.flush()  # populate accumulator.id before writing legs

        for leg_index, leg in enumerate(ticket.legs):
            prediction_id = fixture_to_prediction[leg.fixture_id]
            fixture_uuid = uuid.UUID(leg.fixture_id)
            session.add(
                AccumulatorLeg(
                    accumulator_id=accumulator.id,
                    prediction_id=prediction_id,
                    fixture_id=fixture_uuid,
                    leg_index=leg_index,
                    league_id=leg.league_id,
                    market_family=leg.market_family,
                    selection=leg.selection,
                    decimal_odds=float(leg.decimal_odds),
                    conservative_probability=leg.conservative_probability,
                    edge=leg.edge,
                    qss=leg.qss,
                )
            )
            # Link the prediction back to this accumulator.
            prediction = session.get(Prediction, prediction_id)
            if prediction is not None:
                prediction.accumulator_id = accumulator.id

            legs_written += 1

        session.flush()
        written.append(accumulator)

    return PersistedAccumulatorDecision(accumulators=written, legs_written=legs_written)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate(
    decision: AccumulatorDecision,
    fixture_to_prediction: dict[str, uuid.UUID],
    published_at: datetime,
    session: Session,
) -> list[str]:
    problems: list[str] = []

    if not decision.paper_only:
        problems.append(
            "paper_only must be True; live accumulator persistence is not yet enabled"
        )
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        problems.append("published_at must be timezone-aware")
    if decision.as_of.tzinfo is None or decision.as_of.utcoffset() is None:
        problems.append("decision.as_of must be timezone-aware")

    for pd in decision.products:
        if pd.result.ticket is None:
            continue
        for leg in pd.result.ticket.legs:
            if leg.fixture_id not in fixture_to_prediction:
                problems.append(
                    f"fixture_to_prediction missing entry for fixture_id={leg.fixture_id!r} "
                    f"(product={pd.product.value})"
                )
                continue
            try:
                uuid.UUID(leg.fixture_id)
            except ValueError:
                problems.append(
                    f"fixture_id={leg.fixture_id!r} is not a valid UUID"
                )
                continue
            prediction_id = fixture_to_prediction[leg.fixture_id]
            prediction = session.get(Prediction, prediction_id)
            if prediction is None:
                problems.append(
                    f"prediction {prediction_id} does not exist in the database "
                    f"(fixture_id={leg.fixture_id!r})"
                )
            elif prediction.accumulator_id is not None:
                problems.append(
                    f"prediction {prediction_id} already belongs to accumulator "
                    f"{prediction.accumulator_id}"
                )

    return problems
