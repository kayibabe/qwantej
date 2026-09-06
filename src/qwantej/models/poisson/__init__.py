"""Poisson goal-distribution model — transparent anchor and diagnostic
benchmark (framework §14). Also hosts the Dixon-Coles low-score correction
(framework §15)."""

from qwantej.models.poisson.model import (
    DEFAULT_MAX_GOALS,
    DEFAULT_RHO,
    DIXON_COLES_FAMILY,
    POISSON_FAMILY,
    VERSION,
    dixon_coles_scoreline,
    poisson_scoreline,
)

__all__ = [
    "poisson_scoreline",
    "dixon_coles_scoreline",
    "POISSON_FAMILY",
    "DIXON_COLES_FAMILY",
    "VERSION",
    "DEFAULT_MAX_GOALS",
    "DEFAULT_RHO",
]
