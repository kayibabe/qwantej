"""Additional tests for backend.services.accumulator.persist_accumulator_decision.

Complements test_accumulator_service.py with:
- Truthy non-boolean paper_only values (strict ``is True`` gate).
- Sequential conflict guard confirming AccumulatorPersistenceError is raised
  rather than silently overwriting the back-link.
- Cross-references to the PostgreSQL concurrent test in
  test_persist_accumulator_pg.py.
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
    AccumulatorPersistenceError,
    persist_accumulator_decision,
)
from qwantej.accumulator import (
    QualifiedSelection,
    build_accumulator_decision,
)
from qwantej.accumulator.decision import AccumulatorDecision
from qwantej.bankroll.state import OperatingState

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
    """Insert *count* independent fixtures and one Prediction per fixture."""
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
    """Build a QualifiedSelection whose IDs match the seeded DB rows."""
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
) -> tuple[AccumulatorDecision, list[QualifiedSelection]]:
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
# Concurrent-persist conflict guard (race condition regression)
# ---------------------------------------------------------------------------


class TestConcurrentPersistConflict:
    def test_second_persist_raises_accumulator_persistence_error(self, engine) -> None:
        """Application-level conflict guard: second session raises, not overwrites.

        This is a *sequential* (not concurrent) test of the accumulator_id-not-None
        guard.  It would pass even without SELECT FOR UPDATE because session 1
        commits before session 2 starts.  Its value is confirming that the guard
        correctly raises AccumulatorPersistenceError rather than silently overwriting
        the back-link.  The database-level SELECT FOR UPDATE locking that blocks a
        truly concurrent second writer is tested in test_persist_accumulator_pg.py.
        """
        # --- Session 1: seed data, persist, commit ---
        with Session(engine) as s1:
            decision, candidates = _decision_and_candidates(s1, count=6)
            result = persist_accumulator_decision(s1, decision, published_at=NOW)
            assert result.accumulators, "CORE should find a ticket from 6 qualifying legs"
            s1.commit()

        # --- Session 2: same decision → conflict ---
        with Session(engine) as s2:
            with pytest.raises(AccumulatorPersistenceError, match="already belongs"):
                persist_accumulator_decision(s2, decision, published_at=NOW)


# ---------------------------------------------------------------------------
# Paper-only safety gate — strict identity check
# ---------------------------------------------------------------------------


class TestPaperOnlyGate:
    def test_live_decision_is_rejected(self, session: Session) -> None:
        """persist_accumulator_decision must refuse a non-paper decision."""
        import dataclasses

        decision, candidates = _decision_and_candidates(session)
        live_decision = dataclasses.replace(decision, paper_only=False)

        with pytest.raises(AccumulatorPersistenceError, match="paper_only"):
            persist_accumulator_decision(session, live_decision, published_at=NOW)

    @pytest.mark.parametrize("truthy_non_bool", [1, "true", 1.0, [True]])
    def test_truthy_non_boolean_paper_only_is_rejected(
        self, session: Session, truthy_non_bool: object
    ) -> None:
        """Gate uses ``is True``, not truthiness — truthy non-booleans must be rejected."""
        import dataclasses

        decision, candidates = _decision_and_candidates(session)
        patched = dataclasses.replace(decision, paper_only=truthy_non_bool)  # type: ignore[arg-type,type-var]

        with pytest.raises(AccumulatorPersistenceError, match="paper_only"):
            persist_accumulator_decision(session, patched, published_at=NOW)

    def test_prediction_back_links_are_set(self, session: Session) -> None:
        """Every leg's prediction must be back-linked after a successful persist."""
        decision, candidates = _decision_and_candidates(session)
        result = persist_accumulator_decision(session, decision, published_at=NOW)
        assert result.accumulators

        for accum in result.accumulators:
            for leg_model in accum.legs:
                pred = session.get(Prediction, leg_model.prediction_id)
                assert pred is not None
                assert pred.accumulator_id == accum.id

    def test_non_leg_predictions_are_not_back_linked(self, session: Session) -> None:
        """Predictions not selected as ticket legs must remain unclaimed."""
        decision, candidates = _decision_and_candidates(session, count=6)
        result = persist_accumulator_decision(session, decision, published_at=NOW)
        assert result.accumulators

        leg_pred_ids: set[uuid.UUID] = set()
        for accum in result.accumulators:
            for leg_model in accum.legs:
                leg_pred_ids.add(leg_model.prediction_id)

        all_pred_ids = {uuid.UUID(c.prediction_id) for c in candidates}
        for pred_id in all_pred_ids - leg_pred_ids:
            pred = session.get(Prediction, pred_id)
            assert pred is not None
            assert pred.accumulator_id is None
