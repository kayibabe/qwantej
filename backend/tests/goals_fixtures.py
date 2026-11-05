"""Shared fixtures for the total-goals qualification policies.

The production policies read their qualification probability from a promoted
shared total-goals forecast. Unit tests that exercise the grading and value
logic therefore need an explicit promoted forecast instead of relying on the
old pre-shared-forecast behaviour.
"""

from app.services.total_goals_engine import REQUIRED_SHARED_CHECKS


def promoted_shared_forecast(probabilities: dict[str, float]) -> dict:
    """Return a shared forecast that passes every promotion check."""
    return {
        "schema_version": "qwantej.total-goals-forecast.v1",
        "calibrated": True,
        "markets": dict(probabilities),
        "probability_checks": {
            "over_under_complements": True,
            "over_probabilities_monotone": True,
            "under_probabilities_monotone": True,
        },
        "calibration": {
            "status": "promoted",
            "profile_id": 1,
            "method": "total_goals_poisson_scale",
            "scale": 1.0,
            "checks": {key: True for key in REQUIRED_SHARED_CHECKS},
        },
    }
