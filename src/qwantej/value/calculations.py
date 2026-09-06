"""Auditable value calculations from conservative probabilities (§20-21)."""

from __future__ import annotations

import math


def probability_edge(
    conservative_probability: float, fair_market_probability: float
) -> float:
    """Return probability edge as a decimal probability-point difference."""
    _probability("conservative_probability", conservative_probability)
    _probability("fair_market_probability", fair_market_probability)
    return conservative_probability - fair_market_probability


def expected_value(conservative_probability: float, executable_odds: float) -> float:
    """Expected profit per unit staked: P_cons × decimal odds - 1."""
    _probability("conservative_probability", conservative_probability)
    _odds("executable_odds", executable_odds)
    return conservative_probability * executable_odds - 1.0


def fair_decimal_odds(probability: float) -> float:
    _probability("probability", probability)
    if probability == 0:
        return math.inf
    return 1.0 / probability


def closing_line_value(executable_odds: float, closing_odds: float) -> float:
    """Decimal-odds CLV: taken price divided by closing price, minus one."""
    _odds("executable_odds", executable_odds)
    _odds("closing_odds", closing_odds)
    return executable_odds / closing_odds - 1.0


def _probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1], got {value}")


def _odds(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 1.0:
        raise ValueError(f"{name} must be finite decimal odds > 1, got {value}")
