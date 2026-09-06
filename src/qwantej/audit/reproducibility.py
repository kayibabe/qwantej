"""Reproducibility check for archived predictions (framework §13, §51).

Framework §13 requires that every published prediction "remain reproducible
even after models, features or calibrators change". That is only possible if
the prediction carries its full *version spine* — the exact model, feature,
calibration, risk-policy and optimiser versions plus the code commit that
produced it. This module is the gate that decides whether a prediction meets
that bar.

It is deliberately decoupled from the ORM (like `qwantej.data.dqs`): it
accepts any object exposing the version-spine attributes, so the same check
runs over live ORM rows, backtest records or replayed archive exports alike.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# The version-spine fields that must all be present for a prediction to be
# reproducible. `prediction_timestamp` and `decision_as_of` are NOT NULL by
# construction on the `predictions` table, so they are not re-checked here.
REQUIRED_VERSION_FIELDS: tuple[str, ...] = (
    "model_version_id",
    "feature_version",
    "calibration_version",
    "risk_policy_version",
    "optimiser_version",
    "code_commit",
)


@runtime_checkable
class VersionedPrediction(Protocol):
    """Structural type: anything carrying the version spine can be checked."""

    model_version_id: object | None
    feature_version: str | None
    calibration_version: str | None
    risk_policy_version: str | None
    optimiser_version: str | None
    code_commit: str | None


@dataclass(frozen=True)
class ReproducibilityReport:
    """Result of a reproducibility check. Truthy iff reproducible, so callers
    can write `if check_reproducibility(pred): ...`."""

    reproducible: bool
    missing: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.reproducible


def _is_blank(value: object | None) -> bool:
    """A version field counts as missing if it is None or blank/whitespace."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def check_reproducibility(
    prediction: VersionedPrediction,
    required_fields: Sequence[str] = REQUIRED_VERSION_FIELDS,
) -> ReproducibilityReport:
    """Return which version-spine fields (if any) are missing from `prediction`.

    A prediction is reproducible only when every required field is present;
    the report lists exactly what is missing so an audit can say *why* a
    prediction cannot be reproduced, not merely that it cannot.
    """
    missing = tuple(
        name for name in required_fields if _is_blank(getattr(prediction, name, None))
    )
    return ReproducibilityReport(reproducible=not missing, missing=missing)
