"""Recency-weighted hierarchical reliability estimates (framework §25-27)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unit(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")


class ReliabilityStatus(StrEnum):
    QUALIFIED = "qualified"
    WATCH = "watch"
    RESTRICTED = "restricted"
    BLACKLISTED = "blacklisted"


@dataclass(frozen=True)
class ReliabilityPolicy:
    version: str = "reliability-v1"
    half_life_days: float = 180.0
    prior_strength: float = 100.0
    global_prior: float = 0.50
    confidence_z: float = 1.96
    minimum_qualified_effective_sample: float = 100.0
    qualified_lower_bound: float = 0.65
    watch_lower_bound: float = 0.55
    restricted_lower_bound: float = 0.45
    calibration_weight: float = 0.30
    roi_weight: float = 0.20
    clv_weight: float = 0.15
    variance_weight: float = 0.10
    drawdown_weight: float = 0.10
    stability_weight: float = 0.15

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("reliability policy version must not be blank")
        if not math.isfinite(self.half_life_days) or self.half_life_days <= 0:
            raise ValueError("half_life_days must be finite and positive")
        if not math.isfinite(self.prior_strength) or self.prior_strength <= 0:
            raise ValueError("prior_strength must be finite and positive")
        for name, value in (
            ("global_prior", self.global_prior),
            ("qualified_lower_bound", self.qualified_lower_bound),
            ("watch_lower_bound", self.watch_lower_bound),
            ("restricted_lower_bound", self.restricted_lower_bound),
        ):
            _unit(name, value)
        if not (
            self.qualified_lower_bound
            >= self.watch_lower_bound
            >= self.restricted_lower_bound
        ):
            raise ValueError("status thresholds must be descending")
        if (
            not math.isfinite(self.minimum_qualified_effective_sample)
            or self.minimum_qualified_effective_sample < 0
        ):
            raise ValueError("minimum qualified sample must be finite and non-negative")
        if not math.isfinite(self.confidence_z) or self.confidence_z < 0:
            raise ValueError("confidence_z must be finite and non-negative")
        component_weights = (
            self.calibration_weight,
            self.roi_weight,
            self.clv_weight,
            self.variance_weight,
            self.drawdown_weight,
            self.stability_weight,
        )
        if any(not math.isfinite(value) or value < 0 for value in component_weights):
            raise ValueError("component weights must be finite and non-negative")
        if not math.isclose(sum(component_weights), 1.0, abs_tol=1e-12):
            raise ValueError("component weights must sum to 1")


@dataclass(frozen=True)
class ReliabilityObservation:
    observation_id: str
    league: str
    market_family: str
    competition_class: str
    decision_as_of: datetime
    outcome_observed_at: datetime
    predicted_probability: float
    outcome: int
    profit_units: float
    closing_line_value: float | None
    model_stability: float

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.observation_id,
                self.league,
                self.market_family,
                self.competition_class,
            )
        ):
            raise ValueError("observation identity and segments must not be blank")
        _aware("decision_as_of", self.decision_as_of)
        _aware("outcome_observed_at", self.outcome_observed_at)
        if self.outcome_observed_at <= self.decision_as_of:
            raise ValueError("outcome must be observed after the decision")
        _unit("predicted_probability", self.predicted_probability)
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        if not math.isfinite(self.profit_units):
            raise ValueError("profit_units must be finite")
        if self.closing_line_value is not None and not math.isfinite(
            self.closing_line_value
        ):
            raise ValueError("closing_line_value must be finite when supplied")
        _unit("model_stability", self.model_stability)


@dataclass(frozen=True)
class ReliabilityComponents:
    calibration: float
    roi: float
    clv: float
    variance: float
    drawdown: float
    stability: float


@dataclass(frozen=True)
class ReliabilityEstimate:
    raw_score: float
    posterior_mean: float
    posterior_standard_deviation: float
    conservative_lower_bound: float
    shrinkage_weight: float
    observation_count: int
    effective_sample_size: float
    components: ReliabilityComponents
    status: ReliabilityStatus
    grade: str
    evaluated_as_of: datetime
    policy_version: str


@dataclass(frozen=True)
class ReliabilityCell:
    league: str
    market_family: str
    competition_class: str
    league_reliability: ReliabilityEstimate
    market_reliability: ReliabilityEstimate
    segment_reliability: ReliabilityEstimate


@dataclass(frozen=True)
class ReliabilityMatrix:
    evaluated_as_of: datetime
    policy_version: str
    global_reliability: ReliabilityEstimate
    cells: tuple[ReliabilityCell, ...]
    future_rows_excluded: int

    def find(self, league: str, market_family: str) -> ReliabilityCell | None:
        return next(
            (
                cell
                for cell in self.cells
                if cell.league == league and cell.market_family == market_family
            ),
            None,
        )


DEFAULT_RELIABILITY_POLICY = ReliabilityPolicy()


def build_reliability_matrix(
    observations: list[ReliabilityObservation],
    *,
    evaluated_as_of: datetime,
    policy: ReliabilityPolicy = DEFAULT_RELIABILITY_POLICY,
) -> ReliabilityMatrix:
    _aware("evaluated_as_of", evaluated_as_of)
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("observation_id values must be unique")
    eligible = [item for item in observations if item.outcome_observed_at <= evaluated_as_of]
    if not eligible:
        raise ValueError("no outcomes were observable at evaluated_as_of")
    future_count = len(observations) - len(eligible)
    global_estimate = _estimate(eligible, policy.global_prior, evaluated_as_of, policy)

    competition_estimates = {
        name: _estimate(
            [item for item in eligible if item.competition_class == name],
            global_estimate.posterior_mean,
            evaluated_as_of,
            policy,
        )
        for name in sorted({item.competition_class for item in eligible})
    }
    market_estimates = {
        name: _estimate(
            [item for item in eligible if item.market_family == name],
            global_estimate.posterior_mean,
            evaluated_as_of,
            policy,
        )
        for name in sorted({item.market_family for item in eligible})
    }
    league_estimates: dict[str, ReliabilityEstimate] = {}
    league_classes: dict[str, str] = {}
    for league in sorted({item.league for item in eligible}):
        league_rows = [item for item in eligible if item.league == league]
        classes = {item.competition_class for item in league_rows}
        if len(classes) != 1:
            raise ValueError("a league must map to exactly one competition_class")
        competition_class = classes.pop()
        league_classes[league] = competition_class
        league_estimates[league] = _estimate(
            league_rows,
            competition_estimates[competition_class].posterior_mean,
            evaluated_as_of,
            policy,
        )

    cells: list[ReliabilityCell] = []
    for league, market in sorted({(item.league, item.market_family) for item in eligible}):
        league_estimate = league_estimates[league]
        market_estimate = market_estimates[market]
        parent = _weighted_parent(league_estimate, market_estimate)
        segment = _estimate(
            [
                item
                for item in eligible
                if item.league == league and item.market_family == market
            ],
            parent,
            evaluated_as_of,
            policy,
        )
        cells.append(
            ReliabilityCell(
                league=league,
                market_family=market,
                competition_class=league_classes[league],
                league_reliability=league_estimate,
                market_reliability=market_estimate,
                segment_reliability=segment,
            )
        )
    return ReliabilityMatrix(
        evaluated_as_of=evaluated_as_of,
        policy_version=policy.version,
        global_reliability=global_estimate,
        cells=tuple(cells),
        future_rows_excluded=future_count,
    )


def _estimate(
    rows: list[ReliabilityObservation],
    parent_mean: float,
    evaluated_as_of: datetime,
    policy: ReliabilityPolicy,
) -> ReliabilityEstimate:
    weights = np.asarray(
        [
            0.5
            ** ((evaluated_as_of - item.outcome_observed_at).total_seconds() / 86400.0
                / policy.half_life_days)
            for item in rows
        ],
        dtype=float,
    )
    effective_sample = float(weights.sum())
    outcomes = np.asarray([item.outcome for item in rows], dtype=float)
    probabilities = np.asarray([item.predicted_probability for item in rows], dtype=float)
    profits = np.asarray([item.profit_units for item in rows], dtype=float)
    calibration = 1.0 - _weighted_mean(np.square(probabilities - outcomes), weights)
    roi = _clamp(0.5 + _weighted_mean(profits, weights) / 2.0)
    clv_rows = [
        (item.closing_line_value, weight)
        for item, weight in zip(rows, weights, strict=True)
        if item.closing_line_value is not None
    ]
    clv = (
        _clamp(
            0.5
            + 2.5
            * sum(float(value) * weight for value, weight in clv_rows)
            / sum(weight for _, weight in clv_rows)
        )
        if clv_rows
        else 0.5
    )
    profit_mean = _weighted_mean(profits, weights)
    profit_variance = _weighted_mean(np.square(profits - profit_mean), weights)
    variance = 1.0 / (1.0 + math.sqrt(profit_variance))
    drawdown = 1.0 / (
        1.0
        + _maximum_weighted_drawdown(rows, evaluated_as_of, policy)
        / max(1.0, effective_sample)
    )
    stability = _weighted_mean(
        np.asarray([item.model_stability for item in rows], dtype=float), weights
    )
    components = ReliabilityComponents(
        calibration=calibration,
        roi=roi,
        clv=clv,
        variance=variance,
        drawdown=drawdown,
        stability=stability,
    )
    raw = (
        policy.calibration_weight * calibration
        + policy.roi_weight * roi
        + policy.clv_weight * clv
        + policy.variance_weight * variance
        + policy.drawdown_weight * drawdown
        + policy.stability_weight * stability
    )
    shrinkage = effective_sample / (effective_sample + policy.prior_strength)
    posterior = shrinkage * raw + (1.0 - shrinkage) * parent_mean
    posterior_sd = math.sqrt(
        posterior * (1.0 - posterior) / (effective_sample + policy.prior_strength + 1.0)
    )
    lower = _clamp(posterior - policy.confidence_z * posterior_sd)
    status = _status(lower, effective_sample, policy)
    return ReliabilityEstimate(
        raw_score=raw,
        posterior_mean=posterior,
        posterior_standard_deviation=posterior_sd,
        conservative_lower_bound=lower,
        shrinkage_weight=shrinkage,
        observation_count=len(rows),
        effective_sample_size=effective_sample,
        components=components,
        status=status,
        grade=_grade(posterior),
        evaluated_as_of=evaluated_as_of,
        policy_version=policy.version,
    )


def _weighted_parent(
    league: ReliabilityEstimate, market: ReliabilityEstimate
) -> float:
    total = league.effective_sample_size + market.effective_sample_size
    if total == 0:
        return (league.posterior_mean + market.posterior_mean) / 2.0
    return (
        league.posterior_mean * league.effective_sample_size
        + market.posterior_mean * market.effective_sample_size
    ) / total


def _status(
    lower: float, effective_sample: float, policy: ReliabilityPolicy
) -> ReliabilityStatus:
    if (
        lower >= policy.qualified_lower_bound
        and effective_sample >= policy.minimum_qualified_effective_sample
    ):
        return ReliabilityStatus.QUALIFIED
    if lower >= policy.watch_lower_bound:
        return ReliabilityStatus.WATCH
    if lower >= policy.restricted_lower_bound:
        return ReliabilityStatus.RESTRICTED
    return ReliabilityStatus.BLACKLISTED


def _grade(score: float) -> str:
    if score >= 0.87:
        return "A+"
    if score >= 0.82:
        return "A"
    if score >= 0.77:
        return "B+"
    if score >= 0.72:
        return "B"
    return "Reject"


def _maximum_weighted_drawdown(
    rows: list[ReliabilityObservation],
    evaluated_as_of: datetime,
    policy: ReliabilityPolicy,
) -> float:
    cumulative = peak = maximum = 0.0
    for item in sorted(rows, key=lambda value: (value.decision_as_of, value.observation_id)):
        age_days = (evaluated_as_of - item.outcome_observed_at).total_seconds() / 86400.0
        weight = 0.5 ** (age_days / policy.half_life_days)
        cumulative += item.profit_units * weight
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.average(values, weights=weights))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
