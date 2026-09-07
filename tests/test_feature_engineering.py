"""Tests for qwantej.features.engineering — pure, leakage-free feature computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qwantej.features.engineering import (
    HistoricalResult,
    _elo_expected,
    compute_match_features,
    features_to_dict,
)

# --- Helpers -------------------------------------------------------------------

_T0 = datetime(2025, 8, 1, 15, 0, tzinfo=UTC)


def _result(
    home: str, away: str, hg: int, ag: int, offset_days: int = 0
) -> HistoricalResult:
    return HistoricalResult(
        home_team_id=home,
        away_team_id=away,
        home_goals=hg,
        away_goals=ag,
        kickoff_utc=_T0 + timedelta(days=offset_days),
    )


# --- HistoricalResult validation -----------------------------------------------


def test_result_rejects_same_team():
    with pytest.raises(ValueError, match="differ"):
        HistoricalResult("A", "A", 1, 0, _T0)


def test_result_rejects_negative_goals():
    with pytest.raises(ValueError, match="non-negative"):
        HistoricalResult("A", "B", -1, 0, _T0)


def test_result_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone"):
        HistoricalResult("A", "B", 1, 0, datetime(2025, 1, 1))


# --- compute_match_features — edge cases ----------------------------------------


def test_empty_history_uses_fallbacks():
    features = compute_match_features(
        [],
        "Home",
        "Away",
        league_home_avg_fallback=1.5,
        league_away_avg_fallback=1.2,
    )
    assert features.home_matches == 0
    assert features.away_matches == 0
    assert features.league_home_avg == 1.5
    assert features.league_away_avg == 1.2
    # With no history, both strengths default to 1.0 → xG equals league avg
    assert features.home_xg == pytest.approx(1.5, rel=0.01)
    assert features.away_xg == pytest.approx(1.2, rel=0.01)
    # ELO starts at initial for both
    assert features.elo_home_rating == pytest.approx(1500.0, abs=0.01)
    assert features.elo_away_rating == pytest.approx(1500.0, abs=0.01)
    # H2H unavailable
    assert features.h2h_home_win_rate is None
    # Form is neutral prior
    assert features.home_form == pytest.approx(0.5)
    assert features.away_form == pytest.approx(0.5)


def test_rejects_same_home_away():
    with pytest.raises(ValueError, match="differ"):
        compute_match_features([], "X", "X")


def test_rejects_invalid_n_recent():
    with pytest.raises(ValueError, match="n_recent"):
        compute_match_features([], "A", "B", n_recent=0)


def test_rejects_invalid_k_factor():
    with pytest.raises(ValueError, match="k_factor"):
        compute_match_features([], "A", "B", k_factor=0.0)


# --- ELO computation ------------------------------------------------------------


def test_elo_symmetric_starting_ratings():
    features = compute_match_features([], "H", "A", initial_elo=1500.0)
    assert features.elo_home_rating == features.elo_away_rating


def test_elo_updates_after_home_win():
    history = [_result("H", "A", 2, 0, 0)]
    features = compute_match_features(history, "H", "A", initial_elo=1500.0)
    # Home team won → home rating rises, away falls
    assert features.elo_home_rating > 1500.0
    assert features.elo_away_rating < 1500.0


def test_elo_updates_after_away_win():
    history = [_result("H", "A", 0, 3, 0)]
    features = compute_match_features(history, "H", "A", initial_elo=1500.0)
    assert features.elo_home_rating < 1500.0
    assert features.elo_away_rating > 1500.0


def test_elo_draw_smaller_update():
    """A draw produces a smaller rating change than a decisive result."""
    win_history = [_result("H", "A", 1, 0, 0)]
    draw_history = [_result("H", "A", 1, 1, 0)]
    win_features = compute_match_features(win_history, "H", "A", initial_elo=1500.0)
    draw_features = compute_match_features(draw_history, "H", "A", initial_elo=1500.0)
    win_delta = abs(win_features.elo_home_rating - 1500.0)
    draw_delta = abs(draw_features.elo_home_rating - 1500.0)
    assert win_delta > draw_delta


def test_elo_expected_balanced():
    """Equal ratings + home advantage gives expected > 0.5."""
    e = _elo_expected(1500.0, 1500.0, 65.0)
    assert e > 0.5


def test_elo_expected_range():
    for home_r, away_r, adv in [(1600, 1400, 65), (1400, 1600, 65), (1500, 1500, 0)]:
        e = _elo_expected(home_r, away_r, adv)
        assert 0 < e < 1


# --- xG / strength computation --------------------------------------------------


def test_strong_home_attack_raises_home_xg():
    """A team that always scores 3 at home has higher-than-average home xG."""
    history = [_result("H", "X", 3, 1, i) for i in range(10)]
    history += [_result("A", "H", 2, 1, 20 + i) for i in range(10)]  # away matches for "A"
    features = compute_match_features(history, "H", "A")
    assert features.home_xg > features.league_home_avg


def test_strong_defence_lowers_opponent_xg():
    """A team that concedes 0 away should suppress the home team's xG."""
    # Away team A concedes 0 home-team goals over 10 away matches (X scores 0).
    # home_goals=0 < league_home_avg => away_defence < 1.0 => home_xg < league avg.
    history = [_result("X", "A", 0, 0, i) for i in range(10)]
    history += [_result("H", "X", 1, 1, 20 + i) for i in range(10)]
    features = compute_match_features(history, "H", "A")
    assert features.away_defence < 1.0
    assert features.home_xg < features.league_home_avg


