"""Margin removal / de-vigging (framework §20-21, Appendix B).

A bookmaker's decimal odds imply probabilities `1 / odds` that sum to more
than 1 — the excess is the margin (overround / vig). Fair probabilities must
have that margin removed before they can be compared to a model belief
(framework §20: "Raw implied probabilities include margin and should not be
treated as fair probabilities").

Two documented baseline methods are provided (framework Appendix A — research
defaults, to be validated per market):

- ``proportional`` (multiplicative): scale implied probabilities to sum to 1.
  Always valid; the default.
- ``additive`` (equal-margin): subtract an equal share of the margin from each
  outcome. Simple and sometimes a better fit, but it can drive a strong
  longshot negative — when it does, that is reported as an error rather than
  silently clamped, since a negative fair probability is meaningless.

Fuller bookmaker intelligence (Shin, consensus across books, line movement,
CLV) lands with the value/backtesting phase; this module is the baseline the
"market model" family (framework §14) is built on.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_METHOD = "proportional"


@dataclass(frozen=True)
class DevigResult:
    fair: tuple[float, ...]  # margin-free probabilities, sum to 1
    overround: float  # sum of raw implied probabilities (>= 1 for a real book)
    method: str


def implied_probabilities(odds: Sequence[float]) -> tuple[float, ...]:
    """Raw implied probabilities `1 / odds` (still carrying the margin)."""
    _validate_odds(odds)
    return tuple(1.0 / o for o in odds)


def devig(odds: Sequence[float], method: str = DEFAULT_METHOD) -> DevigResult:
    """Remove the bookmaker margin from a set of odds for one mutually
    exclusive, collectively exhaustive market."""
    _validate_odds(odds)
    implied = [1.0 / o for o in odds]
    overround = sum(implied)

    if method == "proportional":
        fair = [p / overround for p in implied]
    elif method == "additive":
        margin_share = (overround - 1.0) / len(implied)
        fair = [p - margin_share for p in implied]
        if any(p <= 0 for p in fair):
            raise ValueError(
                "additive de-vig produced a non-positive fair probability; "
                "this book's odds are too skewed for the equal-margin method — "
                "use method='proportional'"
            )
    else:
        raise ValueError(f"unknown de-vig method {method!r}; use 'proportional' or 'additive'")

    return DevigResult(fair=tuple(fair), overround=overround, method=method)


def _validate_odds(odds: Sequence[float]) -> None:
    if len(odds) < 2:
        raise ValueError(f"need at least 2 outcomes to de-vig, got {len(odds)}")
    for o in odds:
        # Finiteness first: NaN/inf pass the <= 1.0 check and yield NaN fair
        # probabilities that then escape unvalidated.
        if not math.isfinite(o):
            raise ValueError(f"decimal odds must be finite, got {o}")
        if o <= 1.0:
            raise ValueError(f"decimal odds must be > 1.0, got {o}")
