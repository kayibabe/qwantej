"""Provisional exact-zero qualification, including stressed expected value."""

import math

from app.services.over45 import number
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICY_VERSION = "under05-v1-provisional"
# Initial robustness scenario, not an empirically validated confidence bound.
PROBABILITY_HAIRCUT = .05
THRESHOLDS = {
    "projected_goals": ("max", 1.2),
    "home_projected_goals": ("max", .7),
    "away_projected_goals": ("max", .7),
    "zero_zero_frequency": ("min", .20),
    "under15_frequency": ("min", .55),
    "under25_frequency": ("min", .80),
    "combined_shots_on_target": ("max", 5),
    "combined_big_chances": ("max", 2),
    "btts_frequency": ("max", .25),
    "first_half_zero_zero_frequency": ("min", .45),
}
CONTEXT_CHECKS = (
    "opponent_adjusted_venue_history", "sample_shrinkage", "long_term_context",
    "league_validation", "exact_zero_calibration_validation", "uncertainty_validation",
    "both_team_clean_sheets", "limited_chance_creation", "defensive_stability",
    "measured_low_event_tactics", "lineups_conditions", "supporting_indicators_review",
)
RISK_CHECKS = (
    "attacking_favourite", "defender_goalkeeper_absences", "high_xg_poor_finishing",
    "early_goals_penalties_set_pieces", "pressing_transitions_shot_volume",
    "unsustainable_goalkeeping", "attacking_tactical_incentives", "unreliable_sample",
)


def probability_grade(probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in ((.40, "A+"), (.30, "A"), (.22, "B"), (.15, "C"), (0, "D")) if p >= floor)


def poisson_under05(total):
    total = number(total)
    return math.exp(-total) if total is not None and 0 <= total <= 100 else None


def qualify_under05(probability, odds, evidence=None):
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, "under_0.5")
    if shared_probability is not None:
        probability = shared_probability
    metrics = evidence.get("metrics") or {}
    checks, reasons, warnings = [], [], []
    for key, (direction, threshold) in THRESHOLDS.items():
        value = number(metrics.get(key))
        if value is not None and (value < 0 or (key.endswith("frequency") and value > 1)):
            value = None
        passed = value is not None and (value <= threshold if direction == "max" else value >= threshold)
        status = "missing" if value is None else "pass" if passed else "outside"
        checks.append(dict(key=key, value=value, threshold=threshold, direction=direction,
                           status=status, required=False))
        if not passed:
            warnings.append(f"UNDER05_{key.upper()}_{status.upper()}")
    home, away, total = (number(metrics.get(key)) for key in (
        "home_projected_goals", "away_projected_goals", "projected_goals"))
    if all(value is not None and value >= 0 for value in (home, away, total)) and not math.isclose(home + away, total, abs_tol=.01):
        reasons.append("UNDER05_INCONSISTENT_GOAL_PROJECTIONS")
    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 10 <= counts[side] <= 15 for side in ("home", "away")):
        reasons.append("UNDER05_INSUFFICIENT_RECENT_SAMPLE")
    context = evidence.get("context_review") or {}
    for key in CONTEXT_CHECKS:
        if context.get(key) != "verified":
            reasons.append(f"UNDER05_{key.upper()}_UNVERIFIED")
    for key in RISK_CHECKS:
        state = (evidence.get("risk_review") or {}).get(key)
        if state != "clear":
            reasons.append(f"UNDER05_{key.upper()}_{'FLAGGED' if state == 'flagged' else 'UNREVIEWED'}")
    calibration = evidence.get("calibration") or {}
    required_checks = ("brier_improved", "calibration_not_worse", "enough_priced_bets", "positive_roi_evidence", "roi_not_worse")
    market_calibrated = (calibration.get("market") == "under_0.5"
                  and calibration.get("status") == "promoted" and calibration.get("profile_id") is not None
                  and calibration.get("method") == "platt_logit"
                  and all((calibration.get("checks") or {}).get(key) is True for key in required_checks))
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append("UNDER05_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append("UNDER05_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append("UNDER05_SHARED_GOALS_FORECAST_UNCALIBRATED")
    grade = probability_grade(probability)
    if grade == "B":
        if context.get("conditional_value_review") != "verified":
            reasons.append("UNDER05_B_CONDITIONAL_VALUE_UNVERIFIED")
    elif grade not in ("A+", "A"):
        reasons.append("UNDER05_PROBABILITY_BELOW_22" if grade else "UNDER05_PROBABILITY_MISSING")
    price = number(odds)
    valid_price = price is not None and price > 1
    stressed_p = max(0.0, probability - PROBABILITY_HAIRCUT) if grade else None
    ev = probability * price - 1 if grade and valid_price else None
    stressed_ev = stressed_p * price - 1 if grade and valid_price else None
    if ev is None or ev <= 0:
        reasons.append("UNDER05_NO_POSITIVE_EXPECTED_VALUE")
    if stressed_ev is None or stressed_ev <= 0:
        reasons.append("UNDER05_NO_POSITIVE_STRESSED_VALUE")
    return dict(policy_version=POLICY_VERSION, provisional=True,
                status="REJECT" if reasons else "QUALIFY", grade=grade,
                selection_pool="primary" if grade in ("A+", "A") else "conditional" if grade == "B" else "excluded",
                probability=probability if grade else None,
                one_plus_probability=1 - probability if grade else None,
                calibrated=calibrated, expected_value=ev,
                stressed_probability=stressed_p, stressed_expected_value=stressed_ev,
                probability_haircut=PROBABILITY_HAIRCUT,
                implied_probability=1 / price if valid_price else None,
                edge=probability - 1 / price if grade and valid_price else None,
                fair_odds=1 / probability if grade and probability > 0 else None,
                poisson_baseline=shared_probability if shared_probability is not None else poisson_under05(total),
                probability_source="shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
                shared_goals_forecast=shared_forecast,
                preferred_projection=total is not None and 0 <= total <= .9,
                checks=checks, reasons=reasons, warnings=warnings, sample_sizes=counts,
                source=evidence.get("source", "missing"))


def prediction_qualification(prediction):
    if prediction.market != "under_0.5":
        return None
    return qualify_under05(prediction.model_probability, prediction.source_decimal_odds,
                           (prediction.feature_snapshot or {}).get("under05_evidence"))
