"""Closing Line Value (CLV) calculation (framework §39-40, DATA_DICTIONARY.md).

CLV measures how the taken price compares to the market's final consensus
(closing odds).  Positive CLV means Qwantej captured a better price than
the market eventually implied — a key indicator that the selection process
is exploiting real edge rather than noise.

The `settle()` engine computes CLV as:
    clv = closing_implied − taken_implied
        = 1/closing_odds − 1/taken_odds

Positive → taken_odds > closing_odds (better price than closing) → beat the line.
Negative → taken_odds < closing_odds (worse price than closing) → market moved away.

`clv_probability(a, b)` is a generic helper returning a − b; pass arguments in
the order you want the subtraction to happen.  `clv_log_odds` follows the same
sign convention: log(taken_odds/closing_odds) > 0 when taken_odds > closing_odds.
"""

from __future__ import annotations

import math


def clv_probability(a: float, b: float) -> float:
    """Generic probability difference: a − b.

    The sign is determined by caller convention.  `settle()` calls this as
    clv_probability(closing_implied, taken_implied) so the result is
    positive when taken_odds beat closing (higher odds → better execution).
    """
    _validate_probability("a", a)
    _validate_probability("b", b)
    return a - b


def clv_log_odds(taken_odds: float, closing_odds: float) -> float:
    """Log-odds CLV: log(taken_odds / closing_odds).

    Positive means Qwantej took a higher price (better odds) than the
    market closed at.  Scale: 0.10 ≈ 10% higher odds, which is large.
    """
    _validate_odds("taken_odds", taken_odds)
    _validate_odds("closing_odds", closing_odds)
    return math.log(taken_odds / closing_odds)


def closing_probability_from_odds(closing_odds: float, vig_factor: float = 1.0) -> float:
    """Convert closing decimal odds to implied probability.

    `vig_factor` is the total overround (e.g. 1.05 for a 5% vig market).
    Pass 1.0 (default) to use raw implied probability without vig removal —
    conservative: treats all vig as Qwantej's cost.
    """
    _validate_odds("closing_odds", closing_odds)
    if vig_factor <= 0:
        raise ValueError("vig_factor must be positive")
    return (1.0 / closing_odds) * vig_factor


def calibration_bin(probability: float, width: float = 0.10) -> str:
    """Return the reliability-diagram bin label for a probability.

    E.g. 0.63 → "0.60-0.70" with width=0.10.
    """
    _validate_probability("probability", probability)
    if width <= 0 or width > 1:
        raise ValueError("width must be in (0, 1]")
    # Multiply to avoid floating-point errors from dividing (e.g. 0.60/0.10 = 5.999…)
    n_bins = round(1.0 / width)
    idx = min(int(round(probability * n_bins, 10)), n_bins - 1)
    low = idx / n_bins
    high = min((idx + 1) / n_bins, 1.0)
    return f"{low:.2f}-{high:.2f}"


def _validate_probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError(f"{name} must be a finite float in (0, 1], got {value!r}")


def _validate_odds(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 1:
        raise ValueError(f"{name} must be a finite float > 1, got {value!r}")
