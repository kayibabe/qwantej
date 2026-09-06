"""Recommended-stake pipeline: caps, state, allocation, and no-Martingale."""

import pytest

from qwantej.bankroll import (
    OperatingState,
    ProductTier,
    RiskPolicy,
    StakeCandidate,
    recommend_stake,
)
from qwantej.bankroll.staking import AppliedCap, StakeRejectionReason


def _candidate(**overrides: object) -> StakeCandidate:
    params: dict[str, object] = dict(
        ticket_probability=0.60,
        decimal_odds=2.0,
        product=ProductTier.CORE,
        current_bankroll=1000.0,
        available_bankroll=1000.0,
        committed_daily_exposure=0.0,
        operating_state=OperatingState.NORMAL,
        minimum_stake=0.0,
    )
    params.update(overrides)
    return StakeCandidate(**params)  # type: ignore[arg-type]


def test_single_ticket_cap_binds() -> None:
    # scaled Kelly 0.05 > 2% cap -> stake pinned to 2% of 1000.
    decision = recommend_stake(_candidate())
    assert decision.approved
    assert decision.recommended_stake == 20.0
    assert AppliedCap.SINGLE_TICKET_CAP in decision.applied_caps
    assert decision.reason_codes == ()


def test_small_edge_below_cap_uses_fractional_kelly() -> None:
    # p=0.52,d=2 -> full Kelly 0.04, quarter-Kelly 0.01 -> 1% of 1000.
    decision = recommend_stake(_candidate(ticket_probability=0.52))
    assert decision.recommended_stake == 10.0
    assert AppliedCap.SINGLE_TICKET_CAP not in decision.applied_caps


def test_daily_exposure_cap_limits_stake() -> None:
    decision = recommend_stake(_candidate(committed_daily_exposure=45.0))
    assert decision.recommended_stake == 5.0
    assert AppliedCap.DAILY_EXPOSURE_CAP in decision.applied_caps
    assert decision.approved


def test_daily_exposure_exhausted_blocks() -> None:
    decision = recommend_stake(_candidate(committed_daily_exposure=50.0))
    assert decision.recommended_stake == 0.0
    assert StakeRejectionReason.DAILY_EXPOSURE_EXHAUSTED in decision.reason_codes
    assert not decision.approved


def test_available_bankroll_caps_stake() -> None:
    decision = recommend_stake(_candidate(available_bankroll=3.0))
    assert decision.recommended_stake == 3.0
    assert AppliedCap.AVAILABLE_BANKROLL in decision.applied_caps


def test_zero_available_bankroll_blocks() -> None:
    decision = recommend_stake(_candidate(available_bankroll=0.0))
    assert decision.recommended_stake == 0.0
    assert StakeRejectionReason.INSUFFICIENT_AVAILABLE_BANKROLL in decision.reason_codes


def test_review_state_suspends_staking() -> None:
    decision = recommend_stake(_candidate(operating_state=OperatingState.REVIEW))
    assert decision.recommended_stake == 0.0
    assert StakeRejectionReason.REVIEW_STATE_SUSPENDED in decision.reason_codes
    assert not decision.approved


def test_non_positive_edge_blocks() -> None:
    decision = recommend_stake(_candidate(ticket_probability=0.40))
    assert decision.recommended_stake == 0.0
    assert StakeRejectionReason.NON_POSITIVE_EDGE in decision.reason_codes


def test_below_minimum_stake_blocks_without_placing() -> None:
    decision = recommend_stake(
        _candidate(ticket_probability=0.52, minimum_stake=50.0)
    )
    assert decision.recommended_stake == 0.0
    assert StakeRejectionReason.BELOW_MINIMUM_STAKE in decision.reason_codes


def test_product_allocation_scales_alpha_below_core() -> None:
    core = recommend_stake(_candidate(ticket_probability=0.52, product=ProductTier.CORE))
    alpha = recommend_stake(
        _candidate(ticket_probability=0.52, product=ProductTier.ALPHA)
    )
    assert alpha.recommended_stake < core.recommended_stake
    assert AppliedCap.PRODUCT_ALLOCATION in alpha.applied_caps


def test_stake_never_exceeds_single_ticket_cap_fraction() -> None:
    policy = RiskPolicy()
    decision = recommend_stake(_candidate())
    assert decision.stake_fraction <= policy.single_ticket_cap + 1e-9


def test_no_martingale_stake_non_increasing_as_bankroll_falls() -> None:
    # Same edge, shrinking bankroll -> absolute stake must never rise.
    stakes = [
        recommend_stake(
            _candidate(current_bankroll=bankroll, available_bankroll=bankroll)
        ).recommended_stake
        for bankroll in (1000.0, 800.0, 500.0, 250.0, 100.0)
    ]
    assert stakes == sorted(stakes, reverse=True)


def test_no_martingale_stake_non_increasing_as_state_worsens() -> None:
    # Low edge so the single-ticket cap does not mask the state multiplier.
    stakes = [
        recommend_stake(
            _candidate(ticket_probability=0.52, operating_state=state)
        ).recommended_stake
        for state in (
            OperatingState.NORMAL,
            OperatingState.CAUTION,
            OperatingState.DEFENSIVE,
            OperatingState.REVIEW,
        )
    ]
    assert stakes == sorted(stakes, reverse=True)
    assert stakes[-1] == 0.0


def test_invalid_candidate_available_exceeds_current() -> None:
    with pytest.raises(ValueError):
        _candidate(current_bankroll=100.0, available_bankroll=200.0)
