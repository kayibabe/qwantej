"""One internally consistent independent-Poisson total-goals baseline.

This distribution is an explainability diagnostic until a shared calibration
profile passes its chronological holdout and the market-specific gates pass.
"""

import math


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

MARKETS = {
    "under_0.5": ("under", 0), "over_1.5": ("over", 2), "under_1.5": ("under", 1),
    "over_2.5": ("over", 3), "under_2.5": ("under", 2), "over_3.5": ("over", 4),
    "under_3.5": ("under", 3), "over_4.5": ("over", 5),
}
SHARED_CALIBRATION_MARKET = "shared_total_goals"

REQUIRED_SHARED_CHECKS = (
    "brier_improved", "calibration_not_worse", "enough_priced_bets",
    "probability_ordering", "positive_roi_evidence", "roi_not_worse",
    "chronological_holdout_passed", "market_brier_not_worse",
    "market_calibration_not_worse",
)


def total_goals_distribution(home_goals, away_goals):
    home, away = number(home_goals), number(away_goals)
    if home is None or away is None or not 0 <= home <= 20 or not 0 <= away <= 20:
        return None
    total = home + away
    return total_goals_distribution_from_mean(total, home, away)


def total_goals_distribution_from_mean(total_mean, home_projected=None, away_projected=None):
    total = number(total_mean)
    if total is None or not 0 <= total <= 40:
        return None
    probabilities = {}
    for market, (direction, threshold) in MARKETS.items():
        maximum = threshold - 1 if direction == "over" else threshold
        cdf = math.exp(-total) * sum(total ** k / math.factorial(k) for k in range(maximum + 1))
        probabilities[market] = 1 - cdf if direction == "over" else cdf
    probability_checks = {
        "over_under_complements": all(
            abs(probabilities[f"over_{line}.5"] + probabilities[f"under_{line}.5"] - 1) < 1e-12
            for line in (1, 2, 3)
        ),
        "over_probabilities_monotone": (
            probabilities["over_1.5"] >= probabilities["over_2.5"] >=
            probabilities["over_3.5"] >= probabilities["over_4.5"]
        ),
        "under_probabilities_monotone": (
            probabilities["under_0.5"] <= probabilities["under_1.5"] <=
            probabilities["under_2.5"] <= probabilities["under_3.5"]
        ),
    }
    return {
        "schema_version": "qwantej.total-goals-forecast.v1",
        "source": "independent_poisson_expected_goals_diagnostic",
        "calibrated": False,
        "home_projected_goals": number(home_projected),
        "away_projected_goals": number(away_projected),
        "combined_projected_goals": total,
        "markets": probabilities,
        "probability_checks": probability_checks,
        "calibration": {"status": "unvalidated", "profile_id": None, "checks": {}},
    }


def apply_shared_total_goals_calibration(forecast, profile):
    """Apply a promoted shared calibration profile to one coherent distribution."""
    if not isinstance(forecast, dict) or not profile:
        return forecast
    calibrator = profile.calibrator or {}
    if calibrator.get("type") != "total_goals_poisson_scale":
        return forecast
    scale = number(calibrator.get("scale"))
    total = number(forecast.get("combined_projected_goals"))
    if scale is None or total is None or scale <= 0:
        return forecast
    calibrated = total_goals_distribution_from_mean(
        total * scale,
        number(forecast.get("home_projected_goals")) * scale
        if number(forecast.get("home_projected_goals")) is not None else None,
        number(forecast.get("away_projected_goals")) * scale
        if number(forecast.get("away_projected_goals")) is not None else None,
    )
    if calibrated is None:
        return forecast
    calibrated.update({key: value for key, value in forecast.items() if key not in calibrated})
    calibrated["combined_projected_goals"] = total * scale
    calibrated["raw_combined_projected_goals"] = total
    calibrated["raw_home_projected_goals"] = forecast.get("home_projected_goals")
    calibrated["raw_away_projected_goals"] = forecast.get("away_projected_goals")
    calibrated["source"] = "shared_calibrated_poisson_total_goals"
    calibrated["calibrated"] = profile.status == "shadow_ready"
    calibrated["calibration"] = {
        "status": "promoted" if profile.status == "shadow_ready" else profile.status,
        "profile_id": profile.id,
        "method": calibrator.get("type"),
        "scale": scale,
        "checks": profile.promotion_checks or {},
        "validation_metrics": profile.validation_metrics or {},
    }
    return calibrated


def probability_for_market(forecast, market):
    """Return a validated event probability from a shared forecast snapshot."""
    if not isinstance(forecast, dict) or forecast.get("schema_version") != "qwantej.total-goals-forecast.v1":
        return None
    value = number((forecast.get("markets") or {}).get(market))
    return value if value is not None and 0 <= value <= 1 else None


def shared_calibration_is_promoted(forecast):
    if not isinstance(forecast, dict):
        return False
    calibration = forecast.get("calibration") or {}
    probability_checks = forecast.get("probability_checks") or {}
    return (
        forecast.get("calibrated") is True
        and calibration.get("method") == "total_goals_poisson_scale"
        and (number(calibration.get("scale")) or 0) > 0
        and all(probability_checks.get(key) is True for key in (
            "over_under_complements", "over_probabilities_monotone", "under_probabilities_monotone"
        ))
        and calibration.get("status") == "promoted"
        and calibration.get("profile_id") is not None
        and all((calibration.get("checks") or {}).get(key) is True for key in REQUIRED_SHARED_CHECKS)
    )
