"""Accumulator persistence service (Phase 8, framework §28–36).

`persist_accumulator_decision` is the single write path from an
`AccumulatorDecision` into the database.  It:

1.  Enforces the Phase 8 paper-only safety gate (raises if the decision is
    not flagged paper_only).
2.  Acquires a ``SELECT … FOR UPDATE`` lock on every ``Prediction`` row that
    is a leg of the ticket before reading ``accumulator_id``.
3.  Inserts one ``Accumulator`` row for the requested product tier.
4.  Inserts one ``AccumulatorLeg`` row per ticket leg.
5.  Back-links each ``Prediction.accumulator_id`` so the prediction archive
    knows which accumulator it ended up in.

Race condition closed here
--------------------------
Two concurrent callers can both read ``prediction.accumulator_id = None``
and both try to claim the same predictions.  Without a guard the second
write silently overwrites the first accumulator's back-link.

Fix: for every prediction that is a leg of the ticket, acquire a
``SELECT … FOR UPDATE`` lock before reading ``accumulator_id``.  PostgreSQL
serialises the two transactions; the second caller blocks until the first
commits, then observes ``accumulator_id != None`` and raises
``AccumulatorPersistError`` rather than overwriting the first ticket.
SQLite does not enforce ``FOR UPDATE`` (single-writer model), so the
application-level guard is the only protection there — sufficient for
development and test, where concurrent writers are not expected.

Prediction-identity fix
-----------------------
Indexing candidates by ``fixture_id`` is unsafe when a fixture has more than
one prediction (different markets).  ``AccumulatorLeg.prediction_id`` carries
the exact prediction UUID from ``QualifiedSelection.to_leg()``; the service
uses that field directly and cross-validates against the locked row's
``fixture_id`` to catch any ID confusion early.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.predictions import Prediction
from backend.models.settlements import Accumulator
from backend.models.settlements import AccumulatorLeg as AccumulatorLegModel
from qwantej.accumulator.decision import OPTIMISER_VERSION, AccumulatorDecision
from qwantej.accumulator.types import QualifiedSelection
from qwantej.bankroll.state import ProductTier


class AccumulatorPersistError(Exception):
    """Raised when a prediction leg is already claimed by a different accumulator.

    Callers should treat this as a concurrency conflict and abort; the winning
    accumulator is already persisted and the caller should not retry with the
    same predictions.
    """


def persist_accumulator_decision(
    session: Session,
    *,
    decision: AccumulatorDecision,
    product: ProductTier,
    candidates: list[QualifiedSelection],
    optimiser_version: str = OPTIMISER_VERSION,
) -> Accumulator | None:
    """Persist one product tier's ticket from *decision*.

    Returns the new ``Accumulator`` row, or ``None`` when the decision
    contains no ticket for *product* (a normal operational result — the
    optimiser found no valid combination).

    The session is flushed but **not committed**; the caller owns the
    transaction boundary so it can enrol this call in a larger unit of work
    (e.g. bankroll ledger append + accumulator persist in one transaction).

    Parameters
    ----------
    session:
        An open SQLAlchemy ``Session``.  Must not be in a closed or
        rolled-back state.
    decision:
        The full ``AccumulatorDecision`` returned by
        ``build_accumulator_decision``.  Must have ``paper_only=True``.
    product:
        Which product tier's ticket to persist (CORE / GROWTH / ALPHA).
    candidates:
        The ``QualifiedSelection`` pool passed to ``build_accumulator_decision``.
        Each candidate's ``prediction_id`` must match the ``prediction_id``
        carried on the corresponding ``AccumulatorLeg`` (set automatically by
        ``QualifiedSelection.to_leg()``).
    optimiser_version:
        Version string stamped on the ``Accumulator`` row.  Defaults to the
        module-level ``OPTIMISER_VERSION`` constant.

    Raises
    ------
    ValueError
        If ``decision.paper_only`` is not ``True`` — live publication is gated
        behind an explicit release decision (DEVELOPMENT.md §4).
    AccumulatorPersistError
        If any prediction leg already has a non-NULL ``accumulator_id``.
    ValueError
        If a ticket leg's ``prediction_id`` is blank (leg not built from a
        ``QualifiedSelection``), absent from *candidates*, missing from the
        DB, or whose DB ``fixture_id`` does not match the leg's ``fixture_id``.
    """
    # --- Phase 8 release gate ---
    if not decision.paper_only:
        raise ValueError(
            "decision.paper_only must be True; live publication requires an "
            "explicit release decision (see DEVELOPMENT.md §4)"
        )

    product_decision = next(
        (pd for pd in decision.products if pd.product is product), None
    )
    if product_decision is None or product_decision.result.ticket is None:
        return None

    ticket = product_decision.result.ticket

    # Index candidates by prediction_id.  Each prediction_id is unique across
    # the pool, so this map is 1-to-1 — unlike fixture_id, which could be
    # shared by multiple predictions (one per market) on the same match.
    qs_by_pred_id: dict[str, QualifiedSelection] = {
        c.prediction_id: c for c in candidates
    }

    # --- Acquire row locks before any write (race-condition guard) ---
    #
    # with_for_update() issues SELECT … FOR UPDATE in PostgreSQL.  Each
    # Prediction row is locked for the duration of the transaction, so a
    # concurrent session attempting the same predictions blocks here until
    # this transaction commits or rolls back.  After unblocking, the
    # second session reads the committed accumulator_id and raises below.
    locked_predictions: list[Prediction] = []
    for leg in ticket.legs:
        if not leg.prediction_id:
            raise ValueError(
                f"AccumulatorLeg for fixture {leg.fixture_id!r} has no "
                "prediction_id; legs must be built from QualifiedSelection.to_leg()"
            )
        qs = qs_by_pred_id.get(leg.prediction_id)
        if qs is None:
            raise ValueError(
                f"Ticket leg prediction_id {leg.prediction_id!r} not found "
                "in candidates"
            )
        pred_uuid = uuid.UUID(leg.prediction_id)
        pred = session.execute(
            select(Prediction)
            .where(Prediction.id == pred_uuid)
            .with_for_update()
        ).scalar_one_or_none()
        if pred is None:
            raise ValueError(
                f"Prediction {pred_uuid} (fixture {leg.fixture_id!r}) "
                "not found in database"
            )
        # Cross-validate: the locked Prediction's fixture must match the leg.
        if str(pred.fixture_id) != leg.fixture_id:
            raise ValueError(
                f"Prediction {pred_uuid}: DB fixture_id {pred.fixture_id!r} "
                f"does not match leg fixture_id {leg.fixture_id!r}"
            )
        if pred.accumulator_id is not None:
            raise AccumulatorPersistError(
                f"Prediction {pred_uuid} is already linked to accumulator "
                f"{pred.accumulator_id}; refusing to overwrite back-link"
            )
        locked_predictions.append(pred)

    # --- Insert the Accumulator row ---
    stake_decision = product_decision.stake_decision
    accum = Accumulator(
        product=product.value,
        optimiser_version=optimiser_version,
        policy_version=product_decision.result.policy_version,
        combined_odds=float(ticket.combined_odds),
        conservative_joint_probability=ticket.conservative_joint_probability,
        stressed_joint_probability=ticket.stressed_joint_probability,
        objective_score=ticket.objective_score,
        dependence_penalty_applied=ticket.dependence_penalty_applied,
        published_at=decision.as_of,
        stake=(
            float(stake_decision.recommended_stake)
            if stake_decision is not None and stake_decision.approved
            else None
        ),
        risk_policy_version=(
            stake_decision.policy_version if stake_decision is not None else None
        ),
        input_manifest_hash=decision.input_manifest_hash,
        risk_state=decision.operating_state.value,
        decision_cutoff=decision.as_of,
        paper_only=decision.paper_only,
    )
    session.add(accum)
    session.flush()  # populate accum.id before inserting legs

    # --- Insert AccumulatorLeg rows and back-link each Prediction ---
    for leg_index, (leg, pred) in enumerate(
        zip(ticket.legs, locked_predictions, strict=True)
    ):
        session.add(
            AccumulatorLegModel(
                accumulator_id=accum.id,
                prediction_id=pred.id,
                leg_index=leg_index,
                fixture_id=pred.fixture_id,
                league_id=leg.league_id,
                market_family=leg.market_family,
                selection=leg.selection,
                decimal_odds=float(leg.decimal_odds),
                conservative_probability=leg.conservative_probability,
                edge=leg.edge,
                qss=leg.qss,
            )
        )
        pred.accumulator_id = accum.id

    session.flush()
    return accum
