"""Contracts for deduplicated recommendation-pick reporting."""

from datetime import date
from types import SimpleNamespace

from app.models import MatchStatus
from app.services.recommendation_ledger import (
    _authoritative_result,
    _canonical_pick_key,
    recommendation_metrics,
    walk_forward_accumulator_selections,
)


def _pick(match_status, home_goals=None, away_goals=None):
    return {
        "match_status": match_status.value,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "market": "home_win",
        "selection": "home_win",
    }


def test_postponed_and_cancelled_fixtures_void_instead_of_staying_pending():
    assert _authoritative_result(_pick(MatchStatus.POSTPONED)) == "void"
    assert _authoritative_result(_pick(MatchStatus.CANCELLED)) == "void"


def test_unfinished_fixtures_stay_pending_and_finished_fixtures_are_evaluated():
    assert _authoritative_result(_pick(MatchStatus.SCHEDULED)) == "pending"
    assert _authoritative_result(_pick(MatchStatus.LIVE)) == "pending"
    assert _authoritative_result(_pick(MatchStatus.FINISHED, 2, 0)) == "won"
    assert _authoritative_result(_pick(MatchStatus.FINISHED, 0, 0)) == "lost"


def test_canonical_key_deduplicates_tiers_but_keeps_opposite_selections_distinct():
    target = date(2026, 8, 30)
    home = SimpleNamespace(
        match_id=42,
        market="double_chance",
        selection="double_chance_1x",
        model_version="0.2.1",
    )
    away = SimpleNamespace(
        match_id=42,
        market="double_chance",
        selection="double_chance_x2",
        model_version="0.2.1",
    )
    newer_model = SimpleNamespace(
        match_id=42,
        market="double_chance",
        selection="double_chance_1x",
        model_version="0.3.0",
    )

    assert _canonical_pick_key(target, home) == _canonical_pick_key(target, home)
    assert _canonical_pick_key(target, home) == _canonical_pick_key(target, newer_model)
    assert _canonical_pick_key(target, home) != _canonical_pick_key(target, away)


