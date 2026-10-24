import math

import pytest

from app.services.over45 import THRESHOLDS, probability_grade, qualify_over45, summarize_samples


def evidence():
    return {"metrics": dict(THRESHOLDS), "sample_sizes": {"home": 8, "away": 12},
            "calibration": {"status": "promoted", "profile_id": 1, "method": "platt_logit",
                            "checks": {"brier_improved": True, "calibration_not_worse": True}},
            "context_review": {"opponent_strength": "verified", "tactics_lineups": "verified"}}


@pytest.mark.parametrize("p,grade", [(0, "D"), (.1499, "D"), (.15, "C"), (.2499, "C"), (.25, "B"), (.35, "A"), (.45, "A+"), (1, "A+"), (math.nan, None), (1.1, None)])
def test_grades(p, grade):
    assert probability_grade(p) == grade


def test_btts_is_optional_and_poisson_is_only_baseline():
    data = evidence()
    data["metrics"]["btts_frequency"] = 0
    result = qualify_over45(.35, 3, data)
    assert result["status"] == "QUALIFY"
    assert result["expected_value"] == pytest.approx(.05)
    assert result["poisson_baseline"] == pytest.approx(.3321564)
    assert result["grade"] == "A"


@pytest.mark.parametrize("p,odds", [(.25, 4), (.45, 2), (.5, None), (.5, math.inf), (.2, 10)])
def test_no_value_or_low_probability_rejected(p, odds):
    assert qualify_over45(p, odds, evidence())["status"] == "REJECT"


def test_missing_evidence_and_uncalibrated_probabilities_do_not_qualify():
    assert qualify_over45(.9, 3)["status"] == "REJECT"
    data = evidence()
    data["calibration"]["method"] = "identity"
    assert "OVER45_CALIBRATION_UNVALIDATED" in qualify_over45(.5, 3, data)["reasons"]
    data = evidence()
    data["sample_sizes"]["home"] = 7
    assert "OVER45_INSUFFICIENT_RECENT_SAMPLE" in qualify_over45(.5, 3, data)["reasons"]
    data = evidence()
    data["metrics"]["projected_xg"] = None
    assert "OVER45_PROJECTED_XG_MISSING" in qualify_over45(.5, 3, data)["reasons"]


def test_venue_averages_and_missing_shots_are_not_invented():
    row = dict(id=1, scored=5, conceded=0, xg=4, xga=0, shots=None, ht=2)
    result = summarize_samples({"home": [row] * 8, "away": [row] * 12})
    assert result["metrics"]["over45_frequency"] == 1
    assert result["metrics"]["btts_frequency"] == 0
    assert result["metrics"]["projected_xg"] == 4
    assert result["metrics"]["combined_shots_on_target"] is None
    assert result["metrics"]["expected_first_half_goals"] == 2


def test_market_tier_and_relaxation_cannot_bypass_missing_evidence():
    from types import SimpleNamespace
    from app.services.accumulator_builder import MARKET_TICKET_SPECS, _relax_spec, selection_rejection_reasons
    leg = SimpleNamespace(market="over_4.5", model_probability=.5, raw_model_probability=None,
                          best_odds=3, feature_snapshot={})
    for spec in MARKET_TICKET_SPECS:
        assert "OVER45_CALIBRATION_UNVALIDATED" in selection_rejection_reasons(leg, _relax_spec(spec, 3))
