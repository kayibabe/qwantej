"""Canonical contracts for the match markets currently scored or settled.

Legacy keys retain the existing database/API values. Canonical market and
selection IDs are separate so related selections can share one market contract.
This catalog describes current capability; it does not imply qualification or
model promotion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MarketDefinition:
    market_id: str
    selection_id: str
    legacy_key: str
    family: str
    display_name: str
    scope: str
    settlement_rule: str
    required_events: tuple[str, ...]
    probability_source: str
    qualification_probability_source: str | None = None
    scored: bool = True
    line: float | None = None
    contract_version: str = "1.0.0"


_SCORED_TOTALS = (
    "under_0.5", "over_1.5", "under_1.5", "over_2.5", "under_2.5",
    "over_3.5", "under_3.5", "over_4.5", "under_4.5",
)
_SHARED_TOTAL_QUALIFICATION_MARKETS = {
    "under_0.5", "over_1.5", "under_1.5", "over_2.5", "under_2.5",
    "over_3.5", "under_3.5", "over_4.5",
}


def _total_goal_markets() -> tuple[MarketDefinition, ...]:
    """Register the half-goal lines settlement has historically accepted."""
    scored = set(_SCORED_TOTALS)
    by_id: dict[str, MarketDefinition] = {}
    for half_line in range(1, 22, 2):
        line = half_line / 2
        for side in ("over", "under"):
            market_id = f"{side}_{line:.1f}"
            market_key = f"total_goals_{line:.1f}"
            by_id[market_id] = MarketDefinition(
                market_id=market_key,
                selection_id=side,
                legacy_key=market_id,
                family="total_goals",
                display_name=f"{side.title()} {line:.1f} goals",
                scope="regulation",
                settlement_rule=f"total_{side}",
                required_events=("full_time_score",),
                probability_source="model_ensemble" if market_id in scored else "not_scored",
                qualification_probability_source=(
                    "shared_total_goals"
                    if market_id in _SHARED_TOTAL_QUALIFICATION_MARKETS
                    else None
                ),
                scored=market_id in scored,
                line=line,
            )
    return tuple(by_id[market_id] for market_id in _SCORED_TOTALS) + tuple(
        definition for market_id, definition in by_id.items() if market_id not in scored
    )


_SCORE_MARKETS = _total_goal_markets() + (
    MarketDefinition(
        "btts_full_time", "yes", "btts_yes", "both_teams_to_score",
        "Both teams to score: Yes", "regulation", "btts_yes",
        ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "btts_full_time", "no", "btts_no", "both_teams_to_score",
        "Both teams to score: No", "regulation", "btts_no",
        ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "match_result_1x2", "home", "home_win", "match_result", "Home win",
        "regulation", "home_win", ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "match_result_1x2", "draw", "draw", "match_result", "Draw",
        "regulation", "draw", ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "match_result_1x2", "away", "away_win", "match_result", "Away win",
        "regulation", "away_win", ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "double_chance_full_time", "home_or_draw", "double_chance_1x",
        "double_chance", "Home win or draw", "regulation",
        "double_chance_1x", ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "double_chance_full_time", "draw_or_away", "double_chance_x2",
        "double_chance", "Draw or away win", "regulation",
        "double_chance_x2", ("full_time_score",), "model_ensemble",
    ),
    MarketDefinition(
        "draw_no_bet_full_time", "home", "dnb_home", "draw_no_bet",
        "Home draw no bet", "regulation", "dnb_home", ("full_time_score",),
        "model_ensemble",
    ),
    MarketDefinition(
        "draw_no_bet_full_time", "away", "dnb_away", "draw_no_bet",
        "Away draw no bet", "regulation", "dnb_away", ("full_time_score",),
        "model_ensemble",
    ),
)

# These settlement contracts are not in the live model runner's scored list.
_SETTLEMENT_ONLY_MARKETS = (
    MarketDefinition(
        "double_chance_full_time", "either_team", "double_chance_12", "double_chance",
        "Either team to win", "regulation", "double_chance_12", ("full_time_score",),
        "model_ensemble", scored=False,
    ),
)

SCORED_MARKETS = tuple(market for market in _SCORE_MARKETS if market.scored)
SETTLEMENT_ONLY_MARKETS = (
    tuple(market for market in _SCORE_MARKETS if not market.scored)
    + _SETTLEMENT_ONLY_MARKETS
)
ALL_MARKETS = _SCORE_MARKETS + _SETTLEMENT_ONLY_MARKETS


def normalize_market_id(value: str) -> str:
    """Normalize the legacy spelling used by settlement for decimal lines."""
    return value.lower().replace(".", "_")


_MARKETS_BY_NORMALIZED_LEGACY_KEY = {
    normalize_market_id(market.legacy_key): market for market in ALL_MARKETS
}


def get_market_definition(value: str) -> MarketDefinition | None:
    return _MARKETS_BY_NORMALIZED_LEGACY_KEY.get(normalize_market_id(value))


def market_catalog_payload() -> list[dict]:
    """Return JSON-friendly market contracts for diagnostics and future APIs."""
    return [
        {**asdict(market), "required_events": list(market.required_events)}
        for market in ALL_MARKETS
    ]
