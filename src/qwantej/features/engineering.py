"""Pure, leakage-free feature engineering from historical football results.

All functions are pure (no DB access). *historical* must contain only results
that occurred strictly before the fixture whose features are being computed —
the caller is responsible for enforcing the PIT (point-in-time) cut.

Attack/defence strengths follow the multiplicative Dixon-Coles notation:
    home_xg = league_home_avg × attack_home × defence_away
    away_xg = league_away_avg × attack_away × defence_home

ELO uses the standard base-10 / 400-point formula with a home-advantage offset
applied only to the prediction step, not to the rating update, so ratings are
venue-neutral (the conventional treatment for league Elo systems).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HistoricalResult:
    """One settled match used as a training observation."""

    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    kickoff_utc: datetime  # timezone-aware

    def __post_init__(self) -> None:
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away team must differ")
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("goals must be non-negative")
        if self.kickoff_utc.tzinfo is None or self.kickoff_utc.utcoffset() is None:
            raise ValueError("kickoff_utc must be timezone-aware")


@dataclass(frozen=True)
class MatchFeatures:
    """Leakage-free feature vector for one forthcoming fixture."""

    # ELO (venue-neutral, updated through all prior results)
    elo_home_rating: float
    elo_away_rating: float

    # Poisson expected goals
    home_xg: float
    away_xg: float

    # Multiplicative strength components
    home_attack: float    # home team goals scored relative to league avg
    home_defence: float   # home team goals conceded relative to league avg
    away_attack: float
    away_defence: float

    # Recent form (win rate in last n_recent matches, home+away combined)
    home_form: float      # 0.0–1.0
    away_form: float

    # Head-to-head: None when no H2H history available
    h2h_home_win_rate: float | None

    # Sample size — useful for DQS/reliability gating
    home_matches: int
    away_matches: int

    # League averages inferred from historical (or fallback)
    league_home_avg: float
    league_away_avg: float


# --- Public API -----------------------------------------------------------------


def compute_match_features(
    historical: Sequence[HistoricalResult],
    home_team_id: str,
    away_team_id: str,
    *,
    n_recent: int = 30,
    k_factor: float = 20.0,
    home_elo_advantage: float = 65.0,
    initial_elo: float = 1500.0,
    league_home_avg_fallback: float = 1.5,
    league_away_avg_fallback: float = 1.2,
) -> MatchFeatures:
    """Compute leakage-free features for a match given all prior results.

    *historical* must be sorted in ascending kickoff order. Every entry must
    have a kickoff strictly before the target fixture's kickoff — the caller
    enforces this constraint; this function does not re-check it.

    If either team has no match history the strength defaults to 1.0 (league
    average) and form defaults to 0.5 (neutral prior).
    """
    if home_team_id == away_team_id:
        raise ValueError("home and away team must differ")
    if n_recent < 1:
        raise ValueError("n_recent must be at least 1")
    if k_factor <= 0:
        raise ValueError("k_factor must be positive")

    elo_home, elo_away = _compute_elo(
        historical, home_team_id, away_team_id,
        k_factor=k_factor,
        home_elo_advantage=home_elo_advantage,
        initial_elo=initial_elo,
    )

    league_home_avg, league_away_avg = _league_averages(
        historical, league_home_avg_fallback, league_away_avg_fallback
    )

    home_results = _team_recent(historical, home_team_id, n_recent)
    away_results = _team_recent(historical, away_team_id, n_recent)

    home_attack, home_defence = _strength(
        home_team_id, home_results, league_home_avg, league_away_avg
    )
    away_attack, away_defence = _strength(
        away_team_id, away_results, league_home_avg, league_away_avg
    )

    home_xg = max(0.1, league_home_avg * home_attack * away_defence)
    away_xg = max(0.1, league_away_avg * away_attack * home_defence)

    home_form = _win_rate(home_team_id, home_results)
    away_form = _win_rate(away_team_id, away_results)
    h2h_rate = _h2h_win_rate(historical, home_team_id, away_team_id)

    return MatchFeatures(
        elo_home_rating=round(elo_home, 4),
        elo_away_rating=round(elo_away, 4),
        home_xg=round(home_xg, 6),
        away_xg=round(away_xg, 6),
        home_attack=round(home_attack, 6),
        home_defence=round(home_defence, 6),
        away_attack=round(away_attack, 6),
        away_defence=round(away_defence, 6),
        home_form=round(home_form, 6),
        away_form=round(away_form, 6),
        h2h_home_win_rate=round(h2h_rate, 6) if h2h_rate is not None else None,
        home_matches=len(home_results),
        away_matches=len(away_results),
        league_home_avg=round(league_home_avg, 6),
        league_away_avg=round(league_away_avg, 6),
    )


def features_to_dict(features: MatchFeatures) -> dict[str, float | None]:
    """Convert MatchFeatures to the flat scalar dict the feature store expects."""
    return {
        "elo_away_rating": features.elo_away_rating,
        "elo_home_rating": features.elo_home_rating,
        "away_attack": features.away_attack,
        "away_defence": features.away_defence,
        "away_form": features.away_form,
        "away_matches": float(features.away_matches),
        "away_xg": features.away_xg,
        "h2h_home_win_rate": features.h2h_home_win_rate,
        "home_attack": features.home_attack,
        "home_defence": features.home_defence,
        "home_form": features.home_form,
        "home_matches": float(features.home_matches),
        "home_xg": features.home_xg,
        "league_away_avg": features.league_away_avg,
        "league_home_avg": features.league_home_avg,
    }


# --- Private helpers ------------------------------------------------------------


_ELO_DIVISOR = 400.0  # conventional base-10 / 400-point scale


def _elo_expected(home_rating: float, away_rating: float, home_advantage: float) -> float:
    """Home team's expected score in [0, 1] (win=1, draw=0.5, loss=0)."""
    exponent = (away_rating - home_rating - home_advantage) / _ELO_DIVISOR
    return 1.0 / (1.0 + 10.0**exponent)


