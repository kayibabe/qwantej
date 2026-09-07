"""Explicit, reason-coded Qwantej Value Gate (framework §22)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from qwantej.value.calculations import expected_value, probability_edge


class ValueRejectionReason(StrEnum):
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    UNCERTAINTY_TOO_HIGH = "UNCERTAINTY_TOO_HIGH"
    MARKET_STALE = "MARKET_STALE"
    EDGE_TOO_LOW = "EDGE_TOO_LOW"
    EV_NON_POSITIVE = "EV_NON_POSITIVE"
    DATA_LOW_DQS = "DATA_LOW_DQS"
    RELIABILITY_LOW = "RELIABILITY_LOW"
    MODEL_UNSTABLE = "MODEL_UNSTABLE"
    ANOMALY_REVIEW = "ANOMALY_REVIEW"
    RISK_STATE_BLOCK = "RISK_STATE_BLOCK"


@dataclass(frozen=True)
class ValueGatePolicy:
    version: str = "value-gate-v1"
    minimum_conservative_probability: float = 0.50
    maximum_quote_age: timedelta = timedelta(hours=2)
    minimum_edge: float = 0.03
    minimum_expected_value: float = 0.02
    minimum_dqs: float = 70.0
    minimum_reliability: float = 60.0
    maximum_probability_change: float = 0.10
    maximum_model_disagreement: float = 0.15
    extreme_edge_threshold: float = 0.20

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Value Gate policy version must not be blank")
        for name, value in (
            ("minimum_conservative_probability", self.minimum_conservative_probability),
            ("minimum_edge", self.minimum_edge),
            ("maximum_probability_change", self.maximum_probability_change),
            ("maximum_model_disagreement", self.maximum_model_disagreement),
            ("extreme_edge_threshold", self.extreme_edge_threshold),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if (
            not math.isfinite(self.minimum_expected_value)
            or self.minimum_expected_value < 0
        ):
            raise ValueError("minimum_expected_value must be finite and non-negative")
        for name, value in (
            ("minimum_dqs", self.minimum_dqs),
            ("minimum_reliability", self.minimum_reliability),
        ):
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be finite and in [0, 100]")
        if self.maximum_quote_age < timedelta(0):
            raise ValueError("maximum_quote_age must be non-negative")
        if self.extreme_edge_threshold < self.minimum_edge:
            raise ValueError("extreme_edge_threshold must be at least minimum_edge")


@dataclass(frozen=True)
class ValueCandidate:
    decision_as_of: datetime
    calibrator_approved: bool
    calibrated_probability: float | None
    conservative_probability: float | None
    fair_market_probability: float | None
    executable_odds: float | None
    quote_timestamp: datetime | None
    data_quality_score: float
    league_reliability: float | None
    market_reliability: float | None
    probability_change: float
    model_disagreement: float
    league_reliability_status: str | None = None
    market_reliability_status: str | None = None
    unresolved_anomaly: bool = False
    risk_allowed: bool = True
    research_reliability_exception: bool = False

    def __post_init__(self) -> None:
        _aware("decision_as_of", self.decision_as_of)
        if self.quote_timestamp is not None:
            _aware("quote_timestamp", self.quote_timestamp)
            if self.quote_timestamp > self.decision_as_of:
                raise ValueError("quote_timestamp cannot be after decision_as_of")
        for name, value in (
            ("calibrated_probability", self.calibrated_probability),
            ("conservative_probability", self.conservative_probability),
            ("fair_market_probability", self.fair_market_probability),
        ):
            if value is not None:
                _unit(name, value)
        if self.executable_odds is not None and (
            not math.isfinite(self.executable_odds) or self.executable_odds <= 1
        ):
            raise ValueError("executable_odds must be finite decimal odds > 1")
        if not math.isfinite(self.data_quality_score) or not 0 <= self.data_quality_score <= 100:
            raise ValueError("data_quality_score must be finite and in [0, 100]")
        for name, value in (
            ("league_reliability", self.league_reliability),
            ("market_reliability", self.market_reliability),
        ):
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 100):
                raise ValueError(f"{name} must be finite and in [0, 100]")
        _unit("probability_change", self.probability_change)
        _unit("model_disagreement", self.model_disagreement)
        valid_states = {"qualified", "watch", "restricted", "blacklisted"}
        for state_name, state_value in (
            ("league_reliability_status", self.league_reliability_status),
            ("market_reliability_status", self.market_reliability_status),
        ):
            if state_value is not None and state_value not in valid_states:
                raise ValueError(f"{state_name} is not a valid reliability state")


@dataclass(frozen=True)
class ValueGateResult:
    passed: bool
    edge: float | None
    expected_value: float | None
    reason_codes: tuple[ValueRejectionReason, ...]
    policy_version: str


DEFAULT_VALUE_GATE_POLICY = ValueGatePolicy()


def evaluate_value_gate(
    candidate: ValueCandidate, policy: ValueGatePolicy = DEFAULT_VALUE_GATE_POLICY
) -> ValueGateResult:
    reasons: list[ValueRejectionReason] = []
    if not candidate.calibrator_approved or candidate.calibrated_probability is None:
        reasons.append(ValueRejectionReason.CALIBRATION_UNAVAILABLE)
    if (
        candidate.conservative_probability is None
        or candidate.conservative_probability < policy.minimum_conservative_probability
    ):
        reasons.append(ValueRejectionReason.UNCERTAINTY_TOO_HIGH)

    market_available = (
        candidate.executable_odds is not None
        and candidate.fair_market_probability is not None
        and candidate.quote_timestamp is not None
        and candidate.decision_as_of - candidate.quote_timestamp <= policy.maximum_quote_age
    )
    if not market_available:
        reasons.append(ValueRejectionReason.MARKET_STALE)

    edge: float | None = None
    ev: float | None = None
    if candidate.conservative_probability is not None and market_available:
        assert candidate.fair_market_probability is not None
        assert candidate.executable_odds is not None
        edge = probability_edge(
            candidate.conservative_probability, candidate.fair_market_probability
        )
        ev = expected_value(candidate.conservative_probability, candidate.executable_odds)
        if edge < policy.minimum_edge:
            reasons.append(ValueRejectionReason.EDGE_TOO_LOW)
        if ev < policy.minimum_expected_value:
            reasons.append(ValueRejectionReason.EV_NON_POSITIVE)
        if edge > policy.extreme_edge_threshold:
            reasons.append(ValueRejectionReason.ANOMALY_REVIEW)

    if candidate.data_quality_score < policy.minimum_dqs:
        reasons.append(ValueRejectionReason.DATA_LOW_DQS)
    reliability_values = (
        candidate.league_reliability,
        candidate.market_reliability,
    )
    reliability_states = (
        candidate.league_reliability_status,
        candidate.market_reliability_status,
    )
    if not candidate.research_reliability_exception and (
        any(value is None for value in reliability_values)
        or any(
            value is not None and value < policy.minimum_reliability
            for value in reliability_values
        )
        or any(value in {"restricted", "blacklisted"} for value in reliability_states)
    ):
        reasons.append(ValueRejectionReason.RELIABILITY_LOW)
    if (
        candidate.probability_change > policy.maximum_probability_change
        or candidate.model_disagreement > policy.maximum_model_disagreement
    ):
        reasons.append(ValueRejectionReason.MODEL_UNSTABLE)
    if candidate.unresolved_anomaly and ValueRejectionReason.ANOMALY_REVIEW not in reasons:
        reasons.append(ValueRejectionReason.ANOMALY_REVIEW)
    if not candidate.risk_allowed:
        reasons.append(ValueRejectionReason.RISK_STATE_BLOCK)
    return ValueGateResult(
        passed=not reasons,
        edge=edge,
        expected_value=ev,
        reason_codes=tuple(reasons),
        policy_version=policy.version,
    )


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unit(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
