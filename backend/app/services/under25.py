"""Provisional Under 2.5 screening; missing adjusted evidence fails closed."""

import math

from app.services.over45 import number
from app.services.total_goals_engine import probability_for_market, shared_calibration_is_promoted

POLICY_VERSION = "under25-v1-provisional"
THRESHOLDS = {
    "projected_xg": ("max", 2.0),
    "combined_scored": ("max", 2.2),
    "combined_conceded": ("max", 2.0),
    "under25_frequency": ("min", .70),
    "under35_frequency": ("min", .85),
    "over35_frequency": ("max", .15),
    "combined_shots_on_target": ("max", 7),
    "btts_frequency": ("max", .40),
    "first_half_under15_frequency": ("min", .80),
}
RISK_CHECKS = (
    "defensive_absences", "finishing_slump", "attacking_mismatch",
    "open_transitions", "aggressive_lineup", "unexplained_market_disagreement",
    "second_half_escalation",
)


def probability_grade(probability):
    p = number(probability)
    if p is None or not 0 <= p <= 1:
        return None
    return next(grade for floor, grade in ((.80, "A+"), (.72, "A"), (.65, "B"), (.55, "C"), (0, "D")) if p >= floor)


def poisson_under25(total):
    total = number(total)
    if total is None or not 0 <= total <= 100:
        return None
    return math.exp(-total) * (1 + total + total * total / 2)


def qualify_under25(probability, odds, evidence=None):
    evidence = evidence or {}
    shared_forecast = evidence.get("shared_goals_forecast")
    shared_probability = probability_for_market(shared_forecast, "under_2.5")
    if shared_probability is not None:
        probability = shared_probability
    metrics = evidence.get("metrics") or {}
    reasons, checks = [], []
    for key, (direction, threshold) in THRESHOLDS.items():
        value = number(metrics.get(key))
        if value is not None and (value < 0 or (key.endswith("frequency") and value > 1)):
            value = None
        passed = value is not None and (value <= threshold if direction == "max" else value >= threshold)
        status = "missing" if value is None else "pass" if passed else "outside"
        checks.append(dict(key=key, value=value, threshold=threshold, direction=direction, status=status))
        if not passed:
            reasons.append(f"UNDER25_{key.upper()}_{status.upper()}")
    counts = evidence.get("sample_sizes") or {}
    if any(number(counts.get(side)) is None or not 8 <= counts[side] <= 12 for side in ("home", "away")):
        reasons.append("UNDER25_INSUFFICIENT_RECENT_SAMPLE")
    for key in ("matchup_adjustment", "opponent_sample_weighting", "league_validation", "chance_quality", "defensive_stability", "controlled_tempo"):
        if (evidence.get("context_review") or {}).get(key) != "verified":
            reasons.append(f"UNDER25_{key.upper()}_UNVERIFIED")
    for key in RISK_CHECKS:
        state = (evidence.get("risk_review") or {}).get(key)
        if state != "clear":
            reasons.append(f"UNDER25_{key.upper()}_{'FLAGGED' if state == 'flagged' else 'UNREVIEWED'}")
    calibration = evidence.get("calibration") or {}
    required = ("brier_improved", "calibration_not_worse", "enough_priced_bets", "positive_roi_evidence", "roi_not_worse")
    market_calibrated = (calibration.get("status") == "promoted" and calibration.get("profile_id") is not None
                  and calibration.get("method") == "platt_logit"
                  and all((calibration.get("checks") or {}).get(key) is True for key in required))
    calibrated = market_calibrated and shared_calibration_is_promoted(shared_forecast)
    if not calibrated:
        reasons.append("UNDER25_CALIBRATION_UNVALIDATED")
    if shared_probability is None:
        reasons.append("UNDER25_SHARED_GOALS_FORECAST_MISSING")
    elif not shared_calibration_is_promoted(shared_forecast):
        reasons.append("UNDER25_SHARED_GOALS_FORECAST_UNCALIBRATED")
    grade = probability_grade(probability)
    if grade not in ("A+", "A"):
        reasons.append("UNDER25_PRIMARY_PROBABILITY_BELOW_72" if grade else "UNDER25_PROBABILITY_MISSING")
    price = number(odds)
    ev = probability * price - 1 if grade and price is not None and price > 1 else None
    if ev is None or ev <= 0:
        reasons.append("UNDER25_NO_POSITIVE_EXPECTED_VALUE")
    projected = number(metrics.get("projected_xg"))
    return dict(policy_version=POLICY_VERSION, provisional=True,
                status="REJECT" if reasons else "QUALIFY", grade=grade,
                probability=probability if grade else None, calibrated=calibrated,
                fair_odds=1 / probability if grade and probability > 0 else None,
                expected_value=ev, poisson_baseline=shared_probability if shared_probability is not None else poisson_under25(projected),
                probability_source="shared_goals_forecast" if shared_probability is not None else "market_ensemble_unshared",
                shared_goals_forecast=shared_forecast,
                preferred_projection=projected is not None and 0 <= projected <= 1.8,
                checks=checks, reasons=reasons, sample_sizes=counts,
                source=evidence.get("source", "missing"))


def prediction_qualification(prediction):
    if prediction.market != "under_2.5":
        return None
    return qualify_under25(prediction.model_probability, prediction.source_decimal_odds,
                           (prediction.feature_snapshot or {}).get("under25_evidence"))


def initial_evidence(recent_evidence):
    # Raw venue summaries are retained for research, not passed off as the
    # opponent-weighted, matchup-adjusted features required by this policy.
    return {"sample_sizes": recent_evidence.get("sample_sizes", {}),
            "match_ids": recent_evidence.get("match_ids", {}),
            "descriptive_metrics": recent_evidence.get("metrics", {}),
            "metrics": {}, "source": "adjusted_evidence_pending",
            "context_review": {}, "risk_review": {}}
