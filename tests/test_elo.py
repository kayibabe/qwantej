"""Elo model tests — expected-score identity, symmetry, monotonicity,
draw model validity, and the rating update (framework §14, §51)."""

import pytest

from qwantej.models.elo import (
    DEFAULT_HOME_ADVANTAGE,
    expected_score,
    result_probabilities,
    update_ratings,
)


class TestExpectedScore:
    def test_matches_classic_elo_formula(self) -> None:
        # With no home advantage, expected_score must equal the base-10 Elo form.
        e = expected_score(1600, 1500, home_advantage=0.0)
        assert e == pytest.approx(1 / (1 + 10 ** (-100 / 400)))

    def test_equal_ratings_no_advantage_is_even(self) -> None:
        assert expected_score(1500, 1500, home_advantage=0.0) == pytest.approx(0.5)

    def test_home_advantage_raises_expectation(self) -> None:
        assert expected_score(1500, 1500) > 0.5  # default HFA > 0


class TestResultProbabilities:
    def test_symmetric_when_evenly_matched(self) -> None:
        mr = result_probabilities(1500, 1500, home_advantage=0.0)
        assert mr.home == pytest.approx(mr.away)
        assert mr.draw > 0

    def test_sums_to_one_for_extreme_gap(self) -> None:
        mr = result_probabilities(2400, 1000)
        assert mr.home + mr.draw + mr.away == pytest.approx(1.0)
        assert mr.home > mr.away

    def test_home_advantage_shifts_toward_home(self) -> None:
        neutral = result_probabilities(1500, 1500, home_advantage=0.0)
        with_hfa = result_probabilities(1500, 1500, home_advantage=DEFAULT_HOME_ADVANTAGE)
        assert with_hfa.home > neutral.home

    def test_zero_draw_width_rejected(self) -> None:
        with pytest.raises(ValueError):
            result_probabilities(1500, 1500, draw_width=0.0)

    @pytest.mark.parametrize("rating", [float("nan"), float("inf")])
    def test_non_finite_rating_rejected(self, rating: float) -> None:
        with pytest.raises(ValueError):
            result_probabilities(rating, 1500)
        with pytest.raises(ValueError):
            expected_score(1500, rating)


class TestUpdateRatings:
    @pytest.mark.parametrize("k", [float("nan"), float("inf")])
    def test_non_finite_k_rejected(self, k: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            update_ratings(1500, 1500, 1, 0, k=k)

    def test_update_is_zero_sum(self) -> None:
        h0, a0 = 1500.0, 1500.0
        h1, a1 = update_ratings(h0, a0, home_goals=2, away_goals=0)
        assert (h1 - h0) == pytest.approx(-(a1 - a0))

    def test_home_win_raises_home_rating(self) -> None:
        h1, a1 = update_ratings(1500, 1500, home_goals=3, away_goals=1, home_advantage=0.0)
        assert h1 > 1500 and a1 < 1500

    def test_expected_result_barely_moves_ratings(self) -> None:
        # A heavy favourite winning as expected should move little.
        h1, _ = update_ratings(2000, 1200, home_goals=1, away_goals=0, home_advantage=0.0)
        assert h1 - 2000 < 2.0

    def test_draw_between_equals_is_a_no_op(self) -> None:
        h1, a1 = update_ratings(1500, 1500, home_goals=1, away_goals=1, home_advantage=0.0)
        assert h1 == pytest.approx(1500) and a1 == pytest.approx(1500)
