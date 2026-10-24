import math
from types import SimpleNamespace

import pytest

from app.services.under25 import (
    RISK_CHECKS, THRESHOLDS, initial_evidence, poisson_under25,
    probability_grade, qualify_under25,
)


def evidence():
    return {
        "metrics": {key: value for key, (_, value) in THRESHOLDS.items()},
        "sample_sizes": {"home": 8, "away": 12},
        "context_review": {key: "verified" for key in (
            "matchup_adjustment", "opponent_sample_weighting", "league_validation",
            "chance_quality", "defensive_stability", "controlled_tempo")},
        "risk_review": {key: "clear" for key in RISK_CHECKS},
        "calibration": {"status": "promoted", "profile_id": 1, "method": "platt_logit",
                        "checks": {key: True for key in (
                            "brier_improved", "calibration_not_worse", "enough_priced_bets",
                            "positive_roi_evidence", "roi_not_worse")}},
    }


@pytest.mark.parametrize("p,grade", [(0, "D"), (.5499, "D"), (.55, "C"), (.6499, "C"),
                                     (.65, "B"), (.7199, "B"), (.72, "A"), (.7999, "A"),
                                     (.8, "A+"), (1, "A+"), (math.nan, None), (-1, None)])
def test_probability_grades(p, grade):
    assert probability_grade(p) == grade


def test_poisson_illustration_and_value_are_separate():
    assert poisson_under25(1.7) == pytest.approx(.7572232)
    result = qualify_under25(.8, 1.18, evidence())
    assert result["fair_odds"] == 1.25
    assert result["expected_value"] == pytest.approx(-.056)
    assert result["status"] == "REJECT"
    assert qualify_under25(.72, 1.5, evidence())["status"] == "QUALIFY"


def test_b_grade_is_not_in_primary_pool_even_with_value():
    result = qualify_under25(.71, 2, evidence())
    assert result["grade"] == "B"
    assert "UNDER25_PRIMARY_PROBABILITY_BELOW_72" in result["reasons"]


@pytest.mark.parametrize("key", list(THRESHOLDS))
def test_each_screen_is_enforced_in_correct_direction(key):
    data = evidence()
    direction, threshold = THRESHOLDS[key]
    data["metrics"][key] = threshold + (.01 if direction == "max" else -.01)
    assert f"UNDER25_{key.upper()}_OUTSIDE" in qualify_under25(.8, 1.5, data)["reasons"]


@pytest.mark.parametrize("risk", RISK_CHECKS)
def test_risk_flags_and_missing_reviews_block_release(risk):
    data = evidence()
    data["risk_review"][risk] = "flagged"
    assert f"UNDER25_{risk.upper()}_FLAGGED" in qualify_under25(.8, 1.5, data)["reasons"]
    del data["risk_review"][risk]
    assert f"UNDER25_{risk.upper()}_UNREVIEWED" in qualify_under25(.8, 1.5, data)["reasons"]


def test_raw_recent_history_cannot_substitute_for_adjusted_evidence():
    data = initial_evidence({"metrics": {"projected_xg": 1.7}, "sample_sizes": {"home": 12, "away": 12}})
    assert data["metrics"] == {}
    assert data["descriptive_metrics"]["projected_xg"] == 1.7
    assert qualify_under25(.9, 2, data)["status"] == "REJECT"


@pytest.mark.parametrize("change", ["calibration", "sample", "odds", "nan"])
def test_incomplete_evidence_is_rejected(change):
    data, odds = evidence(), 1.5
    if change == "calibration":
        data["calibration"]["method"] = "identity"
    elif change == "sample":
        data["sample_sizes"]["home"] = 7
    elif change == "odds":
        odds = None
    else:
        data["metrics"]["projected_xg"] = math.nan
    assert qualify_under25(.8, odds, data)["status"] == "REJECT"


def test_relaxation_and_market_pricing_cannot_bypass_gate():
    from app.services.accumulator_builder import MARKET_TICKET_SPECS, _relax_spec, selection_rejection_reasons
    leg = SimpleNamespace(market="under_2.5", model_probability=.9, raw_model_probability=None,
                          best_odds=1.5, feature_snapshot={})
    for spec in MARKET_TICKET_SPECS:
        assert "UNDER25_CALIBRATION_UNVALIDATED" in selection_rejection_reasons(leg, _relax_spec(spec, 3))
