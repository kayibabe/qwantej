import math
from types import SimpleNamespace

import pytest

from app.services.under05 import (
    CONTEXT_CHECKS, RISK_CHECKS, THRESHOLDS, poisson_under05,
    prediction_qualification, probability_grade, qualify_under05,
)


def evidence():
    data = {
        "metrics": {key: threshold for key, (_, threshold) in THRESHOLDS.items()},
        "sample_sizes": {"home": 10, "away": 15},
        "context_review": {key: "verified" for key in CONTEXT_CHECKS},
        "risk_review": {key: "clear" for key in RISK_CHECKS},
        "calibration": {"market": "under_0.5", "status": "promoted", "profile_id": 5,
                        "method": "platt_logit", "checks": {key: True for key in (
                            "brier_improved", "calibration_not_worse", "enough_priced_bets",
                            "positive_roi_evidence", "roi_not_worse")}},
    }
    data["metrics"].update(home_projected_goals=.6, away_projected_goals=.6)
    return data


@pytest.mark.parametrize("p,grade", [(0, "D"), (.1499, "D"), (.15, "C"), (.2199, "C"),
                                     (.22, "B"), (.2999, "B"), (.30, "A"), (.3999, "A"),
                                     (.40, "A+"), (1, "A+"), (math.nan, None), (1.1, None)])
def test_grade_boundaries(p, grade):
    assert probability_grade(p) == grade


def test_poisson_and_stressed_value_examples():
    assert poisson_under05(1) == pytest.approx(.3678794)
    assert 1 - poisson_under05(1.2) == pytest.approx(.6988058)
    assert poisson_under05(math.log(2)) == pytest.approx(.5)
    result = qualify_under05(.35, 3.2, evidence())
    assert result["expected_value"] == pytest.approx(.12)
    assert result["stressed_expected_value"] == pytest.approx(-.04)
    assert result["status"] == "REJECT"
    assert "UNDER05_NO_POSITIVE_STRESSED_VALUE" in result["reasons"]
    assert qualify_under05(.35, 3.5, evidence())["status"] == "QUALIFY"
    result = qualify_under05(.4, 3, evidence())
    assert result["one_plus_probability"] == .6
    assert result["implied_probability"] == pytest.approx(1 / 3)
    assert result["edge"] == pytest.approx(.4 - 1 / 3)


def test_b_grade_requires_explicit_review_and_stressed_value():
    data = evidence()
    assert qualify_under05(.25, 6, data)["status"] == "REJECT"
    data["context_review"]["conditional_value_review"] = "verified"
    assert qualify_under05(.25, 6, data)["status"] == "QUALIFY"
    assert qualify_under05(.25, 5, data)["status"] == "REJECT"  # zero stressed EV
    assert qualify_under05(.21, 10, data)["status"] == "REJECT"


@pytest.mark.parametrize("key", list(THRESHOLDS))
def test_preferences_are_advisory(key):
    data = evidence()
    data["metrics"].pop("home_projected_goals")
    data["metrics"].pop("away_projected_goals")
    direction, threshold = THRESHOLDS[key]
    data["metrics"][key] = threshold + (.01 if direction == "max" else -.01)
    result = qualify_under05(.4, 3, data)
    assert result["status"] == "QUALIFY"
    assert f"UNDER05_{key.upper()}_OUTSIDE" in result["warnings"]


def test_asymmetric_projection_and_10_to_15_sample():
    data = evidence()
    data["metrics"].update(home_projected_goals=.8, away_projected_goals=.2, projected_goals=1)
    assert qualify_under05(.4, 3, data)["status"] == "QUALIFY"
    data["sample_sizes"]["home"] = 9
    assert "UNDER05_INSUFFICIENT_RECENT_SAMPLE" in qualify_under05(.4, 3, data)["reasons"]


@pytest.mark.parametrize("key", RISK_CHECKS)
def test_flagged_and_unreviewed_risks_block_release(key):
    data = evidence()
    data["risk_review"][key] = "flagged"
    assert f"UNDER05_{key.upper()}_FLAGGED" in qualify_under05(.4, 3, data)["reasons"]
    del data["risk_review"][key]
    assert f"UNDER05_{key.upper()}_UNREVIEWED" in qualify_under05(.4, 3, data)["reasons"]


def test_market_is_scored_and_requires_exact_zero_calibration():
    from app.services.model_runner import TARGET_MARKETS
    assert TARGET_MARKETS.count(("under_0.5", "under_0.5")) == 1
    data = evidence()
    data["calibration"]["market"] = "under_1.5"
    assert "UNDER05_CALIBRATION_UNVALIDATED" in qualify_under05(.4, 3, data)["reasons"]
    pred = SimpleNamespace(market="under_0.5", model_probability=.4, source_decimal_odds=3,
                           feature_snapshot={"under15_evidence": evidence()})
    assert prediction_qualification(pred)["status"] == "REJECT"


def test_market_pricing_and_relaxation_cannot_bypass_gate():
    from app.services.accumulator_builder import MARKET_TICKET_SPECS, _relax_spec, selection_rejection_reasons
    leg = SimpleNamespace(market="under_0.5", model_probability=.4, raw_model_probability=None,
                          best_odds=3, feature_snapshot={})
    for spec in MARKET_TICKET_SPECS:
        assert "UNDER05_CALIBRATION_UNVALIDATED" in selection_rejection_reasons(leg, _relax_spec(spec, 3))


@pytest.mark.parametrize("home,away,expected", [(0, 0, "won"), (1, 0, "lost"), (0, 1, "lost"), (1, 1, "lost")])
def test_settlement_boundaries(home, away, expected):
    from app.services.settlement import evaluate_selection
    assert evaluate_selection("under_0.5", home, away).value == expected
