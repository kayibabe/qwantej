import math
from types import SimpleNamespace

import pytest

from app.services.under15 import (
    CONTEXT_CHECKS, RISK_CHECKS, THRESHOLDS, poisson_under15,
    prediction_qualification, probability_grade, qualify_under15,
)


def evidence():
    data = {
        "metrics": {key: threshold for key, (_, threshold) in THRESHOLDS.items()},
        "sample_sizes": {"home": 8, "away": 12},
        "context_review": {key: "verified" for key in CONTEXT_CHECKS},
        "risk_review": {key: "clear" for key in RISK_CHECKS},
        "calibration": {"market": "under_1.5", "status": "promoted", "profile_id": 4,
                        "method": "platt_logit", "checks": {key: True for key in (
                            "brier_improved", "calibration_not_worse", "enough_priced_bets",
                            "positive_roi_evidence", "roi_not_worse")}},
    }
    data["metrics"].update(home_projected_goals=.6, away_projected_goals=.6)
    return data


@pytest.mark.parametrize("p,grade", [(0, "D"), (.4499, "D"), (.45, "C"), (.5999, "C"),
                                     (.60, "B"), (.6999, "B"), (.70, "A"), (.7999, "A"),
                                     (.80, "A+"), (1, "A+"), (math.nan, None), (1.1, None)])
def test_grade_boundaries(p, grade):
    assert probability_grade(p) == grade


def test_poisson_examples_and_value():
    assert poisson_under15(1.2) == pytest.approx(.6626273)
    assert poisson_under15(1) == pytest.approx(.7357589)
    result = qualify_under15(.75, 1.5, evidence())
    assert result["status"] == "QUALIFY"
    assert result["two_plus_probability"] == .25
    assert result["expected_value"] == .125
    assert qualify_under15(.75, 1.25, evidence())["expected_value"] == -.0625
    assert qualify_under15(.75, 1.25, evidence())["status"] == "REJECT"


def test_b_grade_requires_compelling_value_review():
    data = evidence()
    assert qualify_under15(.65, 2, data)["status"] == "REJECT"
    data["context_review"]["compelling_value_review"] = "verified"
    assert qualify_under15(.65, 2, data)["status"] == "QUALIFY"
    assert qualify_under15(.59, 3, data)["status"] == "REJECT"
    assert qualify_under15(.65, 1.1, data)["status"] == "REJECT"


def test_individual_preferences_do_not_reject_valid_combined_projection():
    data = evidence()
    data["metrics"].update(home_projected_goals=.9, away_projected_goals=.2, projected_goals=1.1)
    result = qualify_under15(.75, 1.5, data)
    assert result["status"] == "QUALIFY"
    assert "UNDER15_HOME_PROJECTED_GOALS_OUTSIDE" in result["warnings"]
    data["metrics"]["projected_goals"] = .5
    assert "UNDER15_INCONSISTENT_GOAL_PROJECTIONS" in qualify_under15(.75, 1.5, data)["reasons"]


@pytest.mark.parametrize("key", [key for key in THRESHOLDS if key not in ("home_projected_goals", "away_projected_goals")])
def test_required_thresholds(key):
    data = evidence()
    direction, threshold = THRESHOLDS[key]
    data["metrics"][key] = threshold + (.01 if direction == "max" else -.01)
    assert f"UNDER15_{key.upper()}_OUTSIDE" in qualify_under15(.75, 1.5, data)["reasons"]


@pytest.mark.parametrize("key", RISK_CHECKS)
def test_unreviewed_and_flagged_risks_block_release(key):
    data = evidence()
    data["risk_review"][key] = "flagged"
    assert f"UNDER15_{key.upper()}_FLAGGED" in qualify_under15(.75, 1.5, data)["reasons"]
    del data["risk_review"][key]
    assert f"UNDER15_{key.upper()}_UNREVIEWED" in qualify_under15(.75, 1.5, data)["reasons"]


def test_market_is_scored_and_cannot_reuse_other_market_evidence():
    from app.services.model_runner import TARGET_MARKETS
    assert TARGET_MARKETS.count(("under_1.5", "under_1.5")) == 1
    data = evidence()
    data["calibration"]["market"] = "under_2.5"
    assert "UNDER15_CALIBRATION_UNVALIDATED" in qualify_under15(.75, 1.5, data)["reasons"]
    pred = SimpleNamespace(market="under_1.5", model_probability=.75, source_decimal_odds=1.5,
                           feature_snapshot={"under25_evidence": evidence()})
    assert prediction_qualification(pred)["status"] == "REJECT"


def test_market_pricing_and_relaxation_cannot_bypass_gate():
    from app.services.accumulator_builder import MARKET_TICKET_SPECS, _relax_spec, selection_rejection_reasons
    leg = SimpleNamespace(market="under_1.5", model_probability=.9, raw_model_probability=None,
                          best_odds=1.5, feature_snapshot={})
    for spec in MARKET_TICKET_SPECS:
        assert "UNDER15_CALIBRATION_UNVALIDATED" in selection_rejection_reasons(leg, _relax_spec(spec, 3))


@pytest.mark.parametrize("home,away,expected", [(0, 0, "won"), (1, 0, "won"), (0, 1, "won"),
                                                (1, 1, "lost"), (2, 0, "lost"), (0, 2, "lost")])
def test_settlement_boundaries(home, away, expected):
    from app.services.settlement import evaluate_selection
    assert evaluate_selection("under_1.5", home, away).value == expected
