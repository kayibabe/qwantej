"""Coherent scoreline distribution and its market derivations (framework §15-16).

A `ScorelineDistribution` is a full P(home_goals=i, away_goals=j) matrix. Every
goal-based market — 1X2, double chance, totals (over/under), BTTS, team totals —
is derived from this single distribution, so the outputs are *internally
coherent* by construction (framework §15: "derive 1X2, double chance, totals,
BTTS and team-goal markets from the same internally coherent scoreline
distribution"). Poisson and Dixon-Coles both build one of these; the
derivations below are model-agnostic.
"""

from __future__ import annotations

import numpy as np

from qwantej.models.probabilities import (
    SUM_TOLERANCE,
    BinaryProbs,
    MatchResultProbs,
)


class ScorelineDistribution:
    """An (n+1, n+1) grid of scoreline probabilities, rows = home goals,
    columns = away goals. The matrix must be non-negative and sum to ~1."""

    def __init__(self, matrix: np.ndarray, *, truncated_mass: float = 0.0) -> None:
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError(f"scoreline matrix must be square 2-D, got shape {matrix.shape}")
        if np.any(matrix < -1e-12):
            raise ValueError("scoreline matrix has negative probabilities")
        total = float(matrix.sum())
        if abs(total - 1.0) > SUM_TOLERANCE:
            raise ValueError(f"scoreline matrix must sum to 1, got {total}")
        self.matrix = matrix
        self.max_goals = matrix.shape[0] - 1
        # Diagnostic: probability mass lost to truncation before renormalising
        # (framework §15's tail-handling sanity check).
        self.truncated_mass = truncated_mass

    def correct_score(self, home_goals: int, away_goals: int) -> float:
        return float(self.matrix[home_goals, away_goals])

    def most_likely_score(self) -> tuple[int, int]:
        i, j = np.unravel_index(int(np.argmax(self.matrix)), self.matrix.shape)
        return int(i), int(j)

    def match_result(self) -> MatchResultProbs:
        home = float(np.tril(self.matrix, -1).sum())  # i > j
        draw = float(np.trace(self.matrix))  # i == j
        away = float(np.triu(self.matrix, 1).sum())  # i < j
        # Absorb residual rounding into the largest bucket so the tuple sums to 1.
        return _normalise_triple(home, draw, away)

    def over_under(self, line: float) -> BinaryProbs:
        """Over/under total match goals. `line` is a half-line (e.g. 2.5) — a
        whole-number line would make a push possible and is rejected."""
        if line == int(line):
            raise ValueError(f"over_under needs a half-line (e.g. 2.5) to avoid a push, got {line}")
        totals = np.add.outer(np.arange(self.max_goals + 1), np.arange(self.max_goals + 1))
        over = float(self.matrix[totals > line].sum())
        return _binary(over)

    def both_teams_to_score(self) -> BinaryProbs:
        yes = float(self.matrix[1:, 1:].sum())  # home >= 1 and away >= 1
        return _binary(yes)

    def team_over(self, side: str, line: float) -> BinaryProbs:
        """Over/under goals for one team. `side` is 'home' or 'away'."""
        if line == int(line):
            raise ValueError(f"team_over expects a half-line (e.g. 1.5), got {line}")
        if side == "home":
            goals = np.arange(self.max_goals + 1)[:, None]
        elif side == "away":
            goals = np.arange(self.max_goals + 1)[None, :]
        else:
            raise ValueError(f"side must be 'home' or 'away', got {side!r}")
        over = float(self.matrix[np.broadcast_to(goals > line, self.matrix.shape)].sum())
        return _binary(over)


def _binary(yes: float) -> BinaryProbs:
    yes = min(max(yes, 0.0), 1.0)
    return BinaryProbs(yes=yes, no=1.0 - yes)


def _normalise_triple(home: float, draw: float, away: float) -> MatchResultProbs:
    total = home + draw + away
    if total <= 0:
        raise ValueError("degenerate scoreline distribution: outcomes sum to 0")
    return MatchResultProbs(home=home / total, draw=draw / total, away=away / total)
