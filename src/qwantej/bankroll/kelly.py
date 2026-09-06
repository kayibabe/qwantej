"""Fractional Kelly staking math (framework §35).

Kelly is applied at the *ticket* level: for an accumulator, ``win_probability``
is the combined conservative probability of the whole ticket and
``decimal_odds`` is its combined decimal price. Everything here is a pure
function of edge and odds — never of recent results — so no loss-chasing or
Martingale behaviour can enter through this layer.
"""

from __future__ import annotations

import math


def kelly_fraction(win_probability: float, decimal_odds: float) -> float:
    """Full-Kelly stake fraction ``(p·d − 1) / (d − 1)``, floored at 0.

    A non-positive edge (``p·d ≤ 1``) returns ``0.0`` — Kelly never recommends
    betting into a negative expectation, and it never returns a negative
    (i.e. "lay") fraction here.
    """

    _probability("win_probability", win_probability)
    _odds("decimal_odds", decimal_odds)
    net_odds = decimal_odds - 1.0
    fraction = (win_probability * decimal_odds - 1.0) / net_odds
    return max(0.0, fraction)


def fractional_kelly(
    win_probability: float, decimal_odds: float, multiplier: float
) -> float:
    """Scale full Kelly by ``multiplier`` (≈1/5–1/4 under model uncertainty)."""

    if not math.isfinite(multiplier) or not 0.0 < multiplier <= 1.0:
        raise ValueError(f"multiplier must be finite in (0, 1], got {multiplier}")
    return multiplier * kelly_fraction(win_probability, decimal_odds)


def _probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        raise ValueError(f"{name} must be finite and in (0, 1], got {value}")


def _odds(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 1.0:
        raise ValueError(f"{name} must be finite decimal odds > 1, got {value}")
