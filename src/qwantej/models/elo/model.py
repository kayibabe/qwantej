"""Elo team-strength model (framework §14).

Two pieces:

1. `expected_score` — the classic Elo win expectation (points share in [0, 1])
   for the home team, using base-10 / 400-point scaling so ratings are
   interchangeable with conventional Elo systems.

2. `result_probabilities` — a 1X2 distribution. Elo alone gives only an
   expected score, so draws need an explicit model. We use an ordered-logistic
   ("proportional-odds") draw band: a latent home-strength `z` with two
   symmetric cutpoints `±draw_width` splits into away / draw / home. This is
   always valid — the three probabilities are non-negative and sum to exactly
   1 for any inputs — and is symmetric (swapping the teams swaps home/away and
   leaves the draw unchanged).

`update_ratings` is the standard `R' = R + K(S - E)` step. Margin-of-victory
scaling is deliberately omitted from this baseline (a documented extension for
later). All three are pure functions; the leakage-safe part — only feeding a
match's *pre-kickoff* ratings — belongs to the training/replay loop, not here.

The scale and draw-width defaults below are research defaults (framework
Appendix A), to be fitted and backtested per competition.
"""

from __future__ import annotations

import math

from qwantej.models.probabilities import MatchResultProbs

ELO_FAMILY = "elo"
VERSION = "1.0.0"

DEFAULT_K = 20.0
DEFAULT_HOME_ADVANTAGE = 65.0  # Elo points added to the home rating
# Natural-log scale equivalent to conventional Elo's base-10 / 400 divisor,
# so expected_score matches 1 / (1 + 10 ** (-diff / 400)).
DEFAULT_SCALE = 400.0 / math.log(10.0)
# Cutpoint half-width; ~0.55 puts the draw probability near 0.27 for evenly
# matched teams, in line with typical league draw rates.
DEFAULT_DRAW_WIDTH = 0.55


def _logistic(t: float) -> float:
    return 1.0 / (1.0 + math.exp(-t))


def _strength(
    home_rating: float, away_rating: float, home_advantage: float, scale: float
) -> float:
    for name, value in (
        ("home_rating", home_rating),
        ("away_rating", away_rating),
        ("home_advantage", home_advantage),
        ("scale", scale),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value}")
    if scale <= 0:
        raise ValueError(f"scale must be positive, got {scale}")
    return (home_rating + home_advantage - away_rating) / scale


def expected_score(
    home_rating: float,
    away_rating: float,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_SCALE,
) -> float:
    """Home team's expected score (win = 1, draw = 0.5, loss = 0), in [0, 1]."""
    return _logistic(_strength(home_rating, away_rating, home_advantage, scale))


def result_probabilities(
    home_rating: float,
    away_rating: float,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_SCALE,
    draw_width: float = DEFAULT_DRAW_WIDTH,
) -> MatchResultProbs:
    """1X2 probabilities via the ordered-logistic draw band."""
    if draw_width <= 0:
        raise ValueError(f"draw_width must be positive, got {draw_width}")
    z = _strength(home_rating, away_rating, home_advantage, scale)
    home = _logistic(z - draw_width)
    away = _logistic(-z - draw_width)
    draw = 1.0 - home - away
    return MatchResultProbs(home=home, draw=draw, away=away)


def _actual_score(home_goals: int, away_goals: int) -> float:
    if home_goals > away_goals:
        return 1.0
    if home_goals < away_goals:
        return 0.0
    return 0.5


def update_ratings(
    home_rating: float,
    away_rating: float,
    home_goals: int,
    away_goals: int,
    k: float = DEFAULT_K,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    scale: float = DEFAULT_SCALE,
) -> tuple[float, float]:
    """Return updated (home, away) ratings after a settled result. The update
    is zero-sum: the points the home team gains, the away team loses."""
    if not math.isfinite(k):
        raise ValueError(f"k must be finite, got {k}")
    if k < 0:
        raise ValueError(f"k must be non-negative, got {k}")
    expected = expected_score(home_rating, away_rating, home_advantage, scale)
    actual = _actual_score(home_goals, away_goals)
    delta = k * (actual - expected)
    return home_rating + delta, away_rating - delta
