"""Tests for Phase 8 accumulator orchestration: QualifiedSelection, manifest
hashing, build_accumulator_decision, and the walk-forward backtest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from qwantej.accumulator import (
    AccumulatorPolicy,
    QualifiedSelection,
    build_accumulator_decision,
)
from qwantej.accumulator.backtest import (
    BacktestRound,
    walk_forward_accumulator_backtest,
)
from qwantej.bankroll.state import OperatingState, ProductTier

NOW = datetime(2026, 9, 8, 10, tzinfo=UTC)

_LINEAGE = dict(
    model_version="model-v1",
    calibration_version="cal-v1",
    feature_version="feat-v1",
    code_commit="abc123",
)


def _qs(
    *,
    prediction_id: str = "p1",
    fixture_id: str = "f1",
    league_id: str = "PL",
    market_family: str = "TOTALS",
    selection: str = "Over 2.5",
    decimal_odds: str = "1.85",
    conservative_probability: float = 0.60,
    edge: float = 0.11,
    qss: float = 88.0,
    dqs: float = 80.0,
    reliability: float = 75.0,
    quote_timestamp: datetime = NOW - timedelta(minutes=30),
    **lineage,
) -> QualifiedSelection:
    return QualifiedSelection(
        prediction_id=prediction_id,
        fixture_id=fixture_id,
        league_id=league_id,
        market_family=market_family,
        selection=selection,
        calibrated_probability=conservative_probability + 0.02,
        conservative_probability=conservative_probability,
        decimal_odds=Decimal(decimal_odds),
        edge=edge,
        qss=qss,
        dqs=dqs,
        reliability=reliability,
        quote_timestamp=quote_timestamp,
        **{**_LINEAGE, **lineage},
    )


def _good_pool(n: int = 6) -> list[QualifiedSelection]:
    """Six diverse candidates that can form a valid CORE ticket."""
    return [
        _qs(
            prediction_id=f"p{i}",
            fixture_id=f"f{i}",
            league_id=f"L{i % 3}",
            decimal_odds="1.70",
        )
        for i in range(n)
    ]


def _bankroll_kwargs() -> dict:
    return dict(
        current_bankroll=1000.0,
        available_bankroll=1000.0,
        committed_daily_exposure=0.0,
    )


# ---------------------------------------------------------------------------
# QualifiedSelection validation
# ---------------------------------------------------------------------------


class TestQualifiedSelectionValidation:
    def test_valid_constructs(self) -> None:
        qs = _qs()
        assert qs.prediction_id == "p1"
        assert qs.conservative_probability == 0.60

    def test_blank_prediction_id_raises(self) -> None:
        with pytest.raises(ValueError, match="prediction_id"):
            _qs(prediction_id="  ")

    def test_odds_le_1_raises(self) -> None:
        with pytest.raises(ValueError, match="decimal_odds"):
            _qs(decimal_odds="1.00")

    def test_nan_odds_raises(self) -> None:
        with pytest.raises(ValueError, match="decimal_odds"):
            _qs(decimal_odds="NaN")

    def test_zero_probability_raises(self) -> None:
        with pytest.raises(ValueError, match="conservative_probability"):
            _qs(conservative_probability=0.0)

    def test_qss_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="qss"):
            _qs(qss=101.0)

    def test_naive_quote_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _qs(quote_timestamp=datetime(2026, 9, 8, 10))

    def test_blank_code_commit_raises(self) -> None:
        with pytest.raises(ValueError, match="code_commit"):
            _qs(code_commit="")

    def test_to_leg_propagates_fields(self) -> None:
        qs = _qs(fixture_id="fx99", league_id="BL", decimal_odds="2.00")
        leg = qs.to_leg()
        assert leg.fixture_id == "fx99"
        assert leg.league_id == "BL"
        assert leg.decimal_odds == Decimal("2.00")
        assert leg.captured_at == qs.quote_timestamp


# ---------------------------------------------------------------------------
# build_accumulator_decision — basic contract
# ---------------------------------------------------------------------------


class TestBuildAccumulatorDecision:
    def test_returns_decision_for_all_products(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(), as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        products_covered = {pd.product for pd in decision.products}
        assert products_covered == set(ProductTier)

    def test_paper_only_is_always_true(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(), as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        assert decision.paper_only is True

    def test_candidate_count_matches_pool_size(self) -> None:
        pool = _good_pool(4)
        decision = build_accumulator_decision(
            pool, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        assert decision.candidate_count == 4

    def test_manifest_hash_is_64_hex_chars(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(), as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        assert len(decision.input_manifest_hash) == 64
        int(decision.input_manifest_hash, 16)  # must be valid hex

    def test_naive_as_of_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            build_accumulator_decision(
                _good_pool(),
                as_of=datetime(2026, 9, 8, 10),
                operating_state=OperatingState.NORMAL,
                **_bankroll_kwargs(),
            )

    def test_review_state_suspends_all_stakes(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(),
            as_of=NOW,
            operating_state=OperatingState.REVIEW,
            **_bankroll_kwargs(),
        )
        for pd in decision.products:
            if pd.stake_decision is not None:
                assert not pd.stake_decision.approved

    def test_core_ticket_found_from_good_pool(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(), as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        core = next(pd for pd in decision.products if pd.product is ProductTier.CORE)
        assert core.result.ticket is not None

    def test_stake_decision_attached_when_ticket_found_and_normal_state(self) -> None:
        decision = build_accumulator_decision(
            _good_pool(), as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        core = next(pd for pd in decision.products if pd.product is ProductTier.CORE)
        if core.result.ticket is not None:
            assert core.stake_decision is not None

    def test_stake_decision_none_when_no_ticket(self) -> None:
        # Empty pool → no ticket for any product
        decision = build_accumulator_decision(
            [], as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        )
        for pd in decision.products:
            assert pd.result.ticket is None
            assert pd.stake_decision is None

    def test_custom_policy_respected(self) -> None:
        # Override CORE policy with a very wide odds band — should still produce a ticket
        wide_policy = AccumulatorPolicy(
            version="wide-v1",
            product=ProductTier.CORE,
            min_combined_odds=Decimal("1.01"),
            max_combined_odds=Decimal("100.00"),
            min_legs=2,
            max_legs=8,
            preferred_qss=80.0,
            hard_qss_floor=70.0,
            min_dqs=50.0,
            max_legs_per_league=4,
            max_legs_per_market_family=8,
            price_freshness_max_age=timedelta(hours=6),
        )
        decision = build_accumulator_decision(
            _good_pool(),
            as_of=NOW,
            operating_state=OperatingState.NORMAL,
            policies={ProductTier.CORE: wide_policy},
            **_bankroll_kwargs(),
        )
        core = next(pd for pd in decision.products if pd.product is ProductTier.CORE)
        assert core.result.ticket is not None


# ---------------------------------------------------------------------------
# Manifest hash determinism and sensitivity
# ---------------------------------------------------------------------------


class TestManifestHash:
    def test_same_pool_same_hash(self) -> None:
        pool = _good_pool()
        h1 = build_accumulator_decision(
            pool, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        h2 = build_accumulator_decision(
            pool, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        assert h1 == h2

    def test_shuffled_pool_same_hash(self) -> None:
        pool = _good_pool()
        import random
        shuffled = list(pool)
        random.shuffle(shuffled)
        h1 = build_accumulator_decision(
            pool, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        h2 = build_accumulator_decision(
            shuffled, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        assert h1 == h2

    def test_different_pool_different_hash(self) -> None:
        pool_a = _good_pool()
        pool_b = _good_pool()
        pool_b[0] = _qs(prediction_id="p99", fixture_id="f99", decimal_odds="2.10")
        h1 = build_accumulator_decision(
            pool_a, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        h2 = build_accumulator_decision(
            pool_b, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        assert h1 != h2

    def test_different_as_of_different_hash(self) -> None:
        pool = _good_pool()
        h1 = build_accumulator_decision(
            pool, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        h2 = build_accumulator_decision(
            pool,
            as_of=NOW + timedelta(hours=1),
            operating_state=OperatingState.NORMAL,
            **_bankroll_kwargs(),
        ).input_manifest_hash
        assert h1 != h2

    def test_different_code_commit_different_hash(self) -> None:
        pool_a = _good_pool()
        pool_b = [
            _qs(
                prediction_id=f"p{i}",
                fixture_id=f"f{i}",
                league_id=f"L{i % 3}",
                decimal_odds="1.70",
                code_commit="deadbeef",
            )
            for i in range(6)
        ]
        h1 = build_accumulator_decision(
            pool_a, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        h2 = build_accumulator_decision(
            pool_b, as_of=NOW, operating_state=OperatingState.NORMAL, **_bankroll_kwargs()
        ).input_manifest_hash
        assert h1 != h2


# ---------------------------------------------------------------------------
# Walk-forward accumulator backtest
# ---------------------------------------------------------------------------


def _backtest_round(
    i: int,
    *,
    n_candidates: int = 6,
    all_win: bool = True,
) -> BacktestRound:
    as_of = NOW + timedelta(days=i)
    candidates = [
        _qs(
            prediction_id=f"p{i}_{j}",
            fixture_id=f"f{i}_{j}",
            league_id=f"L{j % 3}",
            decimal_odds="1.70",
            quote_timestamp=as_of - timedelta(minutes=30),
        )
        for j in range(n_candidates)
    ]
    outcome = {c.fixture_id: (1 if all_win else 0) for c in candidates}
    return BacktestRound(
        as_of=as_of,
        candidates=candidates,
        outcome=outcome,
        outcome_observed_at=as_of + timedelta(hours=3),
    )


class TestWalkForwardAccumulatorBacktest:
    def test_report_has_correct_round_count(self) -> None:
        rounds = [_backtest_round(i) for i in range(5)]
        report = walk_forward_accumulator_backtest(rounds)
        assert report.rounds_total == 5

    def test_all_products_represented_in_stats(self) -> None:
        rounds = [_backtest_round(i) for i in range(3)]
        report = walk_forward_accumulator_backtest(rounds)
        assert set(report.product_stats) == set(ProductTier)

    def test_all_wins_improves_return(self) -> None:
        rounds = [_backtest_round(i, all_win=True) for i in range(5)]
        report = walk_forward_accumulator_backtest(rounds)
        core = report.product_stats[ProductTier.CORE]
        if core.tickets_found > 0 and core.hit_rate is not None:
            assert core.hit_rate == 1.0

    def test_all_losses_hit_rate_zero(self) -> None:
        rounds = [_backtest_round(i, all_win=False) for i in range(5)]
        report = walk_forward_accumulator_backtest(rounds)
        core = report.product_stats[ProductTier.CORE]
        if core.tickets_found > 0:
            assert core.tickets_won == 0
            assert core.hit_rate == 0.0

    def test_leakage_price_candidates_excluded(self) -> None:
        # A candidate with quote_timestamp > as_of is price-freshness leakage
        rnd = BacktestRound(
            as_of=NOW,
            candidates=[
                _qs(
                    prediction_id="p_future",
                    fixture_id="f_future",
                    league_id="PL",
                    decimal_odds="1.70",
                    quote_timestamp=NOW + timedelta(minutes=5),
                ),
                *_good_pool(5),
            ],
            outcome={},
            outcome_observed_at=NOW + timedelta(hours=3),
        )
        report = walk_forward_accumulator_backtest([rnd])
        assert report.leakage_rows_rejected == 1

    def test_outcome_leakage_withholds_credit(self) -> None:
        # outcome_observed_at <= as_of: result was already known at decision time.
        # The engine still runs (decision is recorded), but the round must not
        # contribute to tickets_found — otherwise hit_rate would be 0% instead
        # of None, making the backtest misleadingly pessimistic.
        rnd = BacktestRound(
            as_of=NOW,
            candidates=_good_pool(6),
            outcome={f"f{i}": 1 for i in range(6)},
            outcome_observed_at=NOW,  # exactly at as_of — leakage
        )
        report = walk_forward_accumulator_backtest([rnd])
        assert report.leakage_rows_rejected >= 1
        core = report.product_stats[ProductTier.CORE]
        # Excluded round must not appear in the hit-rate denominator
        assert core.tickets_found == 0
        assert core.tickets_won == 0
        assert core.hit_rate is None
        assert core.flat_stake_units == 0

    def test_decisions_recorded_per_round(self) -> None:
        rounds = [_backtest_round(i) for i in range(4)]
        report = walk_forward_accumulator_backtest(rounds)
        assert len(report.decisions) == 4

    def test_summary_is_json_serialisable(self) -> None:
        import json
        rounds = [_backtest_round(i) for i in range(3)]
        report = walk_forward_accumulator_backtest(rounds)
        # Should not raise
        json.dumps(report.summary)

    def test_summary_contains_flat_stake_roi(self) -> None:
        rounds = [_backtest_round(i) for i in range(3)]
        report = walk_forward_accumulator_backtest(rounds)
        for stats in report.summary["products"].values():
            assert "flat_stake_roi" in stats
            assert "bookmaker_baseline_roi" not in stats

    def test_outcome_keyed_by_fixture_id(self) -> None:
        # Outcome dict uses fixture_id (NOT prediction_id).
        # If it were keyed by prediction_id the lookup would always miss
        # and no ticket would ever win.
        rounds = [_backtest_round(i, all_win=True) for i in range(5)]
        report = walk_forward_accumulator_backtest(rounds)
        core = report.product_stats[ProductTier.CORE]
        if core.tickets_found > 0:
            assert core.hit_rate == 1.0, (
                "outcome lookup must use fixture_id; prediction_id keying would yield hit_rate=0"
            )

    def test_empty_rounds_produces_empty_report(self) -> None:
        report = walk_forward_accumulator_backtest([])
        assert report.rounds_total == 0
        assert report.leakage_rows_rejected == 0
        assert len(report.decisions) == 0
        for s in report.product_stats.values():
            assert s.tickets_found == 0

    def test_deterministic_with_same_input(self) -> None:
        rounds = [_backtest_round(i) for i in range(5)]
        r1 = walk_forward_accumulator_backtest(rounds)
        r2 = walk_forward_accumulator_backtest(rounds)
        core1 = r1.product_stats[ProductTier.CORE]
        core2 = r2.product_stats[ProductTier.CORE]
        assert core1.tickets_found == core2.tickets_found
        assert core1.tickets_won == core2.tickets_won

    def test_rounds_processed_in_as_of_order(self) -> None:
        # Supply rounds out of order; outcomes assigned to as_of-ordered index
        rounds = [_backtest_round(i) for i in range(3, 0, -1)]
        report = walk_forward_accumulator_backtest(rounds)
        # All decisions should carry strictly increasing as_of
        as_ofs = [d.as_of for d in report.decisions]
        assert as_ofs == sorted(as_ofs)