def _compute_elo(
    historical: Sequence[HistoricalResult],
    home_team_id: str,
    away_team_id: str,
    *,
    k_factor: float,
    home_elo_advantage: float,
    initial_elo: float,
) -> tuple[float, float]:
    ratings: dict[str, float] = defaultdict(lambda: initial_elo)
    for result in historical:
        h, a = result.home_team_id, result.away_team_id
        expected_h = _elo_expected(ratings[h], ratings[a], home_elo_advantage)
        if result.home_goals > result.away_goals:
            score_h = 1.0
        elif result.home_goals == result.away_goals:
            score_h = 0.5
        else:
            score_h = 0.0
        delta = k_factor * (score_h - expected_h)
        ratings[h] += delta
        ratings[a] -= delta
    return ratings[home_team_id], ratings[away_team_id]


def _league_averages(
    historical: Sequence[HistoricalResult],
    home_fallback: float,
    away_fallback: float,
) -> tuple[float, float]:
    if not historical:
        return home_fallback, away_fallback
    n = len(historical)
    home_avg = sum(r.home_goals for r in historical) / n
    away_avg = sum(r.away_goals for r in historical) / n
    return (
        home_avg if home_avg > 0 else home_fallback,
        away_avg if away_avg > 0 else away_fallback,
    )


def _team_recent(
    historical: Sequence[HistoricalResult],
    team_id: str,
    n: int,
) -> list[HistoricalResult]:
    """Return the last *n* results involving *team_id*, in ascending order."""
    matches = [r for r in historical if team_id in (r.home_team_id, r.away_team_id)]
    return matches[-n:]


def _strength(
    team_id: str,
    results: Sequence[HistoricalResult],
    league_home_avg: float,
    league_away_avg: float,
) -> tuple[float, float]:
    """Return (attack_strength, defence_strength) relative to league averages.

    Each match contributes one observation normalised to its venue role so
    home-heavy schedules don't bias the estimate.  Returns (1.0, 1.0) — league
    average — when no results are available.
    """
    if not results or league_home_avg <= 0 or league_away_avg <= 0:
        return 1.0, 1.0

    scored_rel: list[float] = []
    conceded_rel: list[float] = []

    for r in results:
        if r.home_team_id == team_id:
            # Playing at home: compare against home-venue league average
            scored_rel.append(r.home_goals / league_home_avg)
            conceded_rel.append(r.away_goals / league_away_avg)
        else:
            # Playing away: compare against away-venue league average
            scored_rel.append(r.away_goals / league_away_avg)
            conceded_rel.append(r.home_goals / league_home_avg)

    attack = sum(scored_rel) / len(scored_rel)
    defence = sum(conceded_rel) / len(conceded_rel)
    # Clamp to avoid degenerate xG (a 0-goals defence is treated as very strong
    # but not literally zero, which would zero-out the opponent's xG entirely).
    return max(0.05, attack), max(0.05, defence)


def _win_rate(
    team_id: str,
    results: Sequence[HistoricalResult],
) -> float:
    if not results:
        return 0.5
    wins = sum(
        1 for r in results
        if (r.home_team_id == team_id and r.home_goals > r.away_goals)
        or (r.away_team_id == team_id and r.away_goals > r.home_goals)
    )
    return wins / len(results)


def _h2h_win_rate(
    historical: Sequence[HistoricalResult],
    home_team_id: str,
    away_team_id: str,
) -> float | None:
    h2h = [
        r for r in historical
        if {r.home_team_id, r.away_team_id} == {home_team_id, away_team_id}
    ]
    if not h2h:
        return None
    wins = sum(
        1 for r in h2h
        if (r.home_team_id == home_team_id and r.home_goals > r.away_goals)
        or (r.away_team_id == home_team_id and r.away_goals > r.home_goals)
    )
    return wins / len(h2h)


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
