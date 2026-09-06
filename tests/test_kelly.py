"""Kelly staking math, including the sign/edge cases where bugs hide."""

import math

import pytest

from qwantej.bankroll import fractional_kelly, kelly_fraction


def test_known_kelly_value() -> None:
    # p=0.6 at even money (d=2.0): f* = (0.6*2 - 1)/(2 - 1) = 0.2
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.2)


def test_kelly_matches_edge_over_net_odds() -> None:
    # f* = p - q/b, with b = d - 1
    p, d = 0.55, 3.0
    expected = p - (1 - p) / (d - 1)
    assert kelly_fraction(p, d) == pytest.approx(expected)


def test_non_positive_edge_returns_zero() -> None:
    # p*d = 1 exactly -> zero edge -> no bet
    assert kelly_fraction(0.5, 2.0) == 0.0
    # p*d < 1 -> negative edge -> floored at zero, never a lay
    assert kelly_fraction(0.4, 2.0) == 0.0
    assert kelly_fraction(0.1, 1.5) == 0.0


def test_certain_win_stakes_everything() -> None:
    assert kelly_fraction(1.0, 2.0) == pytest.approx(1.0)


def test_fractional_kelly_scales_linearly() -> None:
    full = kelly_fraction(0.6, 2.0)
    assert fractional_kelly(0.6, 2.0, 0.25) == pytest.approx(0.25 * full)


def test_fractional_kelly_never_exceeds_full() -> None:
    assert fractional_kelly(0.6, 2.0, 1.0) == pytest.approx(kelly_fraction(0.6, 2.0))


@pytest.mark.parametrize("probability", [0.0, -0.1, 1.1, math.nan, math.inf])
def test_invalid_probability_rejected(probability: float) -> None:
    with pytest.raises(ValueError):
        kelly_fraction(probability, 2.0)


@pytest.mark.parametrize("odds", [1.0, 0.5, 0.0, -2.0, math.nan, math.inf])
def test_invalid_odds_rejected(odds: float) -> None:
    with pytest.raises(ValueError):
        kelly_fraction(0.6, odds)


@pytest.mark.parametrize("multiplier", [0.0, -0.1, 1.5, math.nan])
def test_invalid_multiplier_rejected(multiplier: float) -> None:
    with pytest.raises(ValueError):
        fractional_kelly(0.6, 2.0, multiplier)
