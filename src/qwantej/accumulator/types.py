"""Core data types for the accumulator optimiser (framework §28–33)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from qwantej.bankroll.state import ProductTier


class AccumulatorRejectionReason(StrEnum):
    INSUFFICIENT_QUALIFIED_LEGS = "INSUFFICIENT_QUALIFIED_LEGS"
    NO_VALID_COMBINATION = "NO_VALID_COMBINATION"


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


@dataclass(frozen=True)
class AccumulatorTicket:
    """A validated, scored accumulator ticket ready for staking."""

    legs: tuple[AccumulatorLeg, ...]
    product: ProductTier
    combined_odds: Decimal
    conservative_joint_probability: float
    objective_score: float
    dependence_penalty_applied: float
