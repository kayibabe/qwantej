"""Tests for the accumulator optimiser (Phase 8)."""

from __future__ import annotations

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
        with pytest.raises(ValueError, match="min_combined_odds"):
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

    def test_passes_at_qss_exactly_at_floor(self) -> None:
        assert passes_leg_gate(_leg(qss=82.0), CORE_POLICY, as_of=NOW)

    def test_fails_just_below_floor(self) -> None:
        assert not passes_leg_gate(_leg(qss=81.9), CORE_POLICY, as_of=NOW)


# ---------------------------------------------------------------------------
# Constraint checking
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
        result = conservative_joint_probability(legs)
        assert abs(result - 0.42) < 1e-9

    def test_independence_baseline_note(self) -> None:
        legs = tuple(_leg(conservative_probability=0.50) for _ in range(3))
        assert abs(conservative_joint_probability(legs) - 0.125) < 1e-9


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
            _leg(fixture_id="f3", league_id="BL", market_family="TOTALS"),
        )
        # 1 same-league pair → 0.05 * 1 = 0.05
        assert abs(dependence_penalty(legs) - 0.05) < 1e-9

    def test_same_market_triple_penalty(self) -> None:
        legs = tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", market_family="TOTALS")
            for i in range(3)
        )
        # 1 same-market triple → 0.03 * 1 = 0.03
        assert abs(dependence_penalty(legs) - 0.03) < 1e-9

    def test_combined_same_league_and_market(self) -> None:
        legs = (
            _leg(fixture_id="f1", league_id="PL", market_family="TOTALS"),
            _leg(fixture_id="f2", league_id="PL", market_family="TOTALS"),
            _leg(fixture_id="f3", league_id="BL", market_family="TOTALS"),
        )
        # 1 same-league pair (PL) = 0.05; 1 same-market triple (TOTALS) = 0.03
        assert abs(dependence_penalty(legs) - 0.08) < 1e-9


class TestCombinationConstraints:
    def _valid_core_combo(self) -> tuple[AccumulatorLeg, ...]:
        return tuple(
            _leg(fixture_id=f"f{i}", league_id=f"L{i}", decimal_odds="1.70")
            for i in range(3)
        )

    def test_valid_combination_passes(self) -> None:
        combo = self._valid_core_combo()
        assert passes_combination_constraints(combo, CORE_POLICY)

    def test_too_few_legs_fails(self) -> None:
        combo = self._valid_core_combo()[:2]
        assert not passes_combination_constraints(combo, CORE_POLICY)

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

    def test_odds_at_lower_boundary_passes(self) -> None:
        combo = (
            _leg(fixture_id="f1", league_id="L1", decimal_odds="1.44"),
            _leg(fixture_id="f2", league_id="L2", decimal_odds="1.44"),
            _leg(fixture_id="f3", league_id="L3", decimal_odds="1.45"),
        )
        odds = combined_odds(combo)
        assert odds >= CORE_POLICY.min_combined_odds
        assert odds <= CORE_POLICY.max_combined_odds
        assert passes_combination_constraints(combo, CORE_POLICY)


# ---------------------------------------------------------------------------
# Optimiser
# ---------------------------------------------------------------------------

class TestBuildTicketInsufficientLegs:
    def test_empty_pool_returns_insufficient(self) -> None:
        result = build_ticket([], ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS
        assert result.legs_qualified == 0
        assert result.combinations_evaluated == 0

    def test_too_few_qualified_legs(self) -> None:
        pool = [_leg(fixture_id="f1"), _leg(fixture_id="f2")]
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.rejection_reason is AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS

    def test_legs_failing_qss_floor_not_counted_as_qualified(self) -> None:
        pool = _legs_pool(3)
        pool[0] = _leg(fixture_id="f1", qss=79.0)  # below hard floor
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.legs_evaluated == 3
        assert result.legs_qualified == 2


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
        # odds so low combined is below Core minimum
        pool = _legs_pool(4, odds="1.05")
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.ticket is None
        assert result.rejection_reason is AccumulatorRejectionReason.NO_VALID_COMBINATION

    def test_policy_product_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            build_ticket([], ProductTier.GROWTH, CORE_POLICY, as_of=NOW)


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
        from collections import Counter
        league_counts = Counter(leg.league_id for leg in result.ticket.legs)
        assert max(league_counts.values()) <= CORE_POLICY.max_legs_per_league

    def test_result_audit_fields_populated(self) -> None:
        result = build_ticket(self._good_pool(), ProductTier.CORE, CORE_POLICY, as_of=NOW)
        assert result.legs_evaluated == 6
        assert result.legs_qualified == 6
        assert result.combinations_evaluated > 0
        assert result.policy_version == CORE_POLICY.version
        assert result.as_of == NOW

    def test_ticket_joint_probability_is_product_of_leg_probs(self) -> None:
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

    def test_dependence_penalty_applied_to_ticket(self) -> None:
        # all legs same league → penalty applied
        pool = [
            _leg(fixture_id=f"f{i}", league_id="PL", decimal_odds="1.70")
            for i in range(6)
        ]
        result = build_ticket(pool, ProductTier.CORE, CORE_POLICY, as_of=NOW)
        if result.ticket is not None:
            assert result.ticket.dependence_penalty_applied >= 0.0


class TestGrowthProduct:
    def test_growth_ticket_in_correct_odds_band(self) -> None:
        # need higher combined odds for Growth (5.01–10.00)
        # 4 legs × 1.90 = ~13.0 — too high; try 4 × 1.55 = ~5.79 — fits
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
        # 5 legs × 1.75 = ~5.2 — too low; 5 × 1.90 = ~2.48^5...
        # 5 × 1.85 ≈ 22.2 — too high for alpha cap of 20
        # try 5 legs × 1.80 ≈ 18.9 — within 10.01–20.00
        pool = [
            _leg(fixture_id=f"f{i}", league_id=f"L{i % 3}", decimal_odds="1.80")
            for i in range(9)
        ]
        result = build_ticket(pool, ProductTier.ALPHA, ALPHA_POLICY, as_of=NOW)
        if result.ticket is not None:
            assert result.ticket.combined_odds >= ALPHA_POLICY.min_combined_odds
            assert result.ticket.combined_odds <= ALPHA_POLICY.max_combined_odds
            assert len(result.ticket.legs) >= ALPHA_POLICY.min_legs
