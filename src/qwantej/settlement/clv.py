"""Closing Line Value (CLV) calculation (framework §39-40, DATA_DICTIONARY.md).

CLV measures how the taken price compares to the market's final consensus
(closing odds).  Positive CLV means Qwantej captured a better price than
the market eventually implied — a key indicator that the selection process
is exploiting real edge rather than noise.

Convention used here: probability-space CLV (taken_p - closing_p).
Positive → taken probability was higher than the closing market implied
(Qwantej got the best of the market).

Alternative: log-odds CLV = log(taken_odds / closing_odds).  Both are
recorded — log-odds CLV is symmetric and easier to aggregate; probability
CLV is more intuitive.  The framework leaves the choice open (DATA_DICTIONARY
§F.1: "consistent odds/probability convention").
"""

from __future__ import annotations

import math


def clv_probability(taken_probability: float, closing_probability: float) -> float:
    """Probability-space CLV: taken_p − closing_p.

    Positive means Qwantej's price implied a higher win probability than
    the closing market, i.e. Qwantej captured the better side of the line.
    """
    _validate_probability("taken_probability", taken_probability)
    _validate_probability("closing_probability", closing_probability)
    return taken_probability - closing_probability


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
