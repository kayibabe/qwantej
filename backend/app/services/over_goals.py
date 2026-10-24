"""Provisional Over 1.5, 2.5 and 3.5 qualification policies.

Qualification probabilities come from the shared total-goals forecast. The
existing ensemble remains available for prediction/Q-score analysis. The shared
Poisson forecast is uncalibrated, so no selection can qualify until shared and
market-specific calibration plus adjusted evidence and context review pass.
"""

import math

from app.services.over45 import number
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICIES = {
    "over_1.5": {
        "suffix": "OVER15", "version": "over15-v1-provisional", "goals": 2,
        "grades": ((.95, "A+"), (.90, "A"), (.85, "B"), (.75, "C"), (0, "D")),
        "primary": ("A+", "A"), "preferred_goals": 3.2, "screen_goals": 2.8,
        "metrics": {"over15_frequency": .85, "over25_frequency": .60,
                     "over35_frequency": .35, "combined_shots_on_target": 8,
                     "combined_big_chances": 3, "max_team_projected_goals": 1.5,
                     "under05_frequency": .10, "first_half_over05_frequency": .70},
        "optional": ("btts_frequency",),
        "context": ("opponent_strength", "tactics_lineups", "xg_support"),
        "risks": ("weak_attacks", "strong_defences", "key_attacker_absence",
                  "finishing_above_xg", "cautious_tactics"),
    },
    "over_2.5": {
        "suffix": "OVER25", "version": "over25-v1-provisional", "goals": 3,
        "grades": ((.80, "A+"), (.70, "A"), (.60, "B"), (.50, "C"), (0, "D")),
        "primary": ("A+", "A"), "preferred_goals": 3.8, "screen_goals": 3.2,
        "metrics": {"over15_frequency": .85, "over25_frequency": .65,
                     "over35_frequency": .40, "over45_frequency": .20,
                     "combined_shots_on_target": 9, "combined_big_chances": 3.5,
                     "max_team_projected_goals": 1.7,
                     "first_half_over15_frequency": .40},
        "optional": ("btts_frequency",),
        "context": ("opponent_strength", "tactics_lineups", "xg_support", "game_state_review"),
        "risks": ("weak_attacks", "xg_mismatch", "possession_without_chances",
                  "strong_defences", "key_attacker_absence", "tactical_change",
                  "lineup_projection_drop"),
    },
    "over_3.5": {
        "suffix": "OVER35", "version": "over35-v1-provisional", "goals": 4,
        "grades": ((.65, "A+"), (.55, "A"), (.45, "B"), (.35, "C"), (0, "D")),
        "primary": ("A+", "A"), "preferred_goals": 4.2, "screen_goals": 3.8,
        "metrics": {"over25_frequency": .75, "over35_frequency": .45,
                     "over45_frequency": .25, "combined_shots_on_target": 10,
                     "combined_big_chances": 4, "historical_goals_profile": 3.5,
                     "max_team_projected_goals": 2.0,
                     "first_half_over15_frequency": .50},
        "optional": ("btts_frequency",),
        "context": ("opponent_strength", "tactics_lineups", "xg_support", "upper_tail_validation"),
        "risks": ("strong_defences", "xg_mismatch", "lead_protection", "key_attacker_absence",
                  "cautious_tactics", "weak_opponent_sample", "single_assumption_dependence"),
    },
}


def probability_grade(market, probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in POLICIES[market]["grades"] if p >= floor)


def poisson_over(total, goals):
    total = number(total)
    if total is None or not 0 <= total <= 100:
        return None
    return 1 - math.exp(-total) * sum(total ** k / math.factorial(k) for k in range(goals))


