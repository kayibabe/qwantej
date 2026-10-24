"""Provisional Under 1.5 policy, separate from other total-goal markets."""

import math

from app.services.over45 import number
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICY_VERSION = "under15-v1-provisional"
THRESHOLDS = {
    "projected_goals": ("max", 1.2),
    "home_projected_goals": ("max", .7),
    "away_projected_goals": ("max", .6),
    "under15_frequency": ("min", .55),
    "under25_frequency": ("min", .80),
    "under35_frequency": ("min", .90),
    "combined_shots_on_target": ("max", 5),
    "btts_frequency": ("max", .25),
    "first_half_under05_frequency": ("min", .45),
    "first_half_under15_frequency": ("min", .85),
}
CONTEXT_CHECKS = (
    "comparable_venue_history", "opponent_strength", "league_shrinkage",
    "long_term_context", "league_validation", "low_score_validation",
    "low_big_chance_creation", "compact_defensive_structure", "measured_low_tempo",
    "lineups_conditions", "penalty_red_card_tactical_uncertainty",
)
RISK_CHECKS = (
    "high_individual_scoring_rate", "high_xg_despite_low_scores",
    "defender_goalkeeper_absences", "early_goals_conceded",
    "pressing_transitions_box_entries", "small_or_weak_opponent_sample",
    "unexplained_market_disagreement", "aggressive_lineup",
)


def probability_grade(probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in ((.80, "A+"), (.70, "A"), (.60, "B"), (.45, "C"), (0, "D")) if p >= floor)


def poisson_under15(total):
    total = number(total)
    if total is None or not 0 <= total <= 100:
        return None
    return math.exp(-total) * (1 + total)


def qualify_under15(probability, odds, evidence=None):
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, "under_1.5")
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
        required = key not in ("home_projected_goals", "away_projected_goals")
        checks.append(dict(key=key, value=value, threshold=threshold, direction=direction,
                           status=status, required=required))
        if not passed:
            (reasons if required else warnings).append(f"UNDER15_{key.upper()}_{status.upper()}")
    # Projections, when supplied, must describe the same combined forecast.
    home, away, total = (number(metrics.get(key)) for key in (
        "home_projected_goals", "away_projected_goals", "projected_goals"))
    if all(value is not None and value >= 0 for value in (home, away, total)) and not math.isclose(home + away, total, abs_tol=.01):
        reasons.append("UNDER15_INCONSISTENT_GOAL_PROJECTIONS")
    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 8 <= counts[side] <= 12 for side in ("home", "away")):
        reasons.append("UNDER15_INSUFFICIENT_RECENT_SAMPLE")
    context = evidence.get("context_review") or {}
    for key in CONTEXT_CHECKS:
        if context.get(key) != "verified":
            reasons.append(f"UNDER15_{key.upper()}_UNVERIFIED")
    for key in RISK_CHECKS:
        state = (evidence.get("risk_review") or {}).get(key)
        if state != "clear":
            reasons.append(f"UNDER15_{key.upper()}_{'FLAGGED' if state == 'flagged' else 'UNREVIEWED'}")
    calibration = evidence.get("calibration") or {}
    required_checks = ("brier_improved", "calibration_not_worse", "enough_priced_bets", "positive_roi_evidence", "roi_not_worse")
    market_calibrated = (calibration.get("market") == "under_1.5"
                  and calibration.get("status") == "promoted" and calibration.get("profile_id") is not None
                  and calibration.get("method") == "platt_logit"
                  and all((calibration.get("checks") or {}).get(key) is True for key in required_checks))
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append("UNDER15_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append("UNDER15_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append("UNDER15_SHARED_GOALS_FORECAST_UNCALIBRATED")
    grade = probability_grade(probability)
    if grade == "B":
        if context.get("compelling_value_review") != "verified":
            reasons.append("UNDER15_B_COMPELLING_VALUE_UNVERIFIED")
    elif grade not in ("A+", "A"):
        reasons.append("UNDER15_PROBABILITY_BELOW_60" if grade else "UNDER15_PROBABILITY_MISSING")
    price = number(odds)
    ev = probability * price - 1 if grade and price is not None and price > 1 else None
    if ev is None or ev <= 0:
        reasons.append("UNDER15_NO_POSITIVE_EXPECTED_VALUE")
    return dict(policy_version=POLICY_VERSION, provisional=True,
                status="REJECT" if reasons else "QUALIFY", grade=grade,
                selection_pool="primary" if grade in ("A+", "A") else "conditional" if grade == "B" else "excluded",
                probability=probability if grade else None,
                two_plus_probability=1 - probability if grade else None,
                calibrated=calibrated, expected_value=ev,
                fair_odds=1 / probability if grade and probability > 0 else None,
                poisson_baseline=shared_probability if shared_probability is not None else poisson_under15(total),
                probability_source="shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
                shared_goals_forecast=shared_forecast,
                low_score_model=evidence.get("low_score_model"),
                preferred_projection=total is not None and 0 <= total <= 1,
                checks=checks, reasons=reasons, warnings=warnings, sample_sizes=counts,
                source=evidence.get("source", "missing"))


def prediction_qualification(prediction):
    if prediction.market != "under_1.5":
        return None
    return qualify_under15(prediction.model_probability, prediction.source_decimal_odds,
                           (prediction.feature_snapshot or {}).get("under15_evidence"))
