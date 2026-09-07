"""Accumulator optimiser: selects the best ticket per product tier (framework §33).

Search strategy: exhaustive when the qualified pool is small (≤ beam_width
after initial ranking), beam search otherwise.  An auditable, enumerative
approach is preferred over a black-box solver (ACCUMULATOR_POLICY.md §Optimiser
objective) so the selected ticket's constraints are directly verifiable.

Objective (maximise):
    0.40 * mean_edge + 0.30 * mean_qss/100 + 0.30 * mean_reliability/100
    − dependence_penalty
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime

from qwantej.accumulator.constraints import (
    combined_odds,
    conservative_joint_probability,
    dependence_penalty,
    passes_combination_constraints,
    passes_leg_gate,
)
from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import (
    AccumulatorLeg,
    AccumulatorRejectionReason,
    AccumulatorTicket,
)
from qwantej.bankroll.state import ProductTier

_WEIGHT_EDGE = 0.40
_WEIGHT_QSS = 0.30
_WEIGHT_RELIABILITY = 0.30


@dataclass(frozen=True)
class AccumulatorResult:
    product: ProductTier
    ticket: AccumulatorTicket | None
    rejection_reason: AccumulatorRejectionReason | None
    legs_evaluated: int
    legs_qualified: int
    combinations_evaluated: int
    policy_version: str
    as_of: datetime


def build_ticket(
    candidate_legs: list[AccumulatorLeg],
    product: ProductTier,
    policy: AccumulatorPolicy,
    *,
    as_of: datetime,
) -> AccumulatorResult:
    """Find the best accumulator ticket for *product* from *candidate_legs*.

    Returns an `AccumulatorResult` with either a ticket or a rejection reason.
    No exceptions are raised for "no qualified acca" — that is an expected
    operational result (ACCUMULATOR_POLICY.md).
    """
    if policy.product is not product:
        raise ValueError(
            f"policy product {policy.product!r} does not match requested {product!r}"
        )

    total_legs = len(candidate_legs)

    qualified = [
        leg for leg in candidate_legs if passes_leg_gate(leg, policy, as_of=as_of)
    ]
    n_qualified = len(qualified)

    if n_qualified < policy.min_legs:
        return AccumulatorResult(
            product=product,
            ticket=None,
            rejection_reason=AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS,
            legs_evaluated=total_legs,
            legs_qualified=n_qualified,
            combinations_evaluated=0,
            policy_version=policy.version,
            as_of=as_of,
        )

    # Beam: keep the top beam_width legs by QSS to bound the search space.
    pool = sorted(qualified, key=lambda leg: leg.qss, reverse=True)[: policy.beam_width]

    best_ticket: AccumulatorTicket | None = None
    best_score = float("-inf")
    combinations_evaluated = 0

    for size in range(policy.min_legs, policy.max_legs + 1):
        for combo in itertools.combinations(pool, size):
            legs = tuple(combo)
            combinations_evaluated += 1
            if not passes_combination_constraints(legs, policy):
                continue
            score = _objective(legs)
            if score > best_score:
                best_score = score
                penalty = dependence_penalty(legs)
                best_ticket = AccumulatorTicket(
                    legs=legs,
                    product=product,
                    combined_odds=combined_odds(legs),
                    conservative_joint_probability=conservative_joint_probability(legs),
                    objective_score=score,
                    dependence_penalty_applied=penalty,
                )

    if best_ticket is None:
        return AccumulatorResult(
            product=product,
            ticket=None,
            rejection_reason=AccumulatorRejectionReason.NO_VALID_COMBINATION,
            legs_evaluated=total_legs,
            legs_qualified=n_qualified,
            combinations_evaluated=combinations_evaluated,
            policy_version=policy.version,
            as_of=as_of,
        )

    return AccumulatorResult(
        product=product,
        ticket=best_ticket,
        rejection_reason=None,
        legs_evaluated=total_legs,
        legs_qualified=n_qualified,
        combinations_evaluated=combinations_evaluated,
        policy_version=policy.version,
        as_of=as_of,
    )


def _objective(legs: tuple[AccumulatorLeg, ...]) -> float:
    n = len(legs)
    mean_edge = sum(leg.edge for leg in legs) / n
    mean_qss = sum(leg.qss for leg in legs) / n / 100.0
    mean_reliability = sum(leg.reliability for leg in legs) / n / 100.0
    penalty = dependence_penalty(legs)
    return (
        _WEIGHT_EDGE * mean_edge
        + _WEIGHT_QSS * mean_qss
        + _WEIGHT_RELIABILITY * mean_reliability
        - penalty
    )
