import math
from types import SimpleNamespace

import pytest

from app.services.under35 import (
    CONTEXT_CHECKS, RISK_CHECKS, THRESHOLDS, poisson_under35,
    prediction_qualification, probability_grade, qualify_under35,
)


def evidence():
    return {
        "metrics": {key: threshold for key, (_, threshold) in THRESHOLDS.items()},
        "sample_sizes": {"home": 8, "away": 12},
        "context_review": {key: "verified" for key in CONTEXT_CHECKS},
        "risk_review": {key: "clear" for key in RISK_CHECKS},
        "calibration": {"market": "under_3.5", "status": "promoted", "profile_id": 3,
                        "method": "platt_logit", "checks": {key: True for key in (
                            "brier_improved", "calibration_not_worse", "enough_priced_bets",
                            "positive_roi_evidence", "roi_not_worse")}},
    }


@pytest.mark.parametrize("p,grade", [(0, "D"), (.6499, "D"), (.65, "C"), (.7499, "C"),
                                     (.75, "B"), (.8199, "B"), (.82, "A"), (.8999, "A"),
                                     (.90, "A+"), (1, "A+"), (math.nan, None), (1.1, None)])
def test_grade_boundaries(p, grade):
    assert probability_grade(p) == grade


def test_poisson_examples_and_upper_tail():
    assert poisson_under35(2.2) == pytest.approx(.8193524)
    assert poisson_under35(3) == pytest.approx(.6472319)
    assert probability_grade(poisson_under35(2.2)) == "B"
    result = qualify_under35(.85, 1.25, evidence())
    assert result["status"] == "QUALIFY"
    assert result["four_plus_probability"] == pytest.approx(.15)
    assert result["expected_value"] == pytest.approx(.0625)
    assert qualify_under35(.85, 1.1, evidence())["expected_value"] == pytest.approx(-.065)
    assert qualify_under35(.85, 1.1, evidence())["status"] == "REJECT"


def test_b_grade_requires_both_extra_reviews():
    data = evidence()
    assert qualify_under35(.80, 1.5, data)["status"] == "REJECT"
    data["context_review"]["strong_supporting_evidence"] = "verified"
    assert qualify_under35(.80, 1.5, data)["status"] == "REJECT"
    data["context_review"]["attractive_price_review"] = "verified"
    result = qualify_under35(.80, 1.5, data)
    assert result["status"] == "QUALIFY"
    assert result["selection_pool"] == "conditional"
    assert qualify_under35(.74, 2, data)["status"] == "REJECT"


@pytest.mark.parametrize("key", [key for key in THRESHOLDS if key != "projected_goals"])
def test_supporting_thresholds_are_advisory_not_hard_gates(key):
    data = evidence()
    direction, threshold = THRESHOLDS[key]
    data["metrics"][key] = threshold + (.01 if direction == "max" else -.01)
    result = qualify_under35(.85, 1.3, data)
    assert result["status"] == "QUALIFY"
    assert f"UNDER35_{key.upper()}_OUTSIDE" in result["warnings"]
    data["metrics"][key] = None
    assert qualify_under35(.85, 1.3, data)["status"] == "QUALIFY"


def test_core_projection_and_missing_reviews_are_blockers():
    data = evidence()
    data["metrics"]["projected_goals"] = 2.51
    assert "UNDER35_PROJECTED_GOALS_OUTSIDE" in qualify_under35(.85, 1.3, data)["reasons"]
    data = evidence()
    del data["context_review"]["sample_shrinkage"]
    assert "UNDER35_SAMPLE_SHRINKAGE_UNVERIFIED" in qualify_under35(.85, 1.3, data)["reasons"]
    assert qualify_under35(.99, 2)["status"] == "REJECT"


@pytest.mark.parametrize("key", RISK_CHECKS)
def test_explicit_four_goal_risks_block_release(key):
    data = evidence()
    data["risk_review"][key] = "flagged"
    assert f"UNDER35_{key.upper()}_FLAGGED" in qualify_under35(.85, 1.3, data)["reasons"]


def test_under25_calibration_or_snapshot_cannot_qualify_under35():
    data = evidence()
    data["calibration"]["market"] = "under_2.5"
    assert "UNDER35_CALIBRATION_UNVALIDATED" in qualify_under35(.85, 1.3, data)["reasons"]
    pred = SimpleNamespace(market="under_3.5", model_probability=.85, source_decimal_odds=1.3,
                           feature_snapshot={"under25_evidence": evidence()})
    assert prediction_qualification(pred)["status"] == "REJECT"


def test_market_pricing_and_relaxation_cannot_bypass_gate():
    from app.services.accumulator_builder import MARKET_TICKET_SPECS, _relax_spec, selection_rejection_reasons
    leg = SimpleNamespace(market="under_3.5", model_probability=.9, raw_model_probability=None,
                          best_odds=1.3, feature_snapshot={})
    for spec in MARKET_TICKET_SPECS:
        assert "UNDER35_CALIBRATION_UNVALIDATED" in selection_rejection_reasons(leg, _relax_spec(spec, 3))


@pytest.mark.parametrize("home,away,expected", [(0, 0, "won"), (2, 1, "won"), (3, 0, "won"),
                                                (2, 2, "lost"), (3, 1, "lost"), (4, 0, "lost")])
def test_regulation_score_boundaries(home, away, expected):
    from app.services.settlement import evaluate_selection
    assert evaluate_selection("under_3.5", home, away).value == expected
