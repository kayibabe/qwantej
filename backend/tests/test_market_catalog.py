import re

import pytest

from app.services.market_catalog import (
    market_catalog_payload,
    map_api_football_value,
)
from app.services.odds_fetcher import BET_IDS


@pytest.mark.parametrize(
    ("bet_id", "value", "expected"),
    [
        (1, {"value": "Home"}, ("home_win", "home_win")),
        (1, {"value": "Draw"}, ("draw", "draw")),
        (1, {"value": "Away"}, ("away_win", "away_win")),
        (5, {"value": "Over 2.5"}, ("over_2.5", "over_2.5")),
        (5, {"value": "Under 2,5"}, ("under_2.5", "under_2.5")),
        (5, {"value": "Over", "handicap": "1.5"}, ("over_1.5", "over_1.5")),
        (8, {"value": "Yes"}, ("btts_yes", "btts_yes")),
        (8, {"value": "No"}, ("btts_no", "btts_no")),
        (12, {"value": "1X"}, ("double_chance_1x", "double_chance_1x")),
        (12, {"value": "Draw/Away"}, ("double_chance_x2", "double_chance_x2")),
        (12, {"value": "12"}, ("double_chance_12", "double_chance_12")),
        (5, {"value": "Over 2.0"}, (None, "Over 2.0")),
        (99, {"value": "Home"}, (None, "Home")),
    ],
)
def test_api_football_odds_values_map_only_to_registered_contracts(bet_id, value, expected):
    assert map_api_football_value(bet_id, value) == expected


def test_odds_importer_uses_market_catalog_provider_ids():
    assert BET_IDS == {1, 5, 8, 12}
    catalog = market_catalog_payload()
    over_25 = next(row for row in catalog if row["legacy_key"] == "over_2.5")
    assert over_25["odds_source_mappings"] == [{
        "provider": "api_football",
        "provider_market_id": 5,
        "selection_label_regex": r"(?i)^over\s*2[.,]5$",
        "line_fallback_field": "handicap",
    }]
    home_win = next(row for row in catalog if row["legacy_key"] == "home_win")
    assert home_win["odds_source_mappings"][0]["provider_market_id"] == 1
    assert home_win["odds_source_mappings"][0]["selection_labels"] == ["Home"]
    btts_yes = next(row for row in catalog if row["legacy_key"] == "btts_yes")
    assert btts_yes["odds_source_mappings"][0]["provider_market_id"] == 8
    assert btts_yes["odds_source_mappings"][0]["selection_labels"] == ["Yes"]
    double_chance = next(
        row for row in catalog if row["legacy_key"] == "double_chance_1x"
    )
    assert double_chance["odds_source_mappings"][0]["provider_market_id"] == 12


def test_catalog_does_not_imply_odds_coverage_for_unmapped_dnb():
    catalog = market_catalog_payload()
    dnb_home = next(row for row in catalog if row["legacy_key"] == "dnb_home")

    assert dnb_home["odds_source_mappings"] == []


def test_catalog_total_line_pattern_matches_provider_spacing_variants():
    catalog = market_catalog_payload()
    over_25 = next(row for row in catalog if row["legacy_key"] == "over_2.5")
    pattern = re.compile(over_25["odds_source_mappings"][0]["selection_label_regex"])

    assert pattern.fullmatch("Over 2.5")
    assert pattern.fullmatch("over2,5")
