"""Accumulator optimiser: selects the best ticket per product tier (framework §33).

Search strategy: exhaustive over all qualified legs, sorted by a QSS/edge
heuristic so the best candidates are evaluated first. When the combination
count reaches policy.max_combinations the search stops early and
AccumulatorResult.search_truncated is set True — an auditable, measurable
bound rather than a silent pool truncation.

Objective (maximise):
    0.40 * mean_edge + 0.30 * mean_qss/100 + 0.30 * mean_reliability/100
    − dependence_penalty

Tie-breaking is deterministic: equal-score combinations are ordered by the
sorted tuple of fixture_ids, ensuring the same input always produces the
same ticket regardless of database or provider ordering.
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
    stressed_joint_probability,
    ticket_passes_ev_gate,
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
    combinations_rejected_odds_band: int
    combinations_rejected_concentration: int
    combinations_rejected_ticket_ev: int
    search_truncated: bool
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
            combinations_rejected_odds_band=0,
            combinations_rejected_concentration=0,
            combinations_rejected_ticket_ev=0,
            search_truncated=False,
            policy_version=policy.version,
            as_of=as_of,
        )

    # Sort by heuristic so when the budget is hit we've seen the best candidates.
    pool = sorted(qualified, key=lambda leg: (leg.qss, leg.edge), reverse=True)

    best_ticket: AccumulatorTicket | None = None
    best_score = float("-inf")
    best_tiebreaker: tuple[str, ...] = ()

    combinations_evaluated = 0
    rejected_odds_band = 0
    rejected_concentration = 0
    rejected_ticket_ev = 0
    search_truncated = False

    outer: bool = False
    for size in range(policy.min_legs, policy.max_legs + 1):
        for combo in itertools.combinations(pool, size):
            if combinations_evaluated >= policy.max_combinations:
                search_truncated = True
                outer = True
                break
            legs = tuple(combo)
            combinations_evaluated += 1

            # Concentration + odds band check (cheap; runs first)
            if not passes_combination_constraints(legs, policy):
                odds = combined_odds(legs)
                if odds < policy.min_combined_odds or odds > policy.max_combined_odds:
                    rejected_odds_band += 1
                else:
                    rejected_concentration += 1
                continue

            # Ticket EV + stress gate
            if not ticket_passes_ev_gate(legs, policy):
                rejected_ticket_ev += 1
                continue

            score = _objective(legs)
            tiebreaker = tuple(sorted(leg.fixture_id for leg in legs))
            if score > best_score or (score == best_score and tiebreaker < best_tiebreaker):
                best_score = score
                best_tiebreaker = tiebreaker
                penalty = dependence_penalty(legs)
                best_ticket = AccumulatorTicket(
                    legs=legs,
                    product=product,
                    combined_odds=combined_odds(legs),
                    conservative_joint_probability=conservative_joint_probability(legs),
                    stressed_joint_probability=stressed_joint_probability(
                        legs, policy.stress_haircut
                    ),
                    objective_score=score,
                    dependence_penalty_applied=penalty,
                )
        if outer:
            break

    if best_ticket is None:
        reason = (
            AccumulatorRejectionReason.SEARCH_BUDGET_EXHAUSTED
            if search_truncated
            else AccumulatorRejectionReason.NO_VALID_COMBINATION
        )
        return AccumulatorResult(
            product=product,
            ticket=None,
            rejection_reason=reason,
            legs_evaluated=total_legs,
            legs_qualified=n_qualified,
            combinations_evaluated=combinations_evaluated,
            combinations_rejected_odds_band=rejected_odds_band,
            combinations_rejected_concentration=rejected_concentration,
            combinations_rejected_ticket_ev=rejected_ticket_ev,
            search_truncated=search_truncated,
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
        combinations_rejected_odds_band=rejected_odds_band,
        combinations_rejected_concentration=rejected_concentration,
        combinations_rejected_ticket_ev=rejected_ticket_ev,
        search_truncated=search_truncated,
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
