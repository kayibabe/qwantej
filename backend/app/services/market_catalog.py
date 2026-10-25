"""Canonical contracts for the match markets currently scored or settled.

Legacy keys retain the existing database/API values. Canonical market and
selection IDs are separate so related selections can share one market contract.
This catalog describes current capability; it does not imply qualification or
model promotion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


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
    qualification_policy_id: str | None = None
    qualification_mode: str = "generic_recommendation_only"
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
_TOTAL_QUALIFICATION_POLICY_IDS = {
    "under_0.5": "under05-v1-provisional",
    "over_1.5": "over15-v1-provisional",
    "under_1.5": "under15-v1-provisional",
    "over_2.5": "over25-v1-provisional",
    "under_2.5": "under25-v1-provisional",
    "over_3.5": "over35-v1-provisional",
    "under_3.5": "under35-v1-provisional",
    "over_4.5": "over45-v1-provisional",
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
                qualification_policy_id=_TOTAL_QUALIFICATION_POLICY_IDS.get(market_id),
                qualification_mode=(
                    "market_specific_provisional"
                    if market_id in _TOTAL_QUALIFICATION_POLICY_IDS
                    else "generic_recommendation_only" if market_id in scored
                    else "settlement_only"
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
        "model_ensemble", qualification_mode="settlement_only", scored=False,
    ),
)

# These are the provider market IDs the existing live odds importer reads.
# Keep mappings explicit: unsupported bookmaker markets must not inherit a
# superficially similar score-derived settlement contract.
API_FOOTBALL_BET_FAMILIES = {
    1: "match_result",
    5: "total_goals",
    8: "both_teams_to_score",
    12: "double_chance",
}
CATALOG_VERSION = "1.0.0"
API_FOOTBALL_MAPPING_VERSION = "1.0.0"

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


def api_football_odds_mapping(market: MarketDefinition) -> dict | None:
    """Describe the current API-Football quote mapping for one selection."""
    if market.family == "match_result":
        return {
            "provider": "api_football",
            "provider_market_id": 1,
            "mapping_version": API_FOOTBALL_MAPPING_VERSION,
            "selection_labels": {
                "home": ["Home"], "draw": ["Draw"], "away": ["Away"],
            }.get(market.selection_id, []),
        }
    if market.family == "total_goals":
        line = f"{market.line:.1f}" if market.line is not None else None
        if line is None:
            return None
        line_pattern = line.replace(".", "[.,]")
        return {
            "provider": "api_football",
            "provider_market_id": 5,
            "mapping_version": API_FOOTBALL_MAPPING_VERSION,
            "selection_label_regex": rf"(?i)^{market.selection_id}\s*{line_pattern}$",
            "line_fallback_field": "handicap",
        }
    if market.family == "both_teams_to_score":
        return {
            "provider": "api_football",
            "provider_market_id": 8,
            "mapping_version": API_FOOTBALL_MAPPING_VERSION,
            "selection_labels": [market.selection_id.title()],
        }
    if market.family == "double_chance":
        aliases = {
            "home_or_draw": ["1X", "Home/Draw", "Home or Draw"],
            "draw_or_away": ["X2", "Draw/Away", "Away or Draw"],
            "either_team": ["12", "Home/Away", "Home or Away"],
        }.get(market.selection_id)
        if aliases is not None:
            return {
                "provider": "api_football",
                "provider_market_id": 12,
                "mapping_version": API_FOOTBALL_MAPPING_VERSION,
                "selection_labels": aliases,
            }
    return None


def api_football_quote_provenance(bet_id: int, value: dict, market_key: str) -> dict:
    """Return source metadata for an accepted API-Football quote snapshot."""
    definition = get_market_definition(market_key)
    raw_selection = value.get("value")
    raw_line = value.get("handicap")
    return {
        "source_provider": "api_football",
        "provider_market_id": bet_id,
        "provider_selection_raw": None if raw_selection is None else str(raw_selection),
        "provider_line_raw": None if raw_line is None else str(raw_line),
        "market_catalog_version": CATALOG_VERSION,
        "market_contract_version": definition.contract_version if definition else None,
        "market_mapping_version": API_FOOTBALL_MAPPING_VERSION,
    }


def map_api_football_value(bet_id: int, value: dict) -> tuple[str | None, str]:
    """Map supported API-Football bet values to registered legacy keys."""
    label = str(value.get("value", "")).strip()
    low = label.lower()
    family = API_FOOTBALL_BET_FAMILIES.get(bet_id)
    if family == "match_result":
        market_key = {"home": "home_win", "draw": "draw", "away": "away_win"}.get(low)
        definition = get_market_definition(market_key) if market_key else None
        if definition and definition.family == family:
            return definition.legacy_key, definition.legacy_key
    elif family == "total_goals":
        found = re.search(r"(over|under)\s*([0-9]+(?:[.,][0-9]+)?)", low)
        direction = found.group(1) if found else low
        point = found.group(2).replace(",", ".") if found else str(
            value.get("handicap", "")
        ).strip()
        if direction in {"over", "under"} and point:
            definition = get_market_definition(f"{direction}_{point}")
            if definition and definition.family == family:
                return definition.legacy_key, definition.legacy_key
    elif family == "both_teams_to_score" and low in {"yes", "no"}:
        key = f"btts_{low}"
        definition = get_market_definition(key)
        if definition:
            return definition.legacy_key, definition.legacy_key
    elif family == "double_chance":
        normalized = low.replace(" ", "")
        market_key = {
            "1x": "double_chance_1x", "home/draw": "double_chance_1x",
            "homeordraw": "double_chance_1x", "x2": "double_chance_x2",
            "draw/away": "double_chance_x2", "awayordraw": "double_chance_x2",
            "12": "double_chance_12", "home/away": "double_chance_12",
            "homeoraway": "double_chance_12",
        }.get(normalized)
        definition = get_market_definition(market_key) if market_key else None
        if definition:
            return definition.legacy_key, definition.legacy_key
    return None, label


def market_catalog_payload() -> list[dict]:
    """Return JSON-friendly market contracts for diagnostics and future APIs."""
    return [
        {
            **asdict(market),
            "required_events": list(market.required_events),
            "odds_source_mappings": (
                [api_football_odds_mapping(market)]
                if api_football_odds_mapping(market) is not None
                else []
            ),
        }
        for market in ALL_MARKETS
    ]
