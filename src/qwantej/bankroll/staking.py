"""Reason-coded recommended-stake pipeline (framework §34-36).

Turns a ticket's edge into a concrete stake by composing, in order:

    full Kelly → fractional Kelly → operating-state multiplier →
    product allocation → single-ticket cap → remaining daily-exposure cap →
    available-bankroll cap → minimum-stake floor

Every binding constraint is recorded so the decision is auditable, and every
rejection carries an explicit reason code. The recommended stake is a pure
function of edge, odds, bankroll and operating state; nothing here can grow a
stake in response to prior losses (no Martingale — framework §35).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from qwantej.bankroll.kelly import kelly_fraction
from qwantej.bankroll.state import (
    DEFAULT_RISK_POLICY,
    OperatingState,
    ProductTier,
    RiskPolicy,
)


class StakeRejectionReason(StrEnum):
    REVIEW_STATE_SUSPENDED = "REVIEW_STATE_SUSPENDED"
    NON_POSITIVE_EDGE = "NON_POSITIVE_EDGE"
    DAILY_EXPOSURE_EXHAUSTED = "DAILY_EXPOSURE_EXHAUSTED"
    INSUFFICIENT_AVAILABLE_BANKROLL = "INSUFFICIENT_AVAILABLE_BANKROLL"
    BELOW_MINIMUM_STAKE = "BELOW_MINIMUM_STAKE"


class AppliedCap(StrEnum):
    STATE_MULTIPLIER = "STATE_MULTIPLIER"
    PRODUCT_ALLOCATION = "PRODUCT_ALLOCATION"
    SINGLE_TICKET_CAP = "SINGLE_TICKET_CAP"
    DAILY_EXPOSURE_CAP = "DAILY_EXPOSURE_CAP"
    AVAILABLE_BANKROLL = "AVAILABLE_BANKROLL"


@dataclass(frozen=True)
class StakeCandidate:
    ticket_probability: float
    decimal_odds: float
    product: ProductTier
    current_bankroll: float
    available_bankroll: float
    committed_daily_exposure: float
    operating_state: OperatingState
    minimum_stake: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.ticket_probability) or not 0 < self.ticket_probability <= 1:
            raise ValueError("ticket_probability must be finite and in (0, 1]")
        if not math.isfinite(self.decimal_odds) or self.decimal_odds <= 1:
            raise ValueError("decimal_odds must be finite decimal odds > 1")
        for name, value in (
            ("current_bankroll", self.current_bankroll),
            ("available_bankroll", self.available_bankroll),
            ("committed_daily_exposure", self.committed_daily_exposure),
            ("minimum_stake", self.minimum_stake),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.available_bankroll > self.current_bankroll:
            raise ValueError("available_bankroll cannot exceed current_bankroll")


@dataclass(frozen=True)
class StakeDecision:
    approved: bool
    recommended_stake: float
    stake_fraction: float
    kelly_fraction: float
    fractional_kelly: float
    operating_state: OperatingState
    applied_caps: tuple[AppliedCap, ...]
    reason_codes: tuple[StakeRejectionReason, ...]
    policy_version: str


def recommend_stake(
    candidate: StakeCandidate, policy: RiskPolicy = DEFAULT_RISK_POLICY
) -> StakeDecision:
    reasons: list[StakeRejectionReason] = []
    caps: list[AppliedCap] = []

    full_kelly = kelly_fraction(candidate.ticket_probability, candidate.decimal_odds)
    scaled_kelly = policy.kelly_multiplier * full_kelly
    if full_kelly <= 0.0:
        reasons.append(StakeRejectionReason.NON_POSITIVE_EDGE)

    state_multiplier = policy.state_multiplier(candidate.operating_state)
    product_allocation = policy.allocation(candidate.product)
    target_fraction = scaled_kelly * state_multiplier * product_allocation
    if state_multiplier < 1.0 and scaled_kelly > 0.0:
        caps.append(AppliedCap.STATE_MULTIPLIER)
    if product_allocation < 1.0 and scaled_kelly > 0.0:
        caps.append(AppliedCap.PRODUCT_ALLOCATION)
    if candidate.operating_state is OperatingState.REVIEW:
        reasons.append(StakeRejectionReason.REVIEW_STATE_SUSPENDED)

    if target_fraction > policy.single_ticket_cap:
        target_fraction = policy.single_ticket_cap
        caps.append(AppliedCap.SINGLE_TICKET_CAP)

    stake = target_fraction * candidate.current_bankroll

    remaining_daily = (
        policy.daily_exposure_cap * candidate.current_bankroll
        - candidate.committed_daily_exposure
    )
    remaining_daily = max(0.0, remaining_daily)
    if stake > remaining_daily:
        stake = remaining_daily
        caps.append(AppliedCap.DAILY_EXPOSURE_CAP)
    if remaining_daily <= 0.0 and scaled_kelly > 0.0:
        reasons.append(StakeRejectionReason.DAILY_EXPOSURE_EXHAUSTED)

    if stake > candidate.available_bankroll:
        stake = candidate.available_bankroll
        caps.append(AppliedCap.AVAILABLE_BANKROLL)
    if candidate.available_bankroll <= 0.0 and scaled_kelly > 0.0:
        reasons.append(StakeRejectionReason.INSUFFICIENT_AVAILABLE_BANKROLL)

    stake = _floor_round(stake, policy.stake_rounding)

    minimum_stake = max(
        candidate.minimum_stake,
        policy.minimum_stake_fraction * candidate.current_bankroll,
    )
    # Catch-all for a positive-edge stake that survived every cap but is still
    # too small to place; skipped when a harder reason already explains it.
    if full_kelly > 0.0 and stake < minimum_stake and not reasons:
        reasons.append(StakeRejectionReason.BELOW_MINIMUM_STAKE)

    if reasons:
        stake = 0.0

    stake_fraction = (
        stake / candidate.current_bankroll if candidate.current_bankroll > 0 else 0.0
    )
    return StakeDecision(
        approved=not reasons and stake > 0.0,
        recommended_stake=stake,
        stake_fraction=stake_fraction,
        kelly_fraction=full_kelly,
        fractional_kelly=scaled_kelly,
        operating_state=candidate.operating_state,
        applied_caps=tuple(caps),
        reason_codes=tuple(reasons),
        policy_version=policy.version,
    )


def _floor_round(value: float, digits: int) -> float:
    """Round *down* to ``digits`` decimals so a stake never exceeds a cap."""

    if value <= 0.0:
        return 0.0
    factor = 10**digits
    return math.floor(value * factor) / factor