def test_xg_always_positive():
    """xG must stay positive even for a very poor attacking side."""
    history = [_result("H", "X", 0, 3, i) for i in range(20)]
    history += [_result("Y", "A", 0, 3, 30 + i) for i in range(20)]
    features = compute_match_features(history, "H", "A")
    assert features.home_xg > 0
    assert features.away_xg > 0


# --- Form computation -----------------------------------------------------------


def test_form_all_wins():
    history = [_result("H", "X", 2, 0, i) for i in range(5)]
    features = compute_match_features(history, "H", "A", n_recent=5)
    assert features.home_form == pytest.approx(1.0)


def test_form_all_losses():
    history = [_result("X", "H", 3, 0, i) for i in range(5)]
    features = compute_match_features(history, "H", "A", n_recent=5)
    assert features.home_form == pytest.approx(0.0)


def test_form_neutral_prior_no_history():
    features = compute_match_features([], "H", "A")
    assert features.home_form == pytest.approx(0.5)
    assert features.away_form == pytest.approx(0.5)


def test_n_recent_respected():
    """Only the last n_recent results are used for form."""
    old_losses = [_result("X", "H", 3, 0, i) for i in range(10)]
    recent_wins = [_result("H", "X", 2, 0, 20 + i) for i in range(5)]
    history = old_losses + recent_wins
    features = compute_match_features(history, "H", "A", n_recent=5)
    assert features.home_form == pytest.approx(1.0)
    assert features.home_matches == 5


# --- H2H -----------------------------------------------------------------------


def test_h2h_none_when_no_history():
    history = [_result("H", "X", 1, 0, 0), _result("Y", "A", 0, 1, 1)]
    features = compute_match_features(history, "H", "A")
    assert features.h2h_home_win_rate is None


def test_h2h_computed_correctly():
    history = [
        _result("H", "A", 2, 0, 0),   # H wins at home
        _result("A", "H", 0, 1, 10),  # H wins away (as away)
        _result("H", "A", 1, 2, 20),  # H loses
    ]
    features = compute_match_features(history, "H", "A")
    # H won 2 of 3 H2H encounters
    assert features.h2h_home_win_rate == pytest.approx(2 / 3, rel=0.001)


# --- features_to_dict -----------------------------------------------------------


def test_features_to_dict_returns_all_keys():
    features = compute_match_features([], "H", "A")
    d = features_to_dict(features)
    expected_keys = {
        "elo_home_rating", "elo_away_rating",
        "home_xg", "away_xg",
        "home_attack", "home_defence",
        "away_attack", "away_defence",
        "home_form", "away_form",
        "h2h_home_win_rate",
        "home_matches", "away_matches",
        "league_home_avg", "league_away_avg",
    }
    assert set(d.keys()) == expected_keys


def test_features_to_dict_h2h_is_none_when_no_h2h():
    features = compute_match_features([], "H", "A")
    d = features_to_dict(features)
    assert d["h2h_home_win_rate"] is None


def test_features_to_dict_scalars_are_float_or_none():
    history = [_result("H", "A", 1, 0, 0), _result("A", "H", 0, 2, 10)]
    features = compute_match_features(history, "H", "A")
    d = features_to_dict(features)
    for key, value in d.items():
        assert value is None or isinstance(value, float), \
            f"{key}: expected float | None, got {type(value).__name__}"


# --- league averages -----------------------------------------------------------


def test_league_averages_computed_from_history():
    history = [
        _result("A", "B", 2, 1, 0),
        _result("C", "D", 3, 0, 1),
    ]
    features = compute_match_features(history, "X", "Y")
    # home: (2+3)/2 = 2.5, away: (1+0)/2 = 0.5
    assert features.league_home_avg == pytest.approx(2.5)
    assert features.league_away_avg == pytest.approx(0.5)


# --- cross-team isolation -------------------------------------------------------


def test_unrelated_results_update_elo_pool():
    """Matches between other teams still update the ELO pool correctly."""
    history = [
        _result("H", "X", 2, 0, 0),   # H plays X — H improves
        _result("X", "A", 1, 2, 10),  # X plays A — A improves
    ]
    features = compute_match_features(history, "H", "A")
    # Both teams should have ratings that differ from the initial value
    assert features.elo_home_rating != pytest.approx(1500.0)
    assert features.elo_away_rating != pytest.approx(1500.0)
