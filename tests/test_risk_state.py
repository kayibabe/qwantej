"""Operating-state classification and risk-policy validation."""

import pytest

from qwantej.bankroll import OperatingState, RiskPolicy, classify_state
from qwantej.bankroll.state import ProductTier


def test_drawdown_thresholds_map_to_states() -> None:
    assert classify_state(0.0) is OperatingState.NORMAL
    assert classify_state(0.05) is OperatingState.NORMAL
    assert classify_state(0.10) is OperatingState.CAUTION
    assert classify_state(0.12) is OperatingState.CAUTION
    assert classify_state(0.15) is OperatingState.DEFENSIVE
    assert classify_state(0.20) is OperatingState.REVIEW
    assert classify_state(0.35) is OperatingState.REVIEW


def test_qualitative_signals_force_worse_states() -> None:
    assert classify_state(0.0, calibration_failure=True) is OperatingState.REVIEW
    assert classify_state(0.0, severe_drift=True) is OperatingState.REVIEW
    assert classify_state(0.0, drift=True) is OperatingState.DEFENSIVE
    assert classify_state(0.0, soft_deterioration=True) is OperatingState.CAUTION


def test_signals_never_soften_a_worse_drawdown_state() -> None:
    # A 20% drawdown is REVIEW even if only soft deterioration is flagged.
    assert classify_state(0.20, soft_deterioration=True) is OperatingState.REVIEW


@pytest.mark.parametrize("drawdown", [-0.1, 1.5, float("nan")])
def test_invalid_drawdown_rejected(drawdown: float) -> None:
    with pytest.raises(ValueError):
        classify_state(drawdown)


def test_default_policy_state_multipliers_are_non_increasing() -> None:
    policy = RiskPolicy()
    assert policy.state_multiplier(OperatingState.NORMAL) == 1.0
    assert policy.state_multiplier(OperatingState.REVIEW) == 0.0
    assert policy.allocation(ProductTier.CORE) >= policy.allocation(ProductTier.GROWTH)
    assert policy.allocation(ProductTier.GROWTH) >= policy.allocation(ProductTier.ALPHA)


def test_policy_mappings_are_immutable() -> None:
    policy = RiskPolicy()
    with pytest.raises(TypeError):
        policy.state_multipliers[OperatingState.REVIEW] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        policy.product_allocations[ProductTier.ALPHA] = 1.0  # type: ignore[index]


def test_policy_copies_input_mappings_defensively() -> None:
    multipliers = {
        OperatingState.NORMAL: 1.0,
        OperatingState.CAUTION: 0.5,
        OperatingState.DEFENSIVE: 0.25,
        OperatingState.REVIEW: 0.0,
    }
    policy = RiskPolicy(state_multipliers=multipliers)
    # Mutating the original dict after construction must not affect the policy.
    multipliers[OperatingState.REVIEW] = 0.9
    assert policy.state_multiplier(OperatingState.REVIEW) == 0.0


def test_single_ticket_cap_cannot_exceed_daily_cap() -> None:
    with pytest.raises(ValueError):
        RiskPolicy(single_ticket_cap=0.06, daily_exposure_cap=0.05)


def test_drawdown_thresholds_must_ascend() -> None:
    with pytest.raises(ValueError):
        RiskPolicy(caution_drawdown=0.2, defensive_drawdown=0.15, review_drawdown=0.1)


def test_review_must_suspend_staking() -> None:
    with pytest.raises(ValueError):
        RiskPolicy(
            state_multipliers={
                OperatingState.NORMAL: 1.0,
                OperatingState.CAUTION: 0.5,
                OperatingState.DEFENSIVE: 0.25,
                OperatingState.REVIEW: 0.1,
            }
        )


def test_state_multipliers_must_be_non_increasing() -> None:
    with pytest.raises(ValueError):
        RiskPolicy(
            state_multipliers={
                OperatingState.NORMAL: 0.5,
                OperatingState.CAUTION: 0.9,
                OperatingState.DEFENSIVE: 0.25,
                OperatingState.REVIEW: 0.0,
            }
        )
