"""Core data types for the accumulator optimiser (framework §28–33)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from qwantej.bankroll.state import ProductTier


@dataclass(frozen=True)
class QualifiedSelection:
    """A prediction that passed the value gate and is ready for accumulator consideration.

    Carries full model/data lineage so every downstream decision is traceable.
    `quote_timestamp` drives price-freshness checks inside the leg gate.
    """

    prediction_id: str
    fixture_id: str
    league_id: str
    market_family: str
    selection: str
    calibrated_probability: float
    conservative_probability: float
    decimal_odds: Decimal
    edge: float
    qss: float
    dqs: float
    reliability: float
    quote_timestamp: datetime
    model_version: str
    calibration_version: str
    feature_version: str
    code_commit: str
    input_snapshot_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("prediction_id", self.prediction_id),
            ("fixture_id", self.fixture_id),
            ("league_id", self.league_id),
            ("market_family", self.market_family),
            ("selection", self.selection),
            ("model_version", self.model_version),
            ("calibration_version", self.calibration_version),
            ("feature_version", self.feature_version),
            ("code_commit", self.code_commit),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-blank string")
        if not isinstance(self.decimal_odds, Decimal):
            raise ValueError("decimal_odds must be a Decimal")
        if not self.decimal_odds.is_finite() or self.decimal_odds <= 1:
            raise ValueError("decimal_odds must be a finite Decimal > 1")
        # Use distinct loop variables per block so mypy can infer each type correctly.
        for prob_name, prob_val in (
            ("calibrated_probability", self.calibrated_probability),
            ("conservative_probability", self.conservative_probability),
        ):
            if not math.isfinite(prob_val) or not 0 < prob_val <= 1:
                raise ValueError(f"{prob_name} must be finite and in (0, 1]")
        for score_name, score_val in (
            ("edge", self.edge),
            ("qss", self.qss),
            ("dqs", self.dqs),
            ("reliability", self.reliability),
        ):
            if not math.isfinite(score_val):
                raise ValueError(f"{score_name} must be a finite number")
        for band_name, band_val in (
            ("qss", self.qss),
            ("dqs", self.dqs),
            ("reliability", self.reliability),
        ):
            if not 0 <= band_val <= 100:
                raise ValueError(f"{band_name} must be in [0, 100]")
        if self.quote_timestamp.tzinfo is None or self.quote_timestamp.utcoffset() is None:
            raise ValueError("quote_timestamp must be timezone-aware")

    def to_leg(self) -> AccumulatorLeg:
        """Return an AccumulatorLeg for the optimiser, using quote_timestamp as captured_at."""
        return AccumulatorLeg(
            prediction_id=self.prediction_id,
            fixture_id=self.fixture_id,
            league_id=self.league_id,
            market_family=self.market_family,
            selection=self.selection,
            decimal_odds=self.decimal_odds,
            conservative_probability=self.conservative_probability,
            edge=self.edge,
            qss=self.qss,
            dqs=self.dqs,
            reliability=self.reliability,
            captured_at=self.quote_timestamp,
        )


class AccumulatorRejectionReason(StrEnum):
    INSUFFICIENT_QUALIFIED_LEGS = "INSUFFICIENT_QUALIFIED_LEGS"
    NO_VALID_COMBINATION = "NO_VALID_COMBINATION"
    SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class AccumulatorLeg:
    """A single selection that has already passed the value gate."""

    prediction_id: str
    fixture_id: str
    league_id: str
    market_family: str
    selection: str
    decimal_odds: Decimal
    conservative_probability: float
    edge: float
    qss: float
    dqs: float
    reliability: float
    captured_at: datetime

    def __post_init__(self) -> None:
        for field, value in (
            ("prediction_id", self.prediction_id),
            ("fixture_id", self.fixture_id),
            ("league_id", self.league_id),
            ("market_family", self.market_family),
            ("selection", self.selection),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-blank string")
        if not isinstance(self.decimal_odds, Decimal):
            raise ValueError("decimal_odds must be a Decimal")
        try:
            _check_finite_decimal("decimal_odds", self.decimal_odds)
        except ValueError:
            raise
        if self.decimal_odds <= 1:
            raise ValueError("decimal_odds must be greater than 1")
        _check_finite_float("conservative_probability", self.conservative_probability)
        if not 0 < self.conservative_probability <= 1:
            raise ValueError("conservative_probability must be in (0, 1]")
        _check_finite_float("edge", self.edge)
        for _fname, _fval in (
            ("qss", self.qss), ("dqs", self.dqs), ("reliability", self.reliability)
        ):
            _check_finite_float(_fname, _fval)
            if not 0 <= _fval <= 100:
                raise ValueError(f"{_fname} must be in [0, 100]")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")


@dataclass(frozen=True)
class AccumulatorTicket:
    """A validated, scored accumulator ticket ready for staking."""

    legs: tuple[AccumulatorLeg, ...]
    product: ProductTier
    combined_odds: Decimal
    conservative_joint_probability: float
    stressed_joint_probability: float
    objective_score: float
    dependence_penalty_applied: float


def _check_finite_float(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")


def _check_finite_decimal(name: str, value: Decimal) -> None:
    if not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal, got {value!r}")
