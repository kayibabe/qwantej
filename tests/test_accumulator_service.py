"""Tests for backend/services/accumulator.py — persist_accumulator_decision."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
    TicketStatus,
)
from backend.services.accumulator import (
    AccumulatorPersistenceError,
    persist_accumulator_decision,
)
from qwantej.accumulator.decision import (
    AccumulatorDecision,
    AccumulatorProductDecision,
    build_accumulator_decision,
)
from qwantej.accumulator.optimiser import AccumulatorResult
from qwantej.accumulator.types import (
    AccumulatorLeg as DomainLeg,
)
from qwantej.accumulator.types import (
    AccumulatorRejectionReason,
    AccumulatorTicket,
    QualifiedSelection,
)
from qwantej.bankroll.state import OperatingState, ProductTier

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
PUBLISHED_AT = NOW + timedelta(seconds=1)
KICKOFF = NOW + timedelta(hours=3)

_LINEAGE = dict(
    model_version="model-v1",
    calibration_version="cal-v1",
    feature_version="feat-v1",
    code_commit="abc123",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(e)
    return e


@pytest.fixture()
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _seed_fixtures_and_predictions(
    session,
    *,
    n: int = 3,
    kickoff: datetime = KICKOFF,
) -> list[tuple[Fixture, Prediction]]:
    """Seed *n* distinct Fixtures, each with one Prediction."""
    comp = Competition(name="EPL")
    ssn = Season(competition=comp, label="2026/27")
    session.add_all([comp, ssn])
    session.flush()

    pairs: list[tuple[Fixture, Prediction]] = []
    for i in range(n):
        home = Team(name=f"Home{i} FC")
        away = Team(name=f"Away{i} FC")
        fixture = Fixture(
            competition=comp,
            season=ssn,
            home_team=home,
            away_team=away,
            kickoff_utc=kickoff,
            status=FixtureStatus.SCHEDULED,
        )
        session.add_all([home, away, fixture])
        session.flush()
        p = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW - timedelta(hours=1),
            decision_as_of=NOW - timedelta(hours=1),
            market=f"MKT{i}",
            selection=f"sel{i}",
            conservative_probability=0.60,
            executable_odds=1.70,
        )
        session.add(p)
        session.flush()
        pairs.append((fixture, p))
    return pairs


# Keep old name as alias for tests that still use it
def _seed_fixture_and_predictions(session, *, n: int = 3, kickoff: datetime = KICKOFF):
    pairs = _seed_fixtures_and_predictions(session, n=n, kickoff=kickoff)
    first_fixture = pairs[0][0]
    predictions = [p for _, p in pairs]
    return first_fixture, predictions


def _make_domain_leg(
    *,
    fixture_id: str,
    league_id: str = "PL",
    market_family: str = "TOTALS",
    decimal_odds: str = "1.70",
) -> DomainLeg:
    return DomainLeg(
        fixture_id=fixture_id,
        league_id=league_id,
        market_family=market_family,
        selection="Over 2.5",
        decimal_odds=Decimal(decimal_odds),
        conservative_probability=0.60,
        edge=0.11,
        qss=88.0,
        dqs=80.0,
        reliability=75.0,
        captured_at=NOW - timedelta(minutes=30),
    )


def _make_ticket(legs: tuple[DomainLeg, ...]) -> AccumulatorTicket:
    from qwantej.accumulator.constraints import (
        combined_odds,
        conservative_joint_probability,
        dependence_penalty,
        stressed_joint_probability,
    )
    return AccumulatorTicket(
        legs=legs,
        product=ProductTier.CORE,
        combined_odds=combined_odds(legs),
        conservative_joint_probability=conservative_joint_probability(legs),
        stressed_joint_probability=stressed_joint_probability(legs, 0.05),
        objective_score=0.40,
        dependence_penalty_applied=dependence_penalty(legs),
    )


def _make_result_with_ticket(ticket: AccumulatorTicket, product: ProductTier) -> AccumulatorResult:
    return AccumulatorResult(
        product=product,
        ticket=ticket,
        rejection_reason=None,
        legs_evaluated=len(ticket.legs),
        legs_qualified=len(ticket.legs),
        combinations_evaluated=1,
        combinations_rejected_odds_band=0,
        combinations_rejected_concentration=0,
        combinations_rejected_ticket_ev=0,
        search_truncated=False,
        policy_version=f"accumulator-policy-{product.value}-v1",
        as_of=NOW,
    )


def _make_result_no_ticket(product: ProductTier) -> AccumulatorResult:
    return AccumulatorResult(
        product=product,
        ticket=None,
        rejection_reason=AccumulatorRejectionReason.INSUFFICIENT_QUALIFIED_LEGS,
        legs_evaluated=0,
        legs_qualified=0,
        combinations_evaluated=0,
        combinations_rejected_odds_band=0,
        combinations_rejected_concentration=0,
        combinations_rejected_ticket_ev=0,
        search_truncated=False,
        policy_version=f"accumulator-policy-{product.value}-v1",
        as_of=NOW,
    )


def _stub_decision(
    *,
    core_ticket: AccumulatorTicket | None = None,
    operating_state: OperatingState = OperatingState.NORMAL,
    paper_only: bool = True,
) -> AccumulatorDecision:
    """Build an AccumulatorDecision with a hand-crafted CORE ticket (others empty)."""
    products = []
    for product in ProductTier:
        ticket = core_ticket if product is ProductTier.CORE else None
        if ticket is not None:
            result = _make_result_with_ticket(ticket, product)
        else:
            result = _make_result_no_ticket(product)
        products.append(
            AccumulatorProductDecision(product=product, result=result, stake_decision=None)
        )
    return AccumulatorDecision(
        as_of=NOW,
        operating_state=operating_state,
        candidate_count=3,
        input_manifest_hash="a" * 64,
        products=tuple(products),
        paper_only=paper_only,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def _build_legs_and_mapping(
    pairs: list[tuple[Fixture, Prediction]],
) -> tuple[tuple[DomainLeg, ...], dict[str, uuid.UUID]]:
    """Return (legs, fixture_to_prediction) for a list of (fixture, prediction) pairs."""
    legs = tuple(
        _make_domain_leg(
            fixture_id=str(fix.id),
            league_id=f"L{i}",
            market_family=f"MKT{i}",
        )
        for i, (fix, _) in enumerate(pairs)
    )
    fixture_to_prediction = {str(fix.id): pred.id for fix, pred in pairs}
    return legs, fixture_to_prediction


class TestPersistHappyPath:
    def test_writes_accumulator_row_for_ticket(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction=fixture_to_prediction,
            published_at=PUBLISHED_AT,
        )

        assert len(result.accumulators) == 1
        acc = result.accumulators[0]
        assert acc.product == "core"
        assert acc.status is TicketStatus.PENDING
        assert acc.paper_only is True
        assert acc.input_manifest_hash == "a" * 64
        assert acc.risk_state == "normal"
        assert acc.decision_cutoff == NOW

    def test_writes_one_leg_per_ticket_leg(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction=fixture_to_prediction,
            published_at=PUBLISHED_AT,
        )

        assert result.legs_written == 3
        acc = result.accumulators[0]
        db_legs = (
            session.query(AccumulatorLeg)
            .filter(AccumulatorLeg.accumulator_id == acc.id)
            .order_by(AccumulatorLeg.leg_index)
            .all()
        )
        assert len(db_legs) == 3
        for i, (db_leg, (_, pred)) in enumerate(zip(db_legs, pairs, strict=True)):
            assert db_leg.leg_index == i
            assert db_leg.prediction_id == pred.id

    def test_links_prediction_accumulator_id(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction=fixture_to_prediction,
            published_at=PUBLISHED_AT,
        )

        acc = result.accumulators[0]
        for _, pred in pairs:
            session.expire(pred)
            linked = session.get(Prediction, pred.id)
            assert linked is not None
            assert linked.accumulator_id == acc.id

    def test_no_tickets_writes_nothing(self, session) -> None:
        decision = _stub_decision(core_ticket=None)
        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction={},
            published_at=PUBLISHED_AT,
        )
        assert result.accumulators == []
        assert result.legs_written == 0
        assert session.query(Accumulator).count() == 0

    def test_combined_odds_stored_correctly(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction=fixture_to_prediction,
            published_at=PUBLISHED_AT,
        )

        acc = result.accumulators[0]
        expected_odds = float(Decimal("1.70") ** 3)
        assert abs(float(acc.combined_odds) - expected_odds) < 1e-4


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------


class TestPersistValidation:
    def test_non_paper_raises(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket, paper_only=False)
        with pytest.raises(AccumulatorPersistenceError, match="paper_only"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=fixture_to_prediction,
                published_at=PUBLISHED_AT,
            )

    def test_naive_published_at_raises(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)
        with pytest.raises(AccumulatorPersistenceError, match="timezone-aware"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=fixture_to_prediction,
                published_at=datetime(2026, 9, 8, 12),  # naive
            )

    def test_missing_fixture_to_prediction_entry_raises(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, _ = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)
        with pytest.raises(AccumulatorPersistenceError, match="fixture_to_prediction missing"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction={},  # empty — every fixture_id is missing
                published_at=PUBLISHED_AT,
            )

    def test_nonexistent_prediction_raises(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)
        # Replace all predictions with phantom UUIDs
        phantom_mapping = {fid: uuid.uuid4() for fid in fixture_to_prediction}
        with pytest.raises(AccumulatorPersistenceError, match="does not exist"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=phantom_mapping,
                published_at=PUBLISHED_AT,
            )

    def test_already_linked_prediction_raises(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        # Pre-link the first prediction to another accumulator
        pairs[0][1].accumulator_id = uuid.uuid4()
        session.flush()

        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)
        with pytest.raises(AccumulatorPersistenceError, match="already belongs"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=fixture_to_prediction,
                published_at=PUBLISHED_AT,
            )

    def test_nothing_written_when_validation_fails(self, session) -> None:
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, _ = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        with pytest.raises(AccumulatorPersistenceError):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction={},  # missing entry
                published_at=PUBLISHED_AT,
            )

        assert session.query(Accumulator).count() == 0
        assert session.query(AccumulatorLeg).count() == 0

    def test_cross_product_shared_prediction_raises(self, session) -> None:
        """Two product tickets sharing a leg would overwrite prediction.accumulator_id."""
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, fixture_to_prediction = _build_legs_and_mapping(pairs)
        # Build a CORE ticket and a GROWTH ticket that share the same legs.
        core_ticket = _make_ticket(legs)
        growth_ticket = AccumulatorTicket(
            legs=legs,
            product=ProductTier.GROWTH,
            combined_odds=core_ticket.combined_odds,
            conservative_joint_probability=core_ticket.conservative_joint_probability,
            stressed_joint_probability=core_ticket.stressed_joint_probability,
            objective_score=core_ticket.objective_score,
            dependence_penalty_applied=core_ticket.dependence_penalty_applied,
        )

        # Craft a decision with both CORE and GROWTH tickets on the same legs.
        products = []
        for product in ProductTier:
            if product is ProductTier.CORE:
                result = _make_result_with_ticket(core_ticket, product)
            elif product is ProductTier.GROWTH:
                result = _make_result_with_ticket(growth_ticket, product)
            else:
                result = _make_result_no_ticket(product)
            products.append(
                AccumulatorProductDecision(product=product, result=result, stake_decision=None)
            )
        decision = AccumulatorDecision(
            as_of=NOW,
            operating_state=OperatingState.NORMAL,
            candidate_count=3,
            input_manifest_hash="b" * 64,
            products=tuple(products),
            paper_only=True,
        )

        with pytest.raises(AccumulatorPersistenceError, match="claimed by both"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=fixture_to_prediction,
                published_at=PUBLISHED_AT,
            )

        assert session.query(Accumulator).count() == 0
        assert session.query(AccumulatorLeg).count() == 0

    def test_swapped_fixture_prediction_mapping_raises(self, session) -> None:
        """Mapping that points a fixture_id to a prediction on a *different* fixture."""
        pairs = _seed_fixtures_and_predictions(session, n=3)
        legs, correct_mapping = _build_legs_and_mapping(pairs)
        ticket = _make_ticket(legs)
        decision = _stub_decision(core_ticket=ticket)

        # Swap: fixture 0 → prediction 1, fixture 1 → prediction 0, fixture 2 stays
        fix0_id = str(pairs[0][0].id)
        fix1_id = str(pairs[1][0].id)
        fix2_id = str(pairs[2][0].id)
        swapped_mapping = {
            fix0_id: pairs[1][1].id,  # wrong fixture
            fix1_id: pairs[0][1].id,  # wrong fixture
            fix2_id: pairs[2][1].id,
        }

        with pytest.raises(AccumulatorPersistenceError, match="belongs to fixture"):
            persist_accumulator_decision(
                session, decision,
                fixture_to_prediction=swapped_mapping,
                published_at=PUBLISHED_AT,
            )

        assert session.query(Accumulator).count() == 0
        assert session.query(AccumulatorLeg).count() == 0


# ---------------------------------------------------------------------------
# Integration: using build_accumulator_decision output directly
# ---------------------------------------------------------------------------


class TestPersistFromRealDecision:
    def _qs(self, fixture_id: str, prediction_id: str, *, i: int) -> QualifiedSelection:
        return QualifiedSelection(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            league_id=f"L{i}",
            market_family="TOTALS",
            selection="Over 2.5",
            calibrated_probability=0.62,
            conservative_probability=0.60,
            decimal_odds=Decimal("1.70"),
            edge=0.11,
            qss=88.0,
            dqs=80.0,
            reliability=75.0,
            quote_timestamp=NOW - timedelta(minutes=30),
            **_LINEAGE,
        )

    def test_real_decision_persists_cleanly(self, session) -> None:
        fixtures_and_predictions = []
        for i in range(6):
            comp = Competition(name=f"League{i}")
            ssn = Season(competition=comp, label="2026/27")
            home = Team(name=f"Home{i}")
            away = Team(name=f"Away{i}")
            fixture = Fixture(
                competition=comp, season=ssn, home_team=home, away_team=away,
                kickoff_utc=KICKOFF, status=FixtureStatus.SCHEDULED,
            )
            session.add_all([comp, ssn, home, away, fixture])
            session.flush()
            p = Prediction(
                fixture_id=fixture.id,
                prediction_timestamp=NOW - timedelta(hours=1),
                decision_as_of=NOW - timedelta(hours=1),
                market="TOTALS",
                selection="Over 2.5",
                conservative_probability=0.60,
                executable_odds=1.70,
            )
            session.add(p)
            session.flush()
            fixtures_and_predictions.append((fixture, p))

        candidates = [
            self._qs(str(fix.id), str(pred.id), i=i)
            for i, (fix, pred) in enumerate(fixtures_and_predictions)
        ]
        decision = build_accumulator_decision(
            candidates,
            as_of=NOW,
            operating_state=OperatingState.NORMAL,
            current_bankroll=1000.0,
            available_bankroll=1000.0,
            committed_daily_exposure=0.0,
        )
        fixture_to_prediction = {
            str(fix.id): pred.id for fix, pred in fixtures_and_predictions
        }

        result = persist_accumulator_decision(
            session, decision,
            fixture_to_prediction=fixture_to_prediction,
            published_at=PUBLISHED_AT,
        )

        # At least CORE should have found a ticket
        assert len(result.accumulators) >= 1
        for acc in result.accumulators:
            assert acc.paper_only is True
            assert acc.status is TicketStatus.PENDING
            assert acc.input_manifest_hash == decision.input_manifest_hash
            db_legs = (
                session.query(AccumulatorLeg)
                .filter(AccumulatorLeg.accumulator_id == acc.id)
                .all()
            )
            assert len(db_legs) >= 2
            for db_leg in db_legs:
                # Each leg's prediction must be back-linked to this accumulator
                pred = session.get(Prediction, db_leg.prediction_id)
                assert pred is not None
                assert pred.accumulator_id == acc.id
