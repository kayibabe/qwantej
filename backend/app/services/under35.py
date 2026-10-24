"""Independent, provisional Under 3.5 qualification with advisory screens."""

import math

from app.services.over45 import number
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICY_VERSION = "under35-v1-provisional"
THRESHOLDS = {
    "projected_goals": ("max", 2.5),
    "historical_goals_profile": ("max", 2.7),
    "combined_shots_on_target": ("max", 9),
    "under25_frequency": ("min", .55),
    "under35_frequency": ("min", .80),
    "under45_frequency": ("min", .90),
    "over35_frequency": ("max", .20),
    "over45_frequency": ("max", .10),
    "btts_frequency": ("max", .55),
    "first_half_under15_frequency": ("min", .70),
}
CONTEXT_CHECKS = (
    "matchup_adjustment", "opponent_strength", "sample_shrinkage",
    "long_term_league_context", "league_validation", "upper_tail_validation",
    "defensive_stability", "controlled_transitions", "lineups_conditions",
    "supporting_indicators_review",
)
RISK_CHECKS = (
    "exceptional_chance_creation", "dominant_attack_vulnerable_defence",
    "defensive_absences", "fortunate_finishing", "dangerous_transitions",
    "lineup_goals_increase", "unexplained_market_disagreement",
)


def probability_grade(probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in ((.90, "A+"), (.82, "A"), (.75, "B"), (.65, "C"), (0, "D")) if p >= floor)


def poisson_under35(total):
    total = number(total)
    if total is None or not 0 <= total <= 100:
        return None
    return math.exp(-total) * (1 + total + total ** 2 / 2 + total ** 3 / 6)


def qualify_under35(probability, odds, evidence=None):
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, "under_3.5")
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
        # Projected goals is the initial core screen. Correlated historical
        # indicators are advisory, not an additive score or ten hard gates.
        required = key == "projected_goals"
        checks.append(dict(key=key, value=value, threshold=threshold, direction=direction,
                           status=status, required=required))
        if not passed:
            (reasons if required else warnings).append(f"UNDER35_{key.upper()}_{status.upper()}")
    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 8 <= counts[side] <= 12 for side in ("home", "away")):
        reasons.append("UNDER35_INSUFFICIENT_RECENT_SAMPLE")
    context = evidence.get("context_review") or {}
    for key in CONTEXT_CHECKS:
        if context.get(key) != "verified":
            reasons.append(f"UNDER35_{key.upper()}_UNVERIFIED")
    for key in RISK_CHECKS:
        state = (evidence.get("risk_review") or {}).get(key)
        if state != "clear":
            reasons.append(f"UNDER35_{key.upper()}_{'FLAGGED' if state == 'flagged' else 'UNREVIEWED'}")
    calibration = evidence.get("calibration") or {}
    required_checks = ("brier_improved", "calibration_not_worse", "enough_priced_bets", "positive_roi_evidence", "roi_not_worse")
    market_calibrated = (calibration.get("market") == "under_3.5"
                  and calibration.get("status") == "promoted" and calibration.get("profile_id") is not None
                  and calibration.get("method") == "platt_logit"
                  and all((calibration.get("checks") or {}).get(key) is True for key in required_checks))
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append("UNDER35_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append("UNDER35_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append("UNDER35_SHARED_GOALS_FORECAST_UNCALIBRATED")
    grade = probability_grade(probability)
    if grade == "B":
        for key in ("strong_supporting_evidence", "attractive_price_review"):
            if context.get(key) != "verified":
                reasons.append(f"UNDER35_B_{key.upper()}_UNVERIFIED")
    elif grade not in ("A+", "A"):
        reasons.append("UNDER35_PROBABILITY_BELOW_75" if grade else "UNDER35_PROBABILITY_MISSING")
    price = number(odds)
    ev = probability * price - 1 if grade and price is not None and price > 1 else None
    if ev is None or ev <= 0:
        reasons.append("UNDER35_NO_POSITIVE_EXPECTED_VALUE")
    projected = number(metrics.get("projected_goals"))
    return dict(policy_version=POLICY_VERSION, provisional=True,
                status="REJECT" if reasons else "QUALIFY", grade=grade,
                selection_pool="primary" if grade in ("A+", "A") else "conditional" if grade == "B" else "excluded",
                probability=probability if grade else None,
                four_plus_probability=1 - probability if grade else None,
                calibrated=calibrated, expected_value=ev,
                fair_odds=1 / probability if grade and probability > 0 else None,
                poisson_baseline=shared_probability if shared_probability is not None else poisson_under35(projected),
                probability_source="shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
                shared_goals_forecast=shared_forecast,
                preferred_projection=projected is not None and 0 <= projected <= 2.2,
                checks=checks, reasons=reasons, warnings=warnings, sample_sizes=counts,
                source=evidence.get("source", "missing"))


def prediction_qualification(prediction):
    if prediction.market != "under_3.5":
        return None
    return qualify_under35(prediction.model_probability, prediction.source_decimal_odds,
                           (prediction.feature_snapshot or {}).get("under35_evidence"))
