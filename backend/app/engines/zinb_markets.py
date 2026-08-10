"""
zinb_markets.py — ZINB score-matrix → Phase 1A + Phase 2 market probabilities.

Wraps the existing ZINBGoalModel so it:
  1. Fits from HistoricalFixture records using team names as keys.
  2. Converts a score matrix into a dict of market → probability
     for all Phase 1A + Phase 2 markets.

Markets produced:
  Full-match (Phase 1A):
    "Over 1.5", "Over 2.5", "Under 2.5", "Under 3.5",
    "BTTS Yes", "1X (Home or Draw)", "X2 (Draw or Away)",
    "Home Over 0.5", "Away Over 0.5"
  First-half (Phase 2):
    "1H Over 0.5", "1H Over 1.5", "1H Under 1.5"
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Optional

from app.engines.zinb import ZINBGoalModel

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# Fraction of full-match goals typically scored in the first half (~44%).
# Used to scale ZINB full-match lambdas for first-half probability estimates.
_HT_FRACTION = 0.44

PHASE1A_MARKETS = (
    "Over 1.5",
    "Over 2.5",
    "Under 2.5",
    "Under 3.5",
    "BTTS Yes",
    "1X (Home or Draw)",
    "X2 (Draw or Away)",
    "Home Over 0.5",
    "Away Over 0.5",
    # Phase 2 — first-half markets
    "1H Over 0.5",
    "1H Over 1.5",
    "1H Under 1.5",
)


def score_matrix_to_market_probs(matrix: "np.ndarray") -> dict[str, float]:
    """
    Convert a joint score probability matrix M[i,j] = P(home=i, away=j)
    into Phase 1A market probabilities.

    Returns an empty dict if numpy is unavailable or matrix is None.
    """
    try:
        import numpy as np
    except ImportError:
        return {}

    if matrix is None:
        return {}

    n = matrix.shape[0]
    probs: dict[str, float] = {}

    def _sum(cond) -> float:
        total = 0.0
        for i in range(n):
            for j in range(n):
                if cond(i, j):
                    total += matrix[i, j]
        return float(np.clip(total, 0.0, 1.0))

    probs["Over 1.5"] = _sum(lambda i, j: i + j >= 2)
    probs["Over 2.5"] = _sum(lambda i, j: i + j >= 3)
    probs["Under 2.5"] = _sum(lambda i, j: i + j <= 2)
    probs["Under 3.5"] = _sum(lambda i, j: i + j <= 3)
    probs["BTTS Yes"] = _sum(lambda i, j: i > 0 and j > 0)
    probs["1X (Home or Draw)"] = _sum(lambda i, j: i >= j)
    probs["X2 (Draw or Away)"] = _sum(lambda i, j: j >= i)
    probs["Home Over 0.5"] = _sum(lambda i, j: i >= 1)
    probs["Away Over 0.5"] = _sum(lambda i, j: j >= 1)

    return probs


def predict_ht_market_probs(
    lambda_home: Optional[float],
    lambda_away: Optional[float],
) -> dict[str, float]:
    """
    Estimate first-half market probabilities using scaled full-match lambdas.

    Models combined first-half goals as Poisson(_HT_FRACTION * (λh + λa)).
    The sum of two independent Poissons is Poisson — this is exact, not an
    approximation, provided independence holds across the two teams.
    """
    if lambda_home is None or lambda_away is None or lambda_home < 0 or lambda_away < 0:
        return {}
    l = _HT_FRACTION * (lambda_home + lambda_away)
    if l <= 0:
        return {}
    p0 = math.exp(-l)
    p1 = l * p0
    return {
        "1H Over 0.5":  round(max(0.0, min(1.0, 1.0 - p0)), 6),
        "1H Over 1.5":  round(max(0.0, min(1.0, 1.0 - p0 - p1)), 6),
        "1H Under 1.5": round(max(0.0, min(1.0, p0 + p1)), 6),
    }


class ZINBMarketsModel:
    """
    Team-name–keyed ZINB model that produces Phase 1A market probabilities.

    Fits from HistoricalFixture-style dicts (team names, not IDs).
    Internally remaps names to integer IDs for the underlying ZINBGoalModel.
    """

    def __init__(self, decay_rate: float = 0.05, min_matches: int = 5):
        self._model = ZINBGoalModel(decay_rate=decay_rate, min_matches=min_matches)
        self._name_to_id: dict[str, int] = {}
        self._lambda_cache: dict[tuple[str, str], tuple[float, float]] = {}

    def _id(self, name: str) -> int:
        if name not in self._name_to_id:
            self._name_to_id[name] = len(self._name_to_id)
        return self._name_to_id[name]

    def fit(self, matches: list[dict]) -> "ZINBMarketsModel":
        """
        Fit from a list of dicts:
          home_team, away_team, home_goals, away_goals, match_date (ISO str)
        """
        records = [
            {
                "home_team_id": self._id(m["home_team"]),
                "away_team_id": self._id(m["away_team"]),
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"],
                "match_date": m.get("match_date", ""),
            }
            for m in matches
            if m.get("home_team") and m.get("away_team")
            and m.get("home_goals") is not None
            and m.get("away_goals") is not None
        ]
        self._model.fit(records)
        self._lambda_cache.clear()
        return self

    def predict_lambdas(self, home_team: str, away_team: str) -> tuple[float, float]:
        """Return (lambda_home, lambda_away) expected goals."""
        key = (home_team, away_team)
        if key not in self._lambda_cache:
            h_id = self._id(home_team)
            a_id = self._id(away_team)
            self._lambda_cache[key] = self._model.predict_goals(h_id, a_id)
        return self._lambda_cache[key]

    def predict_market_probs(self, home_team: str, away_team: str) -> dict[str, float]:
        """
        Return Phase 1A + Phase 2 market probabilities for a fixture.
        Returns {} if the model isn't fitted or scipy is unavailable.
        """
        if not self._model.fitted:
            return {}

        h_id = self._id(home_team)
        a_id = self._id(away_team)
        matrix = self._model.score_matrix(h_id, a_id)
        if matrix is None:
            return {}

        probs = score_matrix_to_market_probs(matrix)
        # Phase 2: first-half markets via scaled Poisson
        lambda_home, lambda_away = self.predict_lambdas(home_team, away_team)
        probs.update(predict_ht_market_probs(lambda_home, lambda_away))
        return probs
