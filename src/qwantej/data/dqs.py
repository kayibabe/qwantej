"""Data Quality Score (DQS) — framework §10.

DQS is a 0-100 composite gate on whether Qwantej has enough trustworthy,
temporally valid information to support a prediction for a fixture. It is
**not** a model probability — it is a filtering mechanism that runs before
any probability model does.

The framework names six components (completeness, freshness, provider
reliability, sample sufficiency, entity-match confidence, timestamp
validity) but does not specify their weights. The equal weighting below is
an explicit **research default** (see DEVELOPMENT.md §4: "external data
sources earn their place", and framework Appendix A: "these are starting
configuration values, not claims of optimality") — it must be backtested
and may be replaced by a learned/validated weighting once there is enough
settled history to justify one.
"""

import enum
from dataclasses import dataclass, fields


class DQSGrade(enum.StrEnum):
    EXCELLENT = "excellent"
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    REJECT = "reject"


@dataclass(frozen=True)
class DQSClassification:
    grade: DQSGrade
    default_action: str


# Framework §10's table, in descending score order. The upper bound of each
# band is implied by the lower bound of the one above it.
_DQS_BANDS: tuple[tuple[float, DQSClassification], ...] = (
    (90, DQSClassification(DQSGrade.EXCELLENT, "Eligible for all products subject to other gates")),
    (80, DQSClassification(DQSGrade.STRONG, "Eligible")),
    (70, DQSClassification(
        DQSGrade.ACCEPTABLE, "Eligible only if model/reliability/EV evidence is strong"
    )),
    (60, DQSClassification(DQSGrade.WEAK, "Normally reject; research only")),
    (0, DQSClassification(DQSGrade.REJECT, "Do not generate live betting candidates")),
)


@dataclass(frozen=True)
class DQSComponents:
    """Each component is a 0-100 sub-score. See framework §10 for what each
    measures; the exact per-component calculation (e.g. how "freshness"
    decays with data age) is left to the caller/data-ingestion layer — this
    module only owns the composite and the classification."""

    completeness: float
    freshness: float
    provider_reliability: float
    sample_sufficiency: float
    entity_match_confidence: float
    timestamp_validity: float

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if not 0 <= value <= 100:
                raise ValueError(f"DQSComponents.{f.name} must be in [0, 100], got {value}")


@dataclass(frozen=True)
class DQSWeights:
    """Research-default equal weighting across the six components. Must sum
    to 1.0 — construct via `DQSWeights()` for the default, or override
    explicitly once a backtested weighting scheme exists."""

    completeness: float = 1 / 6
    freshness: float = 1 / 6
    provider_reliability: float = 1 / 6
    sample_sufficiency: float = 1 / 6
    entity_match_confidence: float = 1 / 6
    timestamp_validity: float = 1 / 6

    def __post_init__(self) -> None:
        total = sum(getattr(self, f.name) for f in fields(self))
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"DQSWeights must sum to 1.0, got {total}")


def compute_dqs(components: DQSComponents, weights: DQSWeights | None = None) -> float:
    """Weighted composite DQS in [0, 100]."""
    weights = weights or DQSWeights()
    return sum(
        getattr(components, f.name) * getattr(weights, f.name) for f in fields(components)
    )


def classify_dqs(score: float) -> DQSClassification:
    """Map a DQS score to its framework §10 grade and default action."""
    if not 0 <= score <= 100:
        raise ValueError(f"DQS score must be in [0, 100], got {score}")
    for threshold, classification in _DQS_BANDS:
        if score >= threshold:
            return classification
    # Unreachable: the last band's threshold is 0, which always matches.
    raise AssertionError("unreachable")  # pragma: no cover
