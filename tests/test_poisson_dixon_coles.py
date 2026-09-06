"""Poisson and Dixon-Coles tests — numerical sanity, the rho=0 benchmark
identity, and the low-score correction direction (framework §15, §51)."""

import math

import numpy as np
import pytest

from qwantej.models.poisson import dixon_coles_scoreline, poisson_scoreline


class TestPoissonNumericalSanity:
    def test_correct_score_matches_closed_form(self) -> None:
        # P(0-0) = e^-(lh) * e^-(la); with lh=la=1.5 that is e^-3.
        dist = poisson_scoreline(1.5, 1.5, max_goals=15)
        assert dist.correct_score(0, 0) == pytest.approx(math.exp(-3.0), rel=1e-4)

    def test_truncation_mass_is_tiny(self) -> None:
        dist = poisson_scoreline(1.4, 1.2, max_goals=10)
        assert dist.truncated_mass < 1e-6

    def test_most_likely_score_for_low_rates(self) -> None:
        assert poisson_scoreline(0.8, 0.7).most_likely_score() == (0, 0)

    @pytest.mark.parametrize("home_xg,away_xg", [(0, 1.0), (-1.0, 1.0), (1.0, 0.0)])
    def test_non_positive_rates_rejected(self, home_xg: float, away_xg: float) -> None:
        with pytest.raises(ValueError):
            poisson_scoreline(home_xg, away_xg)


class TestDixonColes:
    def test_rho_zero_recovers_independent_poisson(self) -> None:
        dc = dixon_coles_scoreline(1.6, 1.2, rho=0.0)
        pois = poisson_scoreline(1.6, 1.2)
        assert np.allclose(dc.matrix, pois.matrix, atol=1e-12)

    def test_negative_rho_lifts_the_draw_and_nil_nil(self) -> None:
        # The canonical Dixon-Coles effect: a small negative rho raises the
        # 0-0 (and overall draw) probability relative to independent Poisson.
        pois = poisson_scoreline(1.3, 1.1)
        dc = dixon_coles_scoreline(1.3, 1.1, rho=-0.05)
        assert dc.correct_score(0, 0) > pois.correct_score(0, 0)
        assert dc.match_result().draw > pois.match_result().draw

    def test_still_sums_to_one(self) -> None:
        dc = dixon_coles_scoreline(2.0, 1.4, rho=-0.08)
        assert float(dc.matrix.sum()) == pytest.approx(1.0)

    def test_extreme_rho_rejected(self) -> None:
        # rho large enough to make a tau factor negative must be refused.
        with pytest.raises(ValueError):
            dixon_coles_scoreline(1.5, 1.5, rho=1.0)
