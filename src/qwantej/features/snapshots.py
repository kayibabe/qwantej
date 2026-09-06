"""Pure validation for the versioned feature-store contract."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TypeAlias

FeatureValue: TypeAlias = int | float | bool | str | None


def validate_feature_vector(features: Mapping[str, FeatureValue]) -> dict[str, FeatureValue]:
    """Return a key-sorted JSON feature vector or reject ambiguous inputs.

    Missing values must be represented explicitly as ``None``. Nested objects
    are intentionally excluded from the frozen v1 contract: each model input is
    a named scalar, which makes schema diffs and replay comparisons auditable.
    """

    if not features:
        raise ValueError("features must be a non-empty mapping")

    for name in features:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("feature names must be non-blank strings")

    normalized: dict[str, FeatureValue] = {}
    for name in sorted(features):
        value = features[name]
        if not isinstance(value, (int, float, bool, str, type(None))):
            raise ValueError(f"feature {name!r} must be a scalar or null")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"feature {name!r} must be finite")
        normalized[name] = value
    return normalized
