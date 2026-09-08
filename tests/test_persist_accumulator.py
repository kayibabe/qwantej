"""Tests for backend.services.accumulator.persist_accumulator_decision.

Covers:
- Happy path: ticket persisted, Accumulator + legs inserted, predictions back-linked.
- No-ticket case: returns None.
- Paper-only gate: raises ValueError when decision.paper_only is False.
- Conflict guard: second sequential call with already-claimed predictions raises
  AccumulatorPersistError (application-level guard).
  The PostgreSQL-backed truly-concurrent test is in test_persist_accumulator_pg.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Team,
)
from backend.services.accumulator import (
    AccumulatorPersistError,
    persist_accumulator_decision,
)
from qwantej.accumulator import (
    QualifiedSelection,
    build_accumulator_decision,
)
from qwantej.bankroll.state import OperatingState, ProductTier

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)

_LINEAGE = dict(
    model_version="model-v1",
    calibration_version="cal-v1",
    feature_version="feat-v1",
    code_commit="abc123",
)


# ---------------------------------------------------------------------------
# DB session fixture — shared engine so two sessions can see each other's data
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_predictions(session: Session, count: int) -> list[tuple[Fixture, Prediction]]:
    """Insert *count* independent fixtures and one Prediction per fixture.

    Returns a list of (fixture, prediction) pairs, in insertion order.
    Each prediction has ``accumulator_id=None`` (unclaimed).
    """
    comp = Competition(name="TestLeague")
    season = Season(competition=comp, label="2026/27")
    home = Team(name="Home")
    away = Team(name="Away")
    session.add_all([comp, season, home, away])
    session.flush()

    pairs: list[tuple[Fixture, Prediction]] = []
    for i in range(count):
        fixture = Fixture(
            competition=comp,
            season=season,
            home_team=home,
            away_team=away,
            kickoff_utc=NOW + timedelta(days=i + 1),
            status=FixtureStatus.SCHEDULED,
        )
        session.add(fixture)
        session.flush()

        prediction = Prediction(
            fixture_id=fixture.id,
            prediction_timestamp=NOW,
            decision_as_of=NOW,
            market="1X2",
            selection="home",
            ensemble_probability=0.52,
            calibrated_probability=0.53,
            conservative_probability=0.50,
        )
        session.add(prediction)
        session.flush()
        pairs.append((fixture, prediction))

    return pairs


def _make_qs(fixture: Fixture, prediction: Prediction, *, index: int) -> QualifiedSelection:
    """Build a QualifiedSelection whose IDs match the seeded DB rows.

    Values mirror the ``_good_pool`` helper in test_accumulator_decision.py so
    the CORE optimiser reliably finds a ticket (stressed EV ≈ +0.8% with
    p=0.60, odds=1.70, 3-leg combination).
    """
    return QualifiedSelection(
        prediction_id=str(prediction.id),
        fixture_id=str(fixture.id),
        league_id=f"L{index % 3}",
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


def _decision_and_candidates(
    session: Session,
    count: int = 6,
) -> tuple[object, list[QualifiedSelection]]:
    """Seed *count* predictions and build a full AccumulatorDecision."""
    pairs = _seed_predictions(session, count)
    candidates = [_make_qs(f, p, index=i) for i, (f, p) in enumerate(pairs)]
    decision = build_accumulator_decision(
        candidates,
        as_of=NOW,
        operating_state=OperatingState.NORMAL,
        current_bankroll=1000.0,
        available_bankroll=1000.0,
        committed_daily_exposure=0.0,
    )
    return decision, candidates


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPersistAccumulatorDecisionHappyPath:
    def test_returns_accumulator_for_core_product(self, session: Session) -> None:
        decision, candidates = _decision_and_candidates(session)
        accum = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=candidates
        )
        # CORE should find a ticket from 6 qualifying legs
        assert accum is not None

    def test_accumulator_fields_match_decision(self, session: Session) -> None:
        decision, candidates = _decision_and_candidates(session)
        accum = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=candidates
        )
        assert accum is not None
        assert accum.product == ProductTier.CORE.value
        assert accum.input_manifest_hash == decision.input_manifest_hash
        assert accum.paper_only is True
        assert accum.decision_cutoff == decision.as_of
        assert accum.risk_state == decision.operating_state.value

    def test_accumulator_legs_are_inserted(self, session: Session) -> None:
        decision, candidates = _decision_and_candidates(session)
        accum = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=candidates
        )
        assert accum is not None
        session.flush()
        # Legs are accessible via the relationship
        assert len(accum.legs) >= 3  # CORE min_legs == 3

    def test_prediction_back_links_are_set(self, session: Session) -> None:
        decision, candidates = _decision_and_candidates(session)
        accum = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=candidates
        )
        assert accum is not None
        # Every leg's prediction must now point to this accumulator
        for leg_model in accum.legs:
            pred = session.get(Prediction, leg_model.prediction_id)
            assert pred is not None
            assert pred.accumulator_id == accum.id

    def test_non_leg_predictions_are_not_back_linked(self, session: Session) -> None:
        """Predictions not selected as ticket legs must remain unclaimed."""
        decision, candidates = _decision_and_candidates(session, count=6)
        accum = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=candidates
        )
        assert accum is not None
        leg_prediction_ids = {leg.prediction_id for leg in accum.legs}
        all_pred_ids = {uuid.UUID(c.prediction_id) for c in candidates}
        unselected = all_pred_ids - leg_prediction_ids
        for pred_id in unselected:
            pred = session.get(Prediction, pred_id)
            assert pred is not None
            assert pred.accumulator_id is None


# ---------------------------------------------------------------------------
# No-ticket cases
# ---------------------------------------------------------------------------


class TestPersistAccumulatorDecisionNoTicket:
    def test_returns_none_when_no_ticket_for_product(self, session: Session) -> None:
        # Empty candidate pool → no ticket for any product
        decision = build_accumulator_decision(
            [],
            as_of=NOW,
            operating_state=OperatingState.NORMAL,
            current_bankroll=1000.0,
            available_bankroll=1000.0,
            committed_daily_exposure=0.0,
        )
        result = persist_accumulator_decision(
            session, decision=decision, product=ProductTier.CORE, candidates=[]
        )
        assert result is None

    def test_returns_none_for_product_with_no_decision(self, session: Session) -> None:
        decision, candidates = _decision_and_candidates(session, count=6)
        # Build a single-leg-only pool that can't form any valid combo; force
        # an alpha product check which needs ≥5 legs in a wider odds band.
        # Since the fixture uses 1.70 odds, ALPHA (min 5 legs, combined ≥10)
        # is very unlikely to find a ticket.  Use the returned decision as-is:
        # if ALPHA has no ticket, persist must return None.
        alpha_decision = next(pd for pd in decision.products if pd.product is ProductTier.ALPHA)
        if alpha_decision.result.ticket is None:
            result = persist_accumulator_decision(
                session, decision=decision, product=ProductTier.ALPHA, candidates=candidates
            )
            assert result is None


# ---------------------------------------------------------------------------
# Concurrent-persist conflict guard (race condition regression)
# ---------------------------------------------------------------------------


class TestConcurrentPersistConflict:
    def test_second_persist_raises_accumulator_persist_error(self, engine) -> None:
        """Application-level conflict guard: second session raises, not overwrites.

        This is a *sequential* (not concurrent) test of the accumulator_id-not-None
        guard.  It would pass even without SELECT FOR UPDATE because session 1
        commits before session 2 starts.  Its value is confirming that the guard
        correctly raises AccumulatorPersistError rather than silently overwriting
        the back-link.  The database-level SELECT FOR UPDATE locking that blocks a
        truly concurrent second writer is tested in test_persist_accumulator_pg.py.
        """
        # --- Session 1: seed data, persist, commit ---
        with Session(engine) as s1:
            decision, candidates = _decision_and_candidates(s1, count=6)
            accum = persist_accumulator_decision(
                s1, decision=decision, product=ProductTier.CORE, candidates=candidates
            )
            assert accum is not None, "CORE should find a ticket from 6 qualifying legs"
            s1.commit()

        # --- Session 2: same decision + same candidates → conflict ---
        with Session(engine) as s2:
            with pytest.raises(AccumulatorPersistError, match="already linked"):
                persist_accumulator_decision(
                    s2,
                    decision=decision,
                    product=ProductTier.CORE,
                    candidates=candidates,
                )

    def test_second_persist_for_different_product_is_allowed(self, engine) -> None:
        """Persisting a second product tier's ticket (different legs) must succeed.

        Each product tier selects its own combination of legs; unless the
        optimiser happens to pick the same prediction for two products, there
        is no conflict.  For CORE and GROWTH with a 6-leg pool the selected
        legs will typically differ (different odds bands), so this test checks
        that the conflict guard does not block unrelated products.
        """
        with Session(engine) as s1:
            decision, candidates = _decision_and_candidates(s1, count=6)
            persist_accumulator_decision(
                s1, decision=decision, product=ProductTier.CORE, candidates=candidates
            )
            s1.commit()

        with Session(engine) as s2:
            growth_pd = next(
                pd for pd in decision.products if pd.product is ProductTier.GROWTH
            )
            if growth_pd.result.ticket is None:
                pytest.skip("GROWTH ticket not found with this pool; skip")

            # Verify that none of the GROWTH legs share a prediction with CORE.
            core_fixture_ids = {
                leg.fixture_id for leg in (
                    next(pd for pd in decision.products if pd.product is ProductTier.CORE)
                    .result.ticket.legs  # type: ignore[union-attr]
                )
            }
            growth_fixture_ids = {leg.fixture_id for leg in growth_pd.result.ticket.legs}
            if core_fixture_ids & growth_fixture_ids:
                pytest.skip("CORE and GROWTH share a leg fixture; overlap test n/a")

            # No overlap → should succeed
            accum_growth = persist_accumulator_decision(
                s2, decision=decision, product=ProductTier.GROWTH, candidates=candidates
            )
            assert accum_growth is not None


# ---------------------------------------------------------------------------
# Paper-only safety gate
# ---------------------------------------------------------------------------


class TestPaperOnlyGate:
    def test_live_decision_is_rejected(self, session: Session) -> None:
        """persist_accumulator_decision must refuse a non-paper decision.

        AccumulatorDecision.paper_only is always True in Phase 8.  This test
        guards against a manually constructed or future non-paper decision
        bypassing the gate before the release process is complete.
        """
        import dataclasses

        decision, candidates = _decision_and_candidates(session)
        # Force paper_only=False — normally impossible via build_accumulator_decision
        live_decision = dataclasses.replace(decision, paper_only=False)

        with pytest.raises(ValueError, match="paper_only"):
            persist_accumulator_decision(
                session,
                decision=live_decision,
                product=ProductTier.CORE,
                candidates=candidates,
            )
