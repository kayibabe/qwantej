"""Coherence and derivation tests for ScorelineDistribution (framework §15-16)."""

import numpy as np
import pytest

from qwantej.models.poisson import poisson_scoreline
from qwantej.models.scoreline import ScorelineDistribution


def test_rejects_non_square_matrix() -> None:
    with pytest.raises(ValueError):
        ScorelineDistribution(np.ones((3, 4)) / 12)


def test_rejects_matrix_not_summing_to_one() -> None:
    with pytest.raises(ValueError):
        ScorelineDistribution(np.ones((3, 3)))


def test_rejects_negative_probabilities() -> None:
    m = np.zeros((2, 2))
    m[0, 0] = 1.2
    m[0, 1] = -0.2
    with pytest.raises(ValueError):
        ScorelineDistribution(m)


class TestSymmetry:
    """Equal expected goals => a symmetric match: P(home) == P(away)."""

    def test_symmetric_match_result(self) -> None:
        dist = poisson_scoreline(1.3, 1.3)
        mr = dist.match_result()
        assert mr.home == pytest.approx(mr.away, abs=1e-12)
        assert mr.draw > 0

    def test_stronger_home_wins_more(self) -> None:
        mr = poisson_scoreline(2.1, 0.9).match_result()
        assert mr.home > mr.away


class TestDerivationsAreCoherent:
    def test_all_markets_sum_to_one(self) -> None:
        dist = poisson_scoreline(1.7, 1.1)
        mr = dist.match_result()
        assert mr.home + mr.draw + mr.away == pytest.approx(1.0)
        assert sum(dist.over_under(2.5).as_dict().values()) == pytest.approx(1.0)
        assert sum(dist.both_teams_to_score().as_dict().values()) == pytest.approx(1.0)
        assert sum(dist.team_over("home", 1.5).as_dict().values()) == pytest.approx(1.0)

    def test_higher_line_lowers_over_probability(self) -> None:
        dist = poisson_scoreline(1.6, 1.4)
        assert dist.over_under(1.5).yes > dist.over_under(2.5).yes > dist.over_under(3.5).yes

    def test_double_chance_matches_1x2(self) -> None:
        mr = poisson_scoreline(1.5, 1.2).match_result()
        dc = mr.double_chance()
        assert dc.home_or_draw == pytest.approx(mr.home + mr.draw)
        assert dc.draw_or_away == pytest.approx(mr.draw + mr.away)

    def test_whole_number_line_rejected(self) -> None:
        dist = poisson_scoreline(1.5, 1.5)
        with pytest.raises(ValueError):
            dist.over_under(2.0)

    def test_team_over_bad_side_rejected(self) -> None:
        with pytest.raises(ValueError):
            poisson_scoreline(1.5, 1.5).team_over("visitor", 1.5)
