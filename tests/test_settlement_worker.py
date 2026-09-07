"""Tests for backend/workers/settlement_worker.py (Phase 10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Prediction,
    Season,
    Settlement,
    SettlementOutcome as OrmOutcome,
    Team,
)
from backend.workers.settlement_worker import (
    FixtureBatch,
    WorkerRun,
    _finished_fixtures_with_predictions,
    _unsettled_predictions,
    run_settlement,
)

NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
KICKOFF = NOW - timedelta(hours=2)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_fixture(
    session: Session,
    *,
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    status: FixtureStatus = FixtureStatus.FINISHED,
    kickoff_utc: datetime = KICKOFF,
) -> Fixture:
    comp = Competition(name="EPL")
    ssn = Season(competition=comp, label="2026/27")
    home, away = Team(name="Home FC"), Team(name="Away FC")
    f = Fixture(
        competition=comp,
        season=ssn,
        home_team=home,
        away_team=away,
        kickoff_utc=kickoff_utc,
        status=status,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    session.add_all([comp, ssn, home, away, f])
    session.flush()
    return f


def _make_prediction(
    session: Session,
    fixture: Fixture,
    *,
    market: str = "1X2",
    selection: str = "home",
    conservative_probability: float = 0.60,
    executable_odds: float = 1.85,
) -> Prediction:
    p = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=KICKOFF - timedelta(hours=1),
        decision_as_of=KICKOFF - timedelta(hours=1),
        market=market,
        selection=selection,
        conservative_probability=conservative_probability,
        executable_odds=executable_odds,
    )
    session.add(p)
    session.flush()
    return p


def _settlement_for(session: Session, prediction: Prediction) -> Settlement | None:
    return session.scalar(
        select(Settlement).where(
            Settlement.subject_id == prediction.id,
            Settlement.supersedes_id.is_(None),
        )
    )


# ---------------------------------------------------------------------------
# _finished_fixtures_with_predictions
# ---------------------------------------------------------------------------

class TestFinishedFixturesWithPredictions:
    def test_returns_finished_fixture_with_unsettled_prediction(
        self, session: Session
    ) -> None:
        f = _make_fixture(session)
        _make_prediction(session, f)
        since = NOW - timedelta(days=7)
        result = _finished_fixtures_with_predictions(session, since=since)
        assert any(r.id == f.id for r in result)

    def test_excludes_scheduled_fixture(self, session: Session) -> None:
        f = _make_fixture(session, status=FixtureStatus.SCHEDULED)
        _make_prediction(session, f)
        since = NOW - timedelta(days=7)
        result = _finished_fixtures_with_predictions(session, since=since)
        assert not any(r.id == f.id for r in result)

    def test_excludes_fixture_outside_lookback(self, session: Session) -> None:
        old_kickoff = NOW - timedelta(days=30)
        f = _make_fixture(session, kickoff_utc=old_kickoff)
        _make_prediction(session, f)
        since = NOW - timedelta(days=7)
        result = _finished_fixtures_with_predictions(session, since=since)
        assert not any(r.id == f.id for r in result)

    def test_excludes_fully_settled_fixture(self, session: Session) -> None:
        f = _make_fixture(session)
        pred = _make_prediction(session, f)
        session.add(
            Settlement(
                subject_type="prediction",
                subject_id=pred.id,
                outcome=OrmOutcome.WIN,
                settled_at=NOW,
                reason_codes=[],
            )
        )
        session.flush()
        since = NOW - timedelta(days=7)
        result = _finished_fixtures_with_predictions(session, since=since)
        assert not any(r.id == f.id for r in result)

    def test_still_includes_fixture_with_partial_settlement(
        self, session: Session
    ) -> None:
        f = _make_fixture(session)
        pred1 = _make_prediction(session, f, selection="home")
        pred2 = _make_prediction(session, f, selection="draw")
        # Only settle pred1
        session.add(
            Settlement(
                subject_type="prediction",
                subject_id=pred1.id,
                outcome=OrmOutcome.WIN,
                settled_at=NOW,
                reason_codes=[],
            )
        )
        session.flush()
        since = NOW - timedelta(days=7)
        result = _finished_fixtures_with_predictions(session, since=since)
        assert any(r.id == f.id for r in result)


# ---------------------------------------------------------------------------
# _unsettled_predictions
# ---------------------------------------------------------------------------

class TestUnsettledPredictions:
    def test_returns_unsettled(self, session: Session) -> None:
        f = _make_fixture(session)
        pred = _make_prediction(session, f)
        result = _unsettled_predictions(session, f.id)
        assert any(r.id == pred.id for r in result)

    def test_excludes_settled(self, session: Session) -> None:
        f = _make_fixture(session)
        pred = _make_prediction(session, f)
        session.add(
            Settlement(
                subject_type="prediction",
                subject_id=pred.id,
                outcome=OrmOutcome.WIN,
                settled_at=NOW,
                reason_codes=[],
            )
        )
        session.flush()
        result = _unsettled_predictions(session, f.id)
        assert not any(r.id == pred.id for r in result)


# ---------------------------------------------------------------------------
# run_settlement
# ---------------------------------------------------------------------------

class TestRunSettlement:
    def test_settles_home_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=2, away_goals=1)
        pred = _make_prediction(session, f, market="1X2", selection="home")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        assert run.total_errors == 0
        row = _settlement_for(session, pred)
        assert row is not None
        assert row.outcome == OrmOutcome.WIN

    def test_settles_away_win(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=0, away_goals=2)
        pred = _make_prediction(session, f, market="1X2", selection="away")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        row = _settlement_for(session, pred)
        assert row.outcome == OrmOutcome.WIN

    def test_settles_loss(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=2, away_goals=0)
        pred = _make_prediction(session, f, market="1X2", selection="away")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        row = _settlement_for(session, pred)
        assert row.outcome == OrmOutcome.LOSS

    def test_skips_fixture_with_no_goals_recorded(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=None, away_goals=None)
        _make_prediction(session, f)

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 0
        assert run.batches[0].skipped_no_result == 1

    def test_brier_and_clv_fields_populated(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=0)
        pred = _make_prediction(
            session, f,
            market="1X2",
            selection="home",
            conservative_probability=0.65,
            executable_odds=1.80,
        )
        run = run_settlement(session, now=NOW)
        assert run.total_settled == 1
        row = _settlement_for(session, pred)
        assert row.brier_contribution is not None
        assert row.taken_probability is not None
        # No post-kickoff closing quote → CLV is None
        assert row.clv is None

    def test_idempotent_on_second_run(self, session: Session) -> None:
        f = _make_fixture(session)
        _make_prediction(session, f)

        run_settlement(session, now=NOW)
        session.flush()

        # After the first run the fixture is fully settled, so _finished_fixtures_with_predictions
        # excludes it entirely on the second pass — no batches, no errors.
        run2 = run_settlement(session, now=NOW)
        assert run2.total_settled == 0
        assert run2.total_errors == 0
        assert len(run2.batches) == 0

    def test_settles_multiple_predictions_for_same_fixture(
        self, session: Session
    ) -> None:
        # home 2-0: home wins, away loses, draw loses
        f = _make_fixture(session, home_goals=2, away_goals=0)
        p_home = _make_prediction(session, f, selection="home")
        p_draw = _make_prediction(session, f, selection="draw")
        p_away = _make_prediction(session, f, selection="away")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 3
        assert _settlement_for(session, p_home).outcome == OrmOutcome.WIN
        assert _settlement_for(session, p_draw).outcome == OrmOutcome.LOSS
        assert _settlement_for(session, p_away).outcome == OrmOutcome.LOSS

    def test_settles_btts_market(self, session: Session) -> None:
        f = _make_fixture(session, home_goals=1, away_goals=1)
        pred = _make_prediction(session, f, market="BTTS", selection="yes")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        assert _settlement_for(session, pred).outcome == OrmOutcome.WIN

    def test_drift_checked_flag_set(self, session: Session) -> None:
        run = run_settlement(session, now=NOW)
        assert run.drift_checked is True

    def test_error_recorded_for_unknown_market(self, session: Session) -> None:
        f = _make_fixture(session)
        _make_prediction(session, f, market="HANDICAP", selection="home")

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 0
        assert run.total_errors == 1
        assert "resolve_outcome" in run.batches[0].errors[0]
