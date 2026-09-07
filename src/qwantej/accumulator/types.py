"""Core data types for the accumulator optimiser (framework §28–33)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from qwantej.bankroll.state import ProductTier


class AccumulatorRejectionReason(StrEnum):
    INSUFFICIENT_QUALIFIED_LEGS = "INSUFFICIENT_QUALIFIED_LEGS"
    NO_VALID_COMBINATION = "NO_VALID_COMBINATION"
    SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class AccumulatorLeg:
    """A single selection that has already passed the value gate."""

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
