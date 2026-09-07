"""Constraint checking for accumulator leg pools and combinations (framework §30–32).

All functions are pure — no I/O, no side effects.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal

from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import AccumulatorLeg


def passes_leg_gate(leg: AccumulatorLeg, policy: AccumulatorPolicy, *, as_of: datetime) -> bool:
    """Return True if a single leg clears all individual-leg policy gates."""
    if leg.qss < policy.hard_qss_floor:
        return False
    if leg.dqs < policy.min_dqs:
        return False
    age = as_of - leg.captured_at
    if age > policy.price_freshness_max_age:
        return False
    return True


def combined_odds(legs: tuple[AccumulatorLeg, ...]) -> Decimal:
    result = Decimal("1")
    for leg in legs:
        result *= leg.decimal_odds
    return result


def conservative_joint_probability(legs: tuple[AccumulatorLeg, ...]) -> float:
    """Product of conservative leg probabilities (independence baseline only)."""
    p = 1.0
    for leg in legs:
        p *= leg.conservative_probability
    return p


def passes_combination_constraints(
    legs: tuple[AccumulatorLeg, ...],
    policy: AccumulatorPolicy,
) -> bool:
    """Return True if a combination of legs satisfies all hard accumulator constraints."""
    n = len(legs)
    if n < policy.min_legs or n > policy.max_legs:
        return False

    # One leg per fixture
    fixture_counts = Counter(leg.fixture_id for leg in legs)
    if fixture_counts.most_common(1)[0][1] > 1:
        return False

    # Max legs per league
    league_counts = Counter(leg.league_id for leg in legs)
    if league_counts.most_common(1)[0][1] > policy.max_legs_per_league:
        return False

    # Max legs per market family
    market_counts = Counter(leg.market_family for leg in legs)
    if market_counts.most_common(1)[0][1] > policy.max_legs_per_market_family:
        return False

    # Odds band
    odds = combined_odds(legs)
    if odds < policy.min_combined_odds or odds > policy.max_combined_odds:
        return False

    return True


def dependence_penalty(legs: tuple[AccumulatorLeg, ...]) -> float:
    """Conservative proxy penalty for systemic dependence.

    Penalises same-league and same-market-family concentration.  Coefficients
    are intentionally conservative until empirical covariance matrices are
    available (framework §31).
    """
    n = len(legs)
    if n < 2:
        return 0.0

    league_counts = Counter(leg.league_id for leg in legs)
    same_league_pairs = sum(c * (c - 1) // 2 for c in league_counts.values())

    market_counts = Counter(leg.market_family for leg in legs)
    same_market_triples = sum(max(0, c * (c - 1) * (c - 2) // 6) for c in market_counts.values())

    return 0.05 * same_league_pairs + 0.03 * same_market_triples
