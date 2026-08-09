"""
Elo rating system for football match-outcome probability.

Fitted from historical_fixtures records. Produces P(home win), P(draw),
P(away win) for any fixture, which map to the 1X and X2 markets.

Draw model: parabolic suppression of the base draw rate as one team becomes
a heavy favourite, consistent with empirical football distributions.

    E_home = 1 / (1 + 10^((R_away - R_home - ha) / 400))
    P_draw = clamp(base_draw - draw_k * (E_home - 0.5)^2, 0.05, 0.42)
    P_home = E_home - P_draw / 2
    P_away = (1 - E_home) - P_draw / 2

This satisfies P_home + P_draw + P_away = 1 exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

_DEFAULT_RATING = 1500.0
_HOME_ADVANTAGE = 80.0   # Elo points added to home team's effective rating
_K_START = 32.0          # K-factor for first 20 matches
_K_STABLE = 20.0         # K-factor once a team has 20+ matches
_STABLE_THRESHOLD = 20
_BASE_DRAW = 0.265        # empirical draw rate in top European leagues
_DRAW_K = 0.70            # parabola steepness: at E_home=0.9, P_draw ≈ 0.23


@dataclass
class EloTeam:
    name: str
    rating: float = _DEFAULT_RATING
    n_matches: int = 0
    last_match_date: Optional[date] = None


class EloSystem:
    """
    In-memory Elo system for a set of teams.

    Designed to be fitted from historical_fixtures rows in chronological
    order, then serialised to / restored from the elo_ratings DB table.
    """

    def __init__(
        self,
        home_advantage: float = _HOME_ADVANTAGE,
        k_start: float = _K_START,
        k_stable: float = _K_STABLE,
        stable_threshold: int = _STABLE_THRESHOLD,
        base_draw: float = _BASE_DRAW,
        draw_k: float = _DRAW_K,
    ):
        self.home_advantage = home_advantage
        self.k_start = k_start
        self.k_stable = k_stable
        self.stable_threshold = stable_threshold
        self.base_draw = base_draw
        self.draw_k = draw_k
        self._teams: dict[str, EloTeam] = {}

    # ------------------------------------------------------------------
    # Team management
    # ------------------------------------------------------------------

    def _get(self, name: str) -> EloTeam:
        if name not in self._teams:
            self._teams[name] = EloTeam(name=name)
        return self._teams[name]

    def get_rating(self, name: str) -> float:
        return self._get(name).rating

    def all_teams(self) -> list[EloTeam]:
        return list(self._teams.values())

    # ------------------------------------------------------------------
    # Core math
    # ------------------------------------------------------------------

    def _expected(self, r_home: float, r_away: float) -> float:
        """Standard Elo expected score for the home side (includes HA)."""
        return 1.0 / (1.0 + 10.0 ** ((r_away - r_home - self.home_advantage) / 400.0))

    def _k(self, team: EloTeam) -> float:
        return self.k_start if team.n_matches < self.stable_threshold else self.k_stable

    def predict_1x2(self, home: str, away: str) -> tuple[float, float, float]:
        """
        Return (P_home_win, P_draw, P_away_win).
        All three are in [0, 1] and sum to exactly 1.
        """
        h = self._get(home)
        a = self._get(away)
        e_home = self._expected(h.rating, a.rating)

        # Parabolic draw model: fewer draws when one team is a heavy favourite
        raw_draw = self.base_draw - self.draw_k * (e_home - 0.5) ** 2
        p_draw = max(0.05, min(0.42, raw_draw))

        p_home = max(0.0, e_home - p_draw / 2.0)
        p_away = max(0.0, (1.0 - e_home) - p_draw / 2.0)

        # Renormalise to guard against floating-point drift
        total = p_home + p_draw + p_away
        return p_home / total, p_draw / total, p_away / total

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        home: str,
        away: str,
        home_goals: int,
        away_goals: int,
        match_date: Optional[date] = None,
    ) -> None:
        """Update ratings after a completed match."""
        h = self._get(home)
        a = self._get(away)

        actual_home = 1.0 if home_goals > away_goals else (0.5 if home_goals == away_goals else 0.0)
        actual_away = 1.0 - actual_home

        e_home = self._expected(h.rating, a.rating)
        e_away = 1.0 - e_home

        h.rating += self._k(h) * (actual_home - e_home)
        a.rating += self._k(a) * (actual_away - e_away)
        h.n_matches += 1
        a.n_matches += 1
        if match_date:
            h.last_match_date = match_date
            a.last_match_date = match_date

    # ------------------------------------------------------------------
    # Bulk fitting
    # ------------------------------------------------------------------

    def fit(self, matches: list[dict]) -> "EloSystem":
        """
        Fit from a list of dicts with keys:
          home_team, away_team, home_goals, away_goals, match_date (ISO str or date)
        Expects records in chronological order.
        """
        for m in sorted(matches, key=lambda r: r.get("match_date", "")):
            h = m.get("home_team", "")
            a = m.get("away_team", "")
            hg = m.get("home_goals")
            ag = m.get("away_goals")
            if not h or not a or hg is None or ag is None:
                continue
            md = m.get("match_date")
            if isinstance(md, str):
                try:
                    from datetime import datetime
                    md = datetime.strptime(md[:10], "%Y-%m-%d").date()
                except ValueError:
                    md = None
            self.update(h, a, int(hg), int(ag), md)
        return self

    # ------------------------------------------------------------------
    # Serialisation helpers (for DB persistence)
    # ------------------------------------------------------------------

    def to_records(self, league: str, country: str, season: int) -> list[dict]:
        """Flatten to list of dicts suitable for bulk-upserting into elo_ratings."""
        return [
            {
                "team_name": t.name,
                "league": league,
                "country": country,
                "season": season,
                "rating": round(t.rating, 4),
                "n_matches": t.n_matches,
                "last_match_date": t.last_match_date,
            }
            for t in self._teams.values()
        ]

    def load_records(self, records: list[dict]) -> None:
        """Restore from previously persisted DB records."""
        for r in records:
            name = r["team_name"]
            self._teams[name] = EloTeam(
                name=name,
                rating=float(r.get("rating", _DEFAULT_RATING)),
                n_matches=int(r.get("n_matches", 0)),
                last_match_date=r.get("last_match_date"),
            )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def rating_diff(self, home: str, away: str) -> float:
        return self._get(home).rating - self._get(away).rating
