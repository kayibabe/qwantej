"""Independent-Poisson and Dixon-Coles scoreline models (framework §14-15).

Independent Poisson is the transparent anchor and diagnostic benchmark: home
and away goals are independent Poisson variables with means `home_xg`,
`away_xg`. Dixon-Coles keeps that structure but corrects the well-known
under-fit of low scores (0-0, 1-0, 0-1, 1-1) via a single dependence
parameter `rho`; with `rho = 0` it reduces exactly to independent Poisson,
which is the incremental-value benchmark the framework requires (§15: "keep a
simple independent-Poisson benchmark so additional complexity must prove
incremental value").

Both return a `ScorelineDistribution`, from which every goal market is derived
coherently. These are pure functions of the rate parameters — fitting
`home_xg`/`away_xg`/`rho` from data (and the leakage-safety of that fit) is the
feature/estimation layer's responsibility (Phase 5), not this module's.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import poisson

from qwantej.models.scoreline import ScorelineDistribution

# Registry identity (mirrors backend ModelFamily values; kept as plain strings
# so the pure modelling layer never imports the persistence layer).
POISSON_FAMILY = "poisson"
DIXON_COLES_FAMILY = "dixon_coles"
VERSION = "1.0.0"

DEFAULT_MAX_GOALS = 10
# Research default (framework Appendix A): the true rho must be fitted per
# league/season and backtested. Dixon-Coles found a small negative value.
DEFAULT_RHO = -0.05


def _validate_xg(home_xg: float, away_xg: float) -> None:
    # Finiteness first: NaN/inf pass the <= 0 comparison silently and would
    # otherwise poison the whole scoreline matrix.
    for name, value in (("home", home_xg), ("away", away_xg)):
        if not math.isfinite(value):
            raise ValueError(f"{name} expected goals must be finite, got {value}")
    if home_xg <= 0 or away_xg <= 0:
        raise ValueError(f"expected goals must be positive, got home={home_xg}, away={away_xg}")


def _independent_matrix(home_xg: float, away_xg: float, max_goals: int) -> np.ndarray:
    goals = np.arange(max_goals + 1)
    home_pmf = poisson.pmf(goals, home_xg)
    away_pmf = poisson.pmf(goals, away_xg)
    return np.outer(home_pmf, away_pmf)


def _finalise(matrix: np.ndarray) -> ScorelineDistribution:
    """Renormalise a truncated (and possibly tau-adjusted) matrix to sum to 1,
    recording the pre-normalisation mass lost to truncation as a diagnostic."""
    total = float(matrix.sum())
    if total <= 0:
        raise ValueError("degenerate scoreline matrix sums to <= 0")
    return ScorelineDistribution(matrix / total, truncated_mass=max(0.0, 1.0 - total))


def poisson_scoreline(
    home_xg: float, away_xg: float, max_goals: int = DEFAULT_MAX_GOALS
) -> ScorelineDistribution:
    """Independent-Poisson scoreline distribution."""
    _validate_xg(home_xg, away_xg)
    return _finalise(_independent_matrix(home_xg, away_xg, max_goals))


def dixon_coles_scoreline(
    home_xg: float,
    away_xg: float,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> ScorelineDistribution:
    """Dixon-Coles low-score-corrected scoreline distribution.

    Applies the tau adjustment to the four lowest scorelines, then renormalises.
    `rho = 0` recovers independent Poisson exactly. A `rho` extreme enough to
    drive any of the four adjusted cells negative is rejected rather than
    silently clamped.
    """
    _validate_xg(home_xg, away_xg)
    if not math.isfinite(rho):
        raise ValueError(f"rho must be finite, got {rho}")
    matrix = _independent_matrix(home_xg, away_xg, max_goals)

    tau = {
        (0, 0): 1.0 - home_xg * away_xg * rho,
        (0, 1): 1.0 + home_xg * rho,
        (1, 0): 1.0 + away_xg * rho,
        (1, 1): 1.0 - rho,
    }
    for (i, j), factor in tau.items():
        if factor < 0:
            raise ValueError(
                f"rho={rho} makes the Dixon-Coles tau for score {i}-{j} negative "
                f"({factor:.4f}); choose a rho consistent with these rates"
            )
        matrix[i, j] *= factor

    return _finalise(matrix)
