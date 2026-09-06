"""Market baseline model (framework §14, §17, §20).

The bookmaker's own prices, de-vigged, are a model family in their own right:
a strong benchmark and an information signal. It is the reference every other
model must beat to demonstrate value, and — under a governance policy that
prevents Qwantej from simply reproducing the bookmaker (framework §17, §20) —
a candidate blend component.

This is a thin wrapper over `qwantej.markets.devig`: it turns a set of odds for
a market into the same `MatchResultProbs` / probability shapes the statistical
models emit, so the ensemble consumes it uniformly.
"""

from __future__ import annotations

from collections.abc import Mapping

from qwantej.markets.devig import DEFAULT_METHOD, devig
from qwantej.models.probabilities import MatchResultProbs

MARKET_FAMILY = "market"
VERSION = "1.0.0"


def market_result_probabilities(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
    method: str = DEFAULT_METHOD,
) -> MatchResultProbs:
    """Fair (de-vigged) 1X2 probabilities from bookmaker odds."""
    result = devig([home_odds, draw_odds, away_odds], method)
    home, draw, away = result.fair
    return MatchResultProbs(home=home, draw=draw, away=away)


def market_probabilities(
    odds_by_selection: Mapping[str, float],
    method: str = DEFAULT_METHOD,
) -> dict[str, float]:
    """Fair probabilities for an arbitrary market, keyed by selection. The
    odds must cover one mutually exclusive, collectively exhaustive market
    (e.g. all three 1X2 selections, or over/under)."""
    selections = list(odds_by_selection)
    result = devig([odds_by_selection[s] for s in selections], method)
    return dict(zip(selections, result.fair, strict=True))
