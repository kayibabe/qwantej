"""Drawdown-aware operating state and the risk policy (framework §34-37).

The operating state can only ever *reduce* risk relative to NORMAL: each state
carries a stake multiplier that is monotonically non-increasing as conditions
worsen, and REVIEW suspends staking entirely. There is deliberately no state
that increases stakes to recover losses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


class OperatingState(StrEnum):
    NORMAL = "normal"
    CAUTION = "caution"
    DEFENSIVE = "defensive"
    REVIEW = "review"


class ProductTier(StrEnum):
    CORE = "core"
    GROWTH = "growth"
    ALPHA = "alpha"


def _default_state_multipliers() -> dict[OperatingState, float]:
    return {
        OperatingState.NORMAL: 1.0,
        OperatingState.CAUTION: 0.50,
        OperatingState.DEFENSIVE: 0.25,
        OperatingState.REVIEW: 0.0,
    }


def _default_product_allocations() -> dict[ProductTier, float]:
    return {
        ProductTier.CORE: 1.0,
        ProductTier.GROWTH: 0.60,
        ProductTier.ALPHA: 0.30,
    }


@dataclass(frozen=True)
class RiskPolicy:
    version: str = "risk-v1"
    kelly_multiplier: float = 0.25
    single_ticket_cap: float = 0.02
    daily_exposure_cap: float = 0.05
    caution_drawdown: float = 0.10
    defensive_drawdown: float = 0.15
    review_drawdown: float = 0.20
    minimum_stake_fraction: float = 0.001
    stake_rounding: int = 2
    state_multipliers: dict[OperatingState, float] = field(
        default_factory=_default_state_multipliers
    )
    product_allocations: dict[ProductTier, float] = field(
        default_factory=_default_product_allocations
    )

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version must not be blank")
        if not math.isfinite(self.kelly_multiplier) or not 0 < self.kelly_multiplier <= 1:
            raise ValueError("kelly_multiplier must be finite and in (0, 1]")
        for name, value in (
            ("single_ticket_cap", self.single_ticket_cap),
            ("daily_exposure_cap", self.daily_exposure_cap),
            ("minimum_stake_fraction", self.minimum_stake_fraction),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if self.single_ticket_cap > self.daily_exposure_cap:
            raise ValueError("single_ticket_cap cannot exceed daily_exposure_cap")
        for name, value in (
            ("caution_drawdown", self.caution_drawdown),
            ("defensive_drawdown", self.defensive_drawdown),
            ("review_drawdown", self.review_drawdown),
        ):
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite and in (0, 1]")
        if not (
            self.caution_drawdown < self.defensive_drawdown < self.review_drawdown
        ):
            raise ValueError("drawdown thresholds must be strictly ascending")
        if self.stake_rounding < 0:
            raise ValueError("stake_rounding must be non-negative")
        if set(self.state_multipliers) != set(OperatingState):
            raise ValueError("state_multipliers must cover every operating state")
        if set(self.product_allocations) != set(ProductTier):
            raise ValueError("product_allocations must cover every product tier")
        for value in (*self.state_multipliers.values(), *self.product_allocations.values()):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("multipliers/allocations must be finite and in [0, 1]")
        ordered = [
            self.state_multipliers[state]
            for state in (
                OperatingState.NORMAL,
                OperatingState.CAUTION,
                OperatingState.DEFENSIVE,
                OperatingState.REVIEW,
            )
        ]
        if ordered != sorted(ordered, reverse=True):
            raise ValueError(
                "state multipliers must be non-increasing from NORMAL to REVIEW"
            )
        if self.state_multipliers[OperatingState.REVIEW] != 0.0:
            raise ValueError("REVIEW must suspend staking (multiplier 0)")

    def state_multiplier(self, state: OperatingState) -> float:
        return self.state_multipliers[state]

    def allocation(self, product: ProductTier) -> float:
        return self.product_allocations[product]


DEFAULT_RISK_POLICY = RiskPolicy()


def classify_state(
    drawdown_fraction: float,
    *,
    policy: RiskPolicy = DEFAULT_RISK_POLICY,
    calibration_failure: bool = False,
    severe_drift: bool = False,
    drift: bool = False,
    soft_deterioration: bool = False,
) -> OperatingState:
    """Map current drawdown and qualitative signals to an operating state.

    Drawdown thresholds are policy anchors, not the only trigger: a calibration
    failure or severe drift forces REVIEW regardless of drawdown (framework
    §36), lighter drift forces at least DEFENSIVE, and soft deterioration forces
    at least CAUTION.
    """

    if not math.isfinite(drawdown_fraction) or not 0 <= drawdown_fraction <= 1:
        raise ValueError("drawdown_fraction must be finite and in [0, 1]")
    if calibration_failure or severe_drift or drawdown_fraction >= policy.review_drawdown:
        return OperatingState.REVIEW
    if drift or drawdown_fraction >= policy.defensive_drawdown:
        return OperatingState.DEFENSIVE
    if soft_deterioration or drawdown_fraction >= policy.caution_drawdown:
        return OperatingState.CAUTION
    return OperatingState.NORMAL