def qualify_over(market, probability, odds, evidence=None):
    policy = POLICIES[market]
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, market)
    if shared_probability is not None:
        probability = shared_probability
    metrics = evidence.get("metrics") or {}
    checks, reasons, warnings = [], [], []

    for key, threshold in (("projected_goals", policy["screen_goals"]), *policy["metrics"].items()):
        value = number(metrics.get(key))
        if value is not None and (value < 0 or (key.endswith("frequency") and value > 1)):
            value = None
        status = "missing" if value is None else "pass" if value >= threshold else "below"
        # The input framework presents these correlated screens as weighted
        # evidence. Only the projected total is a policy gate.
        required = key == "projected_goals"
        checks.append(dict(key=key, value=value, threshold=threshold, status=status,
                           required=required, direction="min"))
        if status != "pass":
            code = f"{policy['suffix']}_{key.upper()}_{status.upper()}"
            (reasons if required else warnings).append(code)

    for key in policy["optional"]:
        value = number(metrics.get(key))
        checks.append(dict(key=key, value=value, threshold=None,
                           status="missing" if value is None else "descriptive", required=False))

    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 8 <= counts[side] <= 12
           for side in ("home", "away")):
        reasons.append(f"{policy['suffix']}_INSUFFICIENT_RECENT_SAMPLE")

    calibration = evidence.get("calibration") or {}
    expected_checks = ("brier_improved", "calibration_not_worse", "enough_priced_bets",
                       "positive_roi_evidence", "roi_not_worse")
    market_calibrated = (calibration.get("market") == market and calibration.get("status") == "promoted"
                  and calibration.get("profile_id") is not None
                  and calibration.get("method") == "platt_logit"
                  and all((calibration.get("checks") or {}).get(key) is True for key in expected_checks))
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append(f"{policy['suffix']}_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append(f"{policy['suffix']}_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append(f"{policy['suffix']}_SHARED_GOALS_FORECAST_UNCALIBRATED")

    context = evidence.get("context_review") or {}
    for key in policy["context"]:
        if context.get(key) != "verified":
            reasons.append(f"{policy['suffix']}_{key.upper()}_UNVERIFIED")
    for key in policy["risks"]:
        state = (evidence.get("risk_review") or {}).get(key)
        if state != "clear":
            reasons.append(f"{policy['suffix']}_{key.upper()}_{'FLAGGED' if state == 'flagged' else 'UNREVIEWED'}")

    grade = probability_grade(market, probability)
    conditional_b = market == "over_2.5" and grade == "B" and context.get("strong_supporting_value") == "verified"
    if grade not in policy["primary"] and not conditional_b:
        reasons.append(f"{policy['suffix']}_PROBABILITY_BELOW_PRIMARY" if grade else f"{policy['suffix']}_PROBABILITY_MISSING")

    price = number(odds)
    ev = probability * price - 1 if grade and price is not None and price > 1 else None
    if ev is None or ev <= 0:
        reasons.append(f"{policy['suffix']}_NO_POSITIVE_EXPECTED_VALUE")

    projected = number(metrics.get("projected_goals"))
    shared = shared_forecast or evidence.get("shared_distribution") or {}
    shared_baseline = (shared.get("markets") or {}).get(market)
    return {
        "policy_version": policy["version"], "status": "REJECT" if reasons else "QUALIFY",
        "provisional": True, "grade": grade,
        "selection_pool": "primary" if grade in policy["primary"] else "conditional" if conditional_b else "excluded",
        "probability": probability if grade else None,
        "calibrated": calibrated, "expected_value": ev,
        "fair_odds": 1 / probability if grade and probability > 0 else None,
        "poisson_baseline": shared_baseline if number(shared_baseline) is not None else poisson_over(projected, policy["goals"]),
        "shared_distribution": shared or None,
        "shared_goals_forecast": shared_forecast,
        "probability_source": "shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
        "preferred_projection": projected is not None and projected >= policy["preferred_goals"],
        "checks": checks, "reasons": reasons, "warnings": warnings,
        "sample_sizes": counts, "source": evidence.get("source", "missing"),
        "descriptive_metrics": evidence.get("descriptive_metrics", {}),
    }


def initial_evidence(recent_evidence):
    """Keep raw history descriptive; adjusted features await validated pipeline."""
    return {"sample_sizes": recent_evidence.get("sample_sizes", {}),
            "match_ids": recent_evidence.get("match_ids", {}),
            "descriptive_metrics": recent_evidence.get("metrics", {}),
            "metrics": {}, "source": "adjusted_evidence_pending",
            "context_review": {}, "risk_review": {}}


def prediction_qualification(prediction):
    market = prediction.market
    if market not in POLICIES:
        return None
    evidence_key = {"over_1.5": "over15_evidence", "over_2.5": "over25_evidence",
                    "over_3.5": "over35_evidence"}[market]
    return qualify_over(market, prediction.model_probability, prediction.source_decimal_odds,
                        (prediction.feature_snapshot or {}).get(evidence_key))