def test_recommendation_metrics_are_flat_stake_and_exclude_missing_odds_from_roi():
    rows = [
        {"result": "won", "odds": 2.0},
        {"result": "lost", "odds": 1.8},
        {"result": "won", "odds": None},
        {"result": "void", "odds": 1.9},
        {"result": "pending", "odds": 2.1},
    ]

    metrics = recommendation_metrics(rows, stake=10)

    assert metrics["unique_picks"] == 5
    assert metrics["settled"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 1
    assert metrics["voids"] == 1
    assert metrics["priced_settled"] == 2
    assert metrics["missing_odds"] == 1
    assert metrics["staked"] == 20
    assert metrics["returned"] == 20
    assert metrics["profit_loss"] == 0
    assert metrics["roi"] == 0
    assert metrics["hit_rate"] == 0.6667


def _ledger_row(
    target_date: str,
    *,
    market: str = "home_win",
    result: str = "won",
    odds: float | None = 2.0,
    sources: tuple[str, ...] = ("strongest",),
    versions: tuple[str, ...] = ("0.3.0",),
) -> dict:
    return {
        "target_date": target_date,
        "market": market,
        "result": result,
        "odds": odds,
        "sources": set(sources),
        "model_versions": set(versions),
    }


def _selected_dates(selection: dict, bucket: str) -> list[str]:
    return [row["target_date"] for row in selection[bucket]["rows"]]


def test_walk_forward_never_selects_a_date_before_its_threshold_is_met():
    rows = [
        _ledger_row(f"2026-10-0{day}", odds=2.0)
        for day in range(1, 5)
    ]
    rows.append(_ledger_row("2026-10-05", odds=2.0))
    rows.append(_ledger_row("2026-10-06", odds=2.0))

    selection = walk_forward_accumulator_selections(rows, stake=1.0)

    # Four prior picks is below the five-pick minimum, so the market cannot
    # contribute on 2026-10-05 even though it wins that day.
    assert "2026-10-05" not in _selected_dates(selection, "all_unique")
    assert _selected_dates(selection, "all_unique") == ["2026-10-06"]
    assert selection["all_unique"]["qualifying_markets"] == [
        {"market": "home_win", "first_qualified_date": "2026-10-06"}
    ]


def test_walk_forward_does_not_let_todays_result_qualify_todays_ticket():
    rows = [
        _ledger_row(f"2026-10-0{day}", result="lost", odds=2.0)
        for day in range(1, 6)
    ]
    # Seven wins today would lift the market's record above the 10% threshold,
    # but today's rows must not vote on today's selection.
    rows.extend(
        _ledger_row("2026-10-06", odds=2.0)
        for _ in range(7)
    )
    rows.append(_ledger_row("2026-10-07", odds=2.0))

    selection = walk_forward_accumulator_selections(rows, stake=1.0)

    assert "2026-10-06" not in _selected_dates(selection, "all_unique")
    # From 2026-10-07 the seven wins are prior evidence and the market qualifies.
    assert "2026-10-07" in _selected_dates(selection, "all_unique")


def test_walk_forward_uses_tighter_all_unique_threshold_than_published():
    # Four wins at 1.33 and one loss is +6.4% ROI: enough for the Published
    # 5% rule, not enough for the All Unique 10% rule.
    rows = [
        _ledger_row(
            f"2026-10-0{day}",
            result="won" if day <= 4 else "lost",
            odds=1.33,
            sources=("published", "strongest"),
        )
        for day in range(1, 6)
    ]
    rows.append(
        _ledger_row(
            "2026-10-06",
            odds=1.33,
            sources=("published", "strongest"),
        )
    )

    selection = walk_forward_accumulator_selections(rows, stake=1.0)

    assert "2026-10-06" not in _selected_dates(selection, "all_unique")
    assert "2026-10-06" in _selected_dates(selection, "published")


def test_walk_forward_published_combinations_are_scoped_to_model_version():
    good = [
        _ledger_row(
            f"2026-10-0{day}",
            result="won",
            odds=2.0,
            sources=("published",),
            versions=("0.2.0",),
        )
        for day in range(1, 6)
    ]
    bad = [
        _ledger_row(
            f"2026-10-0{day}",
            result="lost",
            odds=2.0,
            sources=("published",),
            versions=("0.3.0",),
        )
        for day in range(1, 6)
    ]
    rows = good + bad + [
        _ledger_row(
            "2026-10-06",
            odds=2.0,
            sources=("published",),
            versions=("0.2.0",),
        ),
        _ledger_row(
            "2026-10-06",
            odds=2.0,
            sources=("published",),
            versions=("0.3.0",),
        ),
    ]

    selection = walk_forward_accumulator_selections(rows, stake=1.0)

    selected = selection["published"]["rows"]
    assert [(row["target_date"], tuple(row["model_versions"])) for row in selected] == [
        ("2026-10-06", ("0.2.0",))
    ]


def test_walk_forward_ignores_input_order_and_strongest_only_rows_for_published():
    rows = [
        _ledger_row("2026-10-03", odds=2.0, sources=("strongest",)),
        _ledger_row("2026-10-01", odds=2.0, sources=("strongest",)),
        _ledger_row("2026-10-02", odds=2.0, sources=("strongest",)),
        _ledger_row("2026-10-05", odds=2.0, sources=("strongest",)),
        _ledger_row("2026-10-04", odds=2.0, sources=("strongest",)),
        _ledger_row("2026-10-06", odds=2.0, sources=("strongest",)),
    ]

    selection = walk_forward_accumulator_selections(list(reversed(rows)), stake=1.0)

    assert _selected_dates(selection, "all_unique") == ["2026-10-06"]
    assert _selected_dates(selection, "published") == []
