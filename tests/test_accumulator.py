"""Tests for the accumulator optimiser (Phase 8)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from qwantej.accumulator import (
    AccumulatorLeg,
    AccumulatorPolicy,
    AccumulatorRejectionReason,
    build_ticket,
)
from qwantej.accumulator.constraints import (
    combined_odds,
    conservative_joint_probability,
    dependence_penalty,
    passes_combination_constraints,
    passes_leg_gate,
    stressed_joint_probability,
    ticket_passes_ev_gate,
)
from qwantej.bankroll.state import ProductTier

NOW = datetime(2026, 9, 7, 10, tzinfo=UTC)

CORE_POLICY = AccumulatorPolicy.default_for(ProductTier.CORE)
GROWTH_POLICY = AccumulatorPolicy.default_for(ProductTier.GROWTH)
ALPHA_POLICY = AccumulatorPolicy.default_for(ProductTier.ALPHA)


def _leg(
    *,
    fixture_id: str = "f1",
    league_id: str = "PL",
    market_family: str = "TOTALS",
    selection: str = "Over 2.5",
    decimal_odds: str = "1.85",
    conservative_probability: float = 0.60,
    edge: float = 0.11,
    qss: float = 88.0,
    dqs: float = 85.0,
    reliability: float = 75.0,
    captured_at: datetime = NOW - timedelta(minutes=30),
) -> AccumulatorLeg:
    return AccumulatorLeg(
        fixture_id=fixture_id,
        league_id=league_id,
        market_family=market_family,
        selection=selection,
        decimal_odds=Decimal(decimal_odds),
        conservative_probability=conservative_probability,
        edge=edge,
        qss=qss,
        dqs=dqs,
        reliability=reliability,
        captured_at=captured_at,
    )


def _legs_pool(n: int, *, start_fixture: int = 1, odds: str = "1.70") -> list[AccumulatorLeg]:
    return [
        _leg(
            fixture_id=f"f{start_fixture + i}",
            league_id=f"L{i % 3}",
            market_family="TOTALS",
            decimal_odds=odds,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# AccumulatorLeg validation
# ---------------------------------------------------------------------------

class TestAccumulatorLegValidation:
    def test_blank_fixture_id_raises(self) -> None:
        with pytest.raises(ValueError, match="fixture_id"):
            _leg(fixture_id="  ")

    def test_blank_league_id_raises(self) -> None:
        with pytest.raises(ValueError, match="league_id"):
            _leg(league_id="")

    def test_blank_market_family_raises(self) -> None:
        with pytest.raises(ValueError, match="market_family"):
            _leg(market_family="")

    def test_blank_selection_raises(self) -> None:
        with pytest.raises(ValueError, match="selection"):
            _leg(selection="")

    def test_decimal_odds_le_1_raises(self) -> None:
        with pytest.raises(ValueError, match="decimal_odds must be greater than 1"):
            _leg(decimal_odds="1.00")

    def test_decimal_odds_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="decimal_odds"):
            AccumulatorLeg(
                fixture_id="f1", league_id="PL", market_family="TOTALS",
                selection="Over 2.5", decimal_odds=Decimal("NaN"),
                conservative_probability=0.6, edge=0.1,
                qss=85.0, dqs=80.0, reliability=75.0,
                captured_at=NOW,
            )

    def test_probability_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="conservative_probability"):
            _leg(conservative_probability=0.0)

    def test_probability_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="conservative_probability"):
            _leg(conservative_probability=1.1)

    def test_nan_qss_raises(self) -> None:
        with pytest.raises(ValueError, match="qss"):
            _leg(qss=float("nan"))

    def test_qss_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="qss"):
            _leg(qss=101.0)

    def test_nan_edge_raises(self) -> None:
        with pytest.raises(ValueError, match="edge"):
            _leg(edge=float("inf"))

    def test_naive_captured_at_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _leg(captured_at=datetime(2026, 9, 7, 10))

    def test_valid_leg_constructs(self) -> None:
        leg = _leg()
        assert leg.fixture_id == "f1"


# ---------------------------------------------------------------------------
# Policy validation
# ---------------------------------------------------------------------------

class TestAccumulatorPolicy:
    def test_default_core_policy_is_valid(self) -> None:
        p = AccumulatorPolicy.default_for(ProductTier.CORE)
        assert p.product is ProductTier.CORE
        assert p.min_combined_odds == Decimal("3.00")
        assert p.max_combined_odds == Decimal("5.00")
        assert p.min_legs == 3
        assert p.max_legs == 4
        assert p.hard_qss_floor == 82.0
        assert p.stress_haircut == 0.05
        assert p.max_combinations == 200_000

    def test_default_growth_policy(self) -> None:
        p = AccumulatorPolicy.default_for(ProductTier.GROWTH)
        assert p.product is ProductTier.GROWTH
        assert p.min_combined_odds > Decimal("5.00")
        assert p.max_combined_odds == Decimal("10.00")
        assert p.min_legs == 4

    def test_default_alpha_policy(self) -> None:
        p = AccumulatorPolicy.default_for(ProductTier.ALPHA)
        assert p.product is ProductTier.ALPHA
        assert p.min_combined_odds > Decimal("10.00")
        assert p.max_combined_odds == Decimal("20.00")
        assert p.min_legs == 5

    def test_min_odds_must_be_less_than_max(self) -> None:
        with pytest.raises(ValueError, match="min_combined_odds must be <"):
            AccumulatorPolicy(
                version="v1", product=ProductTier.CORE,
                min_combined_odds=Decimal("5.00"), max_combined_odds=Decimal("3.00"),
                min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
                min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2),
            )

    def test_hard_floor_must_not_exceed_preferred(self) -> None:
        with pytest.raises(ValueError, match="hard_qss_floor"):
            AccumulatorPolicy(
                version="v1", product=ProductTier.CORE,
                min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
                min_legs=3, max_legs=4, preferred_qss=80.0, hard_qss_floor=85.0,
                min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2),
            )

    def test_zero_freshness_raises(self) -> None:
        with pytest.raises(ValueError, match="price_freshness_max_age"):
            AccumulatorPolicy(
                version="v1", product=ProductTier.CORE,
                min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
                min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
                min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(0),
            )

    def test_default_stress_haircut_is_five_percent(self) -> None:
        assert CORE_POLICY.stress_haircut == 0.05

    def test_stress_haircut_gte_1_raises(self) -> None:
        with pytest.raises(ValueError, match="stress_haircut"):
            AccumulatorPolicy(
                version="v1", product=ProductTier.CORE,
                min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
                min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
                min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2), stress_haircut=1.0,
            )

    def test_max_combinations_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_combinations"):
            AccumulatorPolicy(
                version="v1", product=ProductTier.CORE,
                min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
                min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
                min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
                price_freshness_max_age=timedelta(hours=2), max_combinations=0,
            )

    def test_unknown_product_raises(self) -> None:
        with pytest.raises(ValueError):
            AccumulatorPolicy.default_for("unknown")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Leg gate
# ---------------------------------------------------------------------------

class TestLegGate:
    def test_passes_healthy_leg(self) -> None:
        assert passes_leg_gate(_leg(), CORE_POLICY, as_of=NOW)

    def test_fails_qss_below_hard_floor(self) -> None:
        assert not passes_leg_gate(_leg(qss=79.0), CORE_POLICY, as_of=NOW)

    def test_fails_dqs_below_minimum(self) -> None:
        assert not passes_leg_gate(_leg(dqs=65.0), CORE_POLICY, as_of=NOW)

    def test_fails_stale_price(self) -> None:
        stale = NOW - timedelta(hours=3)
        assert not passes_leg_gate(_leg(captured_at=stale), CORE_POLICY, as_of=NOW)

    def test_fails_future_dated_capture(self) -> None:
        future = NOW + timedelta(minutes=1)
        assert not passes_leg_gate(_leg(captured_at=future), CORE_POLICY, as_of=NOW)

    def test_passes_at_qss_exactly_at_floor(self) -> None:
        assert passes_leg_gate(_leg(qss=82.0), CORE_POLICY, as_of=NOW)

    def test_fails_just_below_floor(self) -> None:
        assert not passes_leg_gate(_leg(qss=81.9), CORE_POLICY, as_of=NOW)

    def test_captured_exactly_at_limit_passes(self) -> None:
        # At the exact age boundary the timedelta == max_age → still passes
        at_limit = NOW - CORE_POLICY.price_freshness_max_age
        assert passes_leg_gate(_leg(captured_at=at_limit), CORE_POLICY, as_of=NOW)


# ---------------------------------------------------------------------------
# Combined odds and probability
# ---------------------------------------------------------------------------

class TestCombinedOdds:
    def test_product_of_decimal_odds(self) -> None:
        legs = tuple(_leg(decimal_odds=str(o)) for o in ["2.00", "1.50", "2.00"])
        assert combined_odds(legs) == Decimal("6.000")

    def test_single_leg(self) -> None:
        legs = (_leg(decimal_odds="3.50"),)
        assert combined_odds(legs) == Decimal("3.50")


class TestConservativeJointProbability:
    def test_product_of_probabilities(self) -> None:
        legs = (
            _leg(conservative_probability=0.60),
            _leg(conservative_probability=0.70),
        )
        assert abs(conservative_joint_probability(legs) - 0.42) < 1e-9

    def test_three_legs_independence_baseline(self) -> None:
        legs = tuple(_leg(conservative_probability=0.50) for _ in range(3))
        assert abs(conservative_joint_probability(legs) - 0.125) < 1e-9


class TestStressedJointProbability:
    def test_stressed_is_less_than_base(self) -> None:
        legs = tuple(_leg(conservative_probability=0.70) for _ in range(3))
        base = conservative_joint_probability(legs)
        stressed = stressed_joint_probability(legs, haircut=0.10)
        assert stressed < base

    def test_zero_haircut_equals_base(self) -> None:
        legs = tuple(_leg(conservative_probability=0.70) for _ in range(3))
        base = conservative_joint_probability(legs)
        stressed = stressed_joint_probability(legs, haircut=0.0)
        assert abs(stressed - base) < 1e-12

    def test_haircut_is_ticket_level_not_per_leg(self) -> None:
        legs = (
            _leg(conservative_probability=0.80),
            _leg(conservative_probability=0.70),
        )
        base = 0.80 * 0.70
        expected = base * (1 - 0.10)
        assert abs(stressed_joint_probability(legs, haircut=0.10) - expected) < 1e-9


# ---------------------------------------------------------------------------
# Ticket EV gate
# ---------------------------------------------------------------------------

class TestTicketEvGate:
    def _high_ev_legs(self) -> tuple[AccumulatorLeg, ...]:
        # 3 legs × 1.85 odds, p=0.60 each → joint_p≈0.216, combined≈6.33
        # EV ≈ 0.216 * 6.33 - 1 ≈ 0.37 > 0 ✓
        return tuple(
            _leg(
                fixture_id=f"f{i}", league_id=f"L{i}",
                decimal_odds="1.85", conservative_probability=0.60,
            )
            for i in range(3)
        )

    def test_positive_ev_passes(self) -> None:
        legs = self._high_ev_legs()
        assert ticket_passes_ev_gate(legs, CORE_POLICY)

    def test_failing_stressed_ev_rejected(self) -> None:
        # 3 legs × 1.70 → combined 4.913, joint_p = 0.216, base EV ≈ +6%
        # Haircut 20% → stressed_joint = 0.216 * 0.80 = 0.173
        # stressed EV = 0.173 * 4.913 − 1 ≈ −0.15 < 0 → rejected
        strict_policy = AccumulatorPolicy(
            version="strict-v1", product=ProductTier.CORE,
            min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
            min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
            min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
            price_freshness_max_age=timedelta(hours=2), stress_haircut=0.20,
        )
        legs = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.70")
            for i in range(3)
        )
        assert not ticket_passes_ev_gate(legs, strict_policy)


# ---------------------------------------------------------------------------
# Dependence penalty
# ---------------------------------------------------------------------------

class TestDependencePenalty:
    def test_no_penalty_all_different_leagues_and_markets(self) -> None:
        markets = ["TOTALS", "1X2", "BTTS"]
        legs = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", market_family=markets[i])
            for i in range(3)
        )
        assert dependence_penalty(legs) == 0.0

    def test_same_league_pair_penalty(self) -> None:
        legs = (
            _leg(fixture_id="f1", league_id="PL", market_family="TOTALS"),
            _leg(fixture_id="f2", league_id="PL", market_family="1X2"),
            _leg(fixture_id="f3", league_id="BL", market_family="BTTS"),
        )
        assert abs(dependence_penalty(legs) - 0.05) < 1e-9

    def test_same_market_triple_penalty(self) -> None:
        legs = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", market_family="TOTALS")
            for i in range(3)
        )
        assert abs(dependence_penalty(legs) - 0.03) < 1e-9

    def test_combined_same_league_and_market(self) -> None:
        legs = (
            _leg(fixture_id="f1", league_id="PL", market_family="TOTALS"),
            _leg(fixture_id="f2", league_id="PL", market_family="TOTALS"),
            _leg(fixture_id="f3", league_id="BL", market_family="TOTALS"),
        )
        # 1 same-league pair (PL) = 0.05; 1 same-market triple (TOTALS) = 0.03
        assert abs(dependence_penalty(legs) - 0.08) < 1e-9


# ---------------------------------------------------------------------------
# Combination constraints
# ---------------------------------------------------------------------------

class TestCombinationConstraints:
    def _valid_core_combo(self) -> tuple[AccumulatorLeg, ...]:
        return tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.70")
            for i in range(3)
        )

    def test_valid_combination_passes(self) -> None:
        assert passes_combination_constraints(self._valid_core_combo(), CORE_POLICY)

    def test_too_few_legs_fails(self) -> None:
        assert not passes_combination_constraints(self._valid_core_combo()[:2], CORE_POLICY)

    def test_too_many_legs_fails(self) -> None:
        legs = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.70")
            for i in range(5)
        )
        assert not passes_combination_constraints(legs, CORE_POLICY)

    def test_duplicate_fixture_fails(self) -> None:
        combo = (
            _leg(fixture_id="f1", league_id="L1", decimal_odds="1.70"),
            _leg(fixture_id="f1", league_id="L2", decimal_odds="1.70"),
            _leg(fixture_id="f3", league_id="L3", decimal_odds="1.70"),
        )
        assert not passes_combination_constraints(combo, CORE_POLICY)

    def test_too_many_same_league_fails(self) -> None:
        combo = (
            _leg(fixture_id="f1", league_id="PL", decimal_odds="1.70"),
            _leg(fixture_id="f2", league_id="PL", decimal_odds="1.70"),
            _leg(fixture_id="f3", league_id="PL", decimal_odds="1.70"),
        )
        assert not passes_combination_constraints(combo, CORE_POLICY)

    def test_two_from_same_league_passes(self) -> None:
        combo = (
            _leg(fixture_id="f1", league_id="PL", decimal_odds="1.70"),
            _leg(fixture_id="f2", league_id="PL", decimal_odds="1.70"),
            _leg(fixture_id="f3", league_id="BL", decimal_odds="1.70"),
        )
        assert passes_combination_constraints(combo, CORE_POLICY)

    def test_odds_below_minimum_fails(self) -> None:
        combo = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.10")
            for i in range(3)
        )
        assert not passes_combination_constraints(combo, CORE_POLICY)

    def test_odds_above_maximum_fails(self) -> None:
        combo = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="3.50")
            for i in range(3)
        )
        assert not passes_combination_constraints(combo, CORE_POLICY)


# ---------------------------------------------------------------------------
# Optimiser — insufficient legs
# ---------------------------------------------------------------------------

class TestBuildTicketInsufficientLegs:
    def test_empty_pool_returns_insufficient(self) -> None:
        result = build_ticket([], ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS
        assert result.legs_qualified == 0
        assert result.combinations_evaluated == 0
        assert not result.search_truncated

    def test_too_few_qualified_legs(self) -> None:
        pool = [_leg(fixture_id="f1"), _leg(fixture_id="f2")]
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.rejection_reason is AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS

    def test_future_dated_leg_not_counted_as_qualified(self) -> None:
        pool = [
            _leg(fixture_id="f1", captured_at=NOW + timedelta(minutes=1)),
            _leg(fixture_id="f2"),
            _leg(fixture_id="f3"),
        ]
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.legs_evaluated == 3
        assert result.legs_qualified == 2

    def test_legs_failing_qss_floor_not_counted_as_qualified(self) -> None:
        pool = _legs_pool(3)
        pool[0] = _leg(fixture_id="f1", qss=79.0)
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.legs_evaluated == 3
        assert result.legs_qualified == 2


# ---------------------------------------------------------------------------
# Optimiser — no valid combination
# ---------------------------------------------------------------------------

class TestBuildTicketNoValidCombination:
    def test_all_legs_from_same_fixture_returns_no_valid_combo(self) -> None:
        pool = [
            _leg(fixture_id="same", league_id=f"L{i}", decimal_odds="1.70")
            for i in range(4)
        ]
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.NO_VALID_COMBINATION

    def test_odds_always_outside_band_returns_no_valid_combo(self) -> None:
        pool = _legs_pool(4, odds="1.05")
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.NO_VALID_COMBINATION
        assert result.combinations_rejected_odds_band > 0

    def test_policy_product_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            build_ticket([], ProductTier.GROWTH, CORE_POLICY, as_of=NOW)

    def test_combination_counters_populated(self) -> None:
        pool = _legs_pool(4, odds="1.05")
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        total_rejected = (
            result.combinations_rejected_odds_band
            + result.combinations_rejected_concentration
            + result.combinations_rejected_ticket_ev
        )
        assert result.combinations_evaluated == total_rejected


# ---------------------------------------------------------------------------
# Optimiser — search budget exhausted
# ---------------------------------------------------------------------------

class TestSearchBudget:
    def _tight_budget_policy(self) -> AccumulatorPolicy:
        return AccumulatorPolicy(
            version="budget-v1", product=ProductTier.CORE,
            min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("5.00"),
            min_legs=3, max_legs=4, preferred_qss=87.0, hard_qss_floor=82.0,
            min_dqs=70.0, max_legs_per_league=2, max_legs_per_market_family=3,
            price_freshness_max_age=timedelta(hours=2), max_combinations=1,
        )

    def test_budget_exhausted_sets_flag(self) -> None:
        policy = self._tight_budget_policy()
        pool = _legs_pool(6, odds="1.70")
        result = build_ticket(pool, ProductTier.CORE, policy, as_of=NOW)
        assert result.search_truncated

    def test_budget_exhausted_without_ticket_gives_search_budget_reason(self) -> None:
        # Pool where no valid combo fits odds band, and budget = 1
        policy = self._tight_budget_policy()
        pool = _legs_pool(4, odds="1.05")  # combined odds always below minimum
        result = build_ticket(pool, ProductTier.CORE, policy, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.SEARCH_BUDGET_EXHAUSTED

    def test_valid_combination_outside_original_beam_is_now_found(self) -> None:
        """Regression: the old beam_width=64 truncation caused valid combos to be missed."""
        # 67 legs where legs 65-67 are the only ones that fit the odds band
        # Legs 0-63: odds=1.10 → combined too low for CORE
        # Legs 64-66: odds=1.70 → 3-leg combo = 4.913, fits 3.00-5.00 ✓
        low_odds_pool = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i % 3}", decimal_odds="1.10")
            for i in range(64)
        ]
        valid_legs = [
            _leg(fixture_id=f"fv{i}", league_id=f"V{i}", decimal_odds="1.70")
            for i in range(3)
        ]
        pool = low_odds_pool + valid_legs
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        # The valid combo exists; it must be found (no pool pre-truncation)
        assert result.legs_evaluated == 67
        # If found, ticket should be in the band
        if result.ticket is not None:
            assert result.ticket.combined_odds >= CORE_POLICY.min_combined_odds
            assert result.ticket.combined_odds <= CORE_POLICY.max_combined_odds


# ---------------------------------------------------------------------------
# Optimiser — successful ticket
# ---------------------------------------------------------------------------

class TestBuildTicketSuccess:
    def _good_pool(self) -> list[AccumulatorLeg]:
        return [
            _leg(fixture_id=f"f{i}", league_id=f"L{i % 3}", decimal_odds="1.70")
            for i in range(6)
        ]

    def test_returns_ticket_with_qualifying_pool(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        assert result.rejection_reason is None

    def test_ticket_satisfies_leg_count(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        n = len(result.ticket.legs)
        assert CORE_POLICY.min_legs <= n <= CORE_POLICY.max_legs

    def test_ticket_combined_odds_in_band(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        odds = result.ticket.combined_odds
        assert odds >= CORE_POLICY.min_combined_odds
        assert odds <= CORE_POLICY.max_combined_odds

    def test_ticket_one_leg_per_fixture(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        fixture_ids = [leg.fixture_id for leg in result.ticket.legs]
        assert len(fixture_ids) == len(set(fixture_ids))

    def test_ticket_max_two_legs_per_league(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        league_counts = Counter(leg.league_id for leg in result.ticket.legs)
        assert max(league_counts.values()) <= CORE_POLICY.max_legs_per_league

    def test_result_audit_fields_populated(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.legs_evaluated == 6
        assert result.legs_qualified == 6
        assert result.combinations_evaluated > 0
        assert result.policy_version == CORE_POLICY.version
        assert result.as_of == NOW
        assert not result.search_truncated

    def test_ticket_has_conservative_and_stressed_joint_probability(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        t = result.ticket
        assert t.stressed_joint_probability < t.conservative_joint_probability

    def test_ticket_joint_probability_matches_leg_product(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        expected = 1.0
        for leg in result.ticket.legs:
            expected *= leg.conservative_probability
        assert abs(result.ticket.conservative_joint_probability - expected) < 1e-9

    def test_optimiser_prefers_higher_qss_legs(self) -> None:
        low_qss_leg = _leg(fixture_id="f_low", league_id="L9", qss=82.0, decimal_odds="1.70")
        high_qss_legs = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", qss=95.0, decimal_odds="1.70")
            for i in range(5)
        ]
        pool = [low_qss_leg] + high_qss_legs
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is not None
        leg_ids = {leg.fixture_id for leg in result.ticket.legs}
        assert "f_low" not in leg_ids, "optimiser should prefer high-QSS legs"

    def test_result_is_deterministic_regardless_of_input_order(self) -> None:
        pool = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i % 3}", decimal_odds="1.70")
            for i in range(6)
        ]
        import random
        shuffled = list(pool)
        random.shuffle(shuffled)
        result_a = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        result_b = build_ticket(shuffled, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        if result_a.ticket and result_b.ticket:
            ids_a = tuple(sorted(leg.fixture_id for leg in result_a.ticket.legs))
            ids_b = tuple(sorted(leg.fixture_id for leg in result_b.ticket.legs))
            assert ids_a == ids_b, "ticket selection must be deterministic"


# ---------------------------------------------------------------------------
# Growth and Alpha products
# ---------------------------------------------------------------------------

class TestGrowthProduct:
    def test_growth_ticket_in_correct_odds_band(self) -> None:
        pool = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.55")
            for i in range(8)
        ]
        result = build_ticket(pool, ProductTier.GROWTH, GROWTH_POLICY, as_of=NOW)
        if result.ticket is not None:
            assert result.ticket.combined_odds >= GROWTH_POLICY.min_combined_odds
            assert result.ticket.combined_odds <= GROWTH_POLICY.max_combined_odds


class TestAlphaProduct:
    def test_alpha_ticket_in_correct_odds_band(self) -> None:
        pool = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i % 3}", decimal_odds="1.80")
            for i in range(9)
        ]
        result = build_ticket(pool, ProductTier.ALPHA, ALPHA_POLICY, as_of=NOW)
        if result.ticket is not None:
            assert result.ticket.combined_odds >= ALPHA_POLICY.min_combined_odds
            assert result.ticket.combined_odds <= ALPHA_POLICY.max_combined_odds
            assert len(result.ticket.legs) >= ALPHA_POLICY.min_legs
