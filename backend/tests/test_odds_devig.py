from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.clv import clv_is_valid
from app.services.model_runner import devig_group, fair_implied_probabilities

T0 = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def quote(row_id, bookmaker, market, implied):
    return SimpleNamespace(
        id=row_id, bookmaker=bookmaker, market=market, implied_probability=implied
    )


def test_devig_group_recognises_outcome_families():
    assert set(devig_group("home_win")) == {"home_win", "draw", "away_win"}
    assert set(devig_group("over_2.5")) == {"over_2.5", "under_2.5"}
    assert set(devig_group("under_2.5")) == {"over_2.5", "under_2.5"}
    assert set(devig_group("btts_no")) == {"btts_yes", "btts_no"}
    # A derived market has no clean mutually exclusive group; it stays raw.
    assert devig_group("double_chance_1x") == ("double_chance_1x",)


def test_three_way_probabilities_sum_to_one_per_bookmaker():
    entries = [
        quote(1, "BookA", "home_win", 0.50),
        quote(2, "BookA", "draw", 0.30),
        quote(3, "BookA", "away_win", 0.25),
    ]
    fair = fair_implied_probabilities(entries)
    assert fair[1] == pytest.approx(0.50 / 1.05)
    assert fair[2] == pytest.approx(0.30 / 1.05)
    assert fair[3] == pytest.approx(0.25 / 1.05)
    assert sum(fair.values()) == pytest.approx(1.0)


def test_two_way_pair_is_devigged():
    entries = [
        quote(1, "BookA", "over_2.5", 0.60),
        quote(2, "BookA", "under_2.5", 0.50),
    ]
    fair = fair_implied_probabilities(entries)
    assert fair[1] == pytest.approx(0.60 / 1.10)
    assert fair[2] == pytest.approx(0.50 / 1.10)
    assert sum(fair.values()) == pytest.approx(1.0)


def test_incomplete_group_falls_back_to_raw():
    entries = [quote(1, "BookA", "over_2.5", 0.60)]
    assert fair_implied_probabilities(entries)[1] == pytest.approx(0.60)


def test_bookmakers_are_not_mixed():
    entries = [
        quote(1, "BookA", "over_2.5", 0.60),
        quote(2, "BookB", "under_2.5", 0.50),
    ]
    fair = fair_implied_probabilities(entries)
    assert fair[1] == pytest.approx(0.60)
    assert fair[2] == pytest.approx(0.50)


def test_clv_requires_a_strictly_later_quote():
    good = SimpleNamespace(
        source_odds_at=T0,
        closing_odds_at=T0 + timedelta(hours=2),
        closing_decimal_odds=2.1,
    )
    same_time = SimpleNamespace(
        source_odds_at=T0, closing_odds_at=T0, closing_decimal_odds=2.1
    )
    earlier = SimpleNamespace(
        source_odds_at=T0,
        closing_odds_at=T0 - timedelta(minutes=1),
        closing_decimal_odds=2.1,
    )
    missing = SimpleNamespace(
        source_odds_at=None, closing_odds_at=T0, closing_decimal_odds=2.1
    )
    assert clv_is_valid(good) is True
    assert clv_is_valid(same_time) is False
    assert clv_is_valid(earlier) is False
    assert clv_is_valid(missing) is False
