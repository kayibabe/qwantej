"""Tests for query_reliability_observations and rebuild_reliability_snapshots.

Verifies that the post-settlement reliability rebuild correctly converts
settled predictions into ReliabilityObservation objects, excludes superseded
and VOID settlements, and writes fresh ReliabilitySnapshot rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.models.base import Base
from backend.models.fixtures import Competition, Fixture, FixtureStatus, Season, Team
from backend.models.predictions import Prediction
from backend.models.reliability import ReliabilitySnapshot
from backend.models.settlements import Settlement, SettlementOutcome
from backend.services.reliability import (
    query_reliability_observations,
    rebuild_reliability_snapshots,
)

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
DECISION = NOW - timedelta(days=3)
SETTLED = NOW - timedelta(hours=2)


@pytest.fixture()
def session():
    from backend.core.db import make_engine

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _competition(session: Session, *, name: str = "Premier League", tier: int = 1) -> Competition:
    comp = Competition(name=name, tier=tier)
    session.add(comp)
    session.flush()
    return comp


def _fixture(session: Session, competition: Competition) -> Fixture:
    season = Season(competition_id=competition.id, label="2025/2026")
    home = Team(name="Home FC")
    away = Team(name="Away FC")
    session.add_all([season, home, away])
    session.flush()
    fix = Fixture(
        competition_id=competition.id,
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_utc=DECISION - timedelta(hours=2),
        status=FixtureStatus.FINISHED,
        home_goals=2,
        away_goals=1,
    )
    session.add(fix)
    session.flush()
    return fix


def _prediction(
    session: Session,
    fixture: Fixture,
    *,
    calibrated_probability: float | None = 0.62,
    market: str = "1X2",
    executable_odds: float = 1.80,
) -> Prediction:
    pred = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=DECISION,
        decision_as_of=DECISION,
        market=market,
        selection="home",
        calibrated_probability=calibrated_probability,
        conservative_probability=0.58,
        executable_odds=executable_odds,
    )
    session.add(pred)
    session.flush()
    return pred


def _settlement(
    session: Session,
    prediction: Prediction,
    *,
    outcome: SettlementOutcome = SettlementOutcome.WIN,
    taken_odds: float = 1.80,
    clv: float | None = 0.05,
    supersedes_id: uuid.UUID | None = None,
    settled_at: datetime = SETTLED,
) -> Settlement:
    s = Settlement(
        subject_type="prediction",
        subject_id=prediction.id,
        outcome=outcome,
        settled_at=settled_at,
        taken_odds=taken_odds,
        clv=clv,
        supersedes_id=supersedes_id,
    )
    session.add(s)
    session.flush()
    return s


class TestQueryReliabilityObservations:
    def test_no_settled_returns_empty(self, session):
        obs, comp_map = query_reliability_observations(session, as_of=NOW)
        assert obs == []
        assert comp_map == {}

    def test_win_produces_observation(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix, calibrated_probability=0.62)
        _settlement(session, pred, outcome=SettlementOutcome.WIN, taken_odds=2.10)

        obs, comp_map = query_reliability_observations(session, as_of=NOW)
        assert len(obs) == 1
        o = obs[0]
        assert o.observation_id == str(pred.id)
        assert o.league == "Premier League"
        assert o.market_family == "1X2"
        assert o.competition_class == "tier-1"
        assert o.outcome == 1
        assert o.predicted_probability == pytest.approx(0.62)
        # profit for win at decimal odds 2.10 → 2.10 - 1 = 1.10
        assert o.profit_units == pytest.approx(1.10)
        assert o.closing_line_value == pytest.approx(0.05)
        assert comp_map == {"Premier League": comp.id}

    def test_profit_uses_taken_odds_not_taken_probability(self, session):
        # Regression: taken_probability is the model's probability, not decimal odds.
        # At taken_odds=2.00, profit=1.00; 1/taken_probability would give a
        # very different value when calibrated_probability=0.40.
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix, calibrated_probability=0.40)
        _settlement(session, pred, outcome=SettlementOutcome.WIN, taken_odds=2.00)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        # Correct: decimal_odds - 1 = 2.00 - 1 = 1.00
        assert obs[0].profit_units == pytest.approx(1.00)

    def test_loss_produces_observation(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, outcome=SettlementOutcome.LOSS, taken_odds=1.90)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert len(obs) == 1
        o = obs[0]
        assert o.outcome == 0
        assert o.profit_units == pytest.approx(-1.0)

    def test_void_settlement_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, outcome=SettlementOutcome.VOID)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs == []

    def test_settlement_without_taken_odds_excluded(self, session):
        # Settlements with no taken_odds cannot contribute to ROI calculation.
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        s = Settlement(
            subject_type="prediction",
            subject_id=pred.id,
            outcome=SettlementOutcome.WIN,
            settled_at=SETTLED,
            taken_odds=None,
        )
        session.add(s)
        session.flush()

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs == []

    def test_superseded_settlement_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        original = _settlement(session, pred, outcome=SettlementOutcome.LOSS)
        # Correction row supersedes the original; original must not appear.
        _settlement(
            session,
            pred,
            outcome=SettlementOutcome.WIN,
            supersedes_id=original.id,
            settled_at=SETTLED + timedelta(hours=1),
        )

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert len(obs) == 1
        assert obs[0].outcome == 1
        assert obs[0].observation_id == str(pred.id)

    def test_settled_after_as_of_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, settled_at=NOW + timedelta(hours=1))

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs == []

    def test_missing_calibrated_probability_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix, calibrated_probability=None)
        pred.calibrated_probability = None
        session.flush()
        _settlement(session, pred, outcome=SettlementOutcome.WIN)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs == []

    def test_competition_tier_none_defaults_to_tier1(self, session):
        comp = Competition(name="Unknown League", tier=None)
        session.add(comp)
        session.flush()
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs[0].competition_class == "tier-1"

    def test_naive_as_of_raises(self, session):
        with pytest.raises(ValueError, match="as_of must be timezone-aware"):
            query_reliability_observations(session, as_of=datetime(2026, 9, 10, 12))

    def test_no_clv_gives_none(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, clv=None)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs[0].closing_line_value is None


class TestRebuildReliabilitySnapshots:
    def test_no_data_returns_zero(self, session):
        n = rebuild_reliability_snapshots(session, as_of=NOW, code_commit="abc1234")
        assert n == 0

    def test_rebuilds_snapshot_from_settled_predictions(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        for i in range(10):
            pred = _prediction(session, fix, calibrated_probability=0.55 + i * 0.01)
            outcome = SettlementOutcome.WIN if i % 2 == 0 else SettlementOutcome.LOSS
            _settlement(
                session, pred, outcome=outcome,
                settled_at=SETTLED - timedelta(hours=i),
            )

        n = rebuild_reliability_snapshots(session, as_of=NOW, code_commit="abc1234")
        assert n > 0

        snaps = session.query(ReliabilitySnapshot).all()
        assert len(snaps) == n
        for snap in snaps:
            assert snap.competition_id == comp.id
            assert snap.market_family == "1X2"
            assert snap.input_snapshot_ref == "settlement-worker-rebuild"
            assert len(snap.input_snapshot_hash) == 64

    def test_snapshot_hash_changes_when_odds_change(self, session):
        # Regression: hash must cover behavior-affecting fields, not just IDs.
        # Use two different as_of timestamps so each rebuild writes a distinct row
        # (unique constraint is on competition_id, market_family, evaluated_as_of,
        # policy_version — different evaluated_as_of avoids the conflict).
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix, calibrated_probability=0.60)
        _settlement(session, pred, outcome=SettlementOutcome.WIN, taken_odds=2.00)
        rebuild_reliability_snapshots(session, as_of=NOW, code_commit="abc1234")
        first_hash = session.query(ReliabilitySnapshot).first().input_snapshot_hash

        # Change the odds on the settlement row — same IDs, different data.
        s = session.query(Settlement).first()
        s.taken_odds = 3.50
        session.flush()
        now2 = NOW + timedelta(seconds=1)
        rebuild_reliability_snapshots(session, as_of=now2, code_commit="abc1234")
        second_hash = session.query(ReliabilitySnapshot).order_by(
            ReliabilitySnapshot.created_at.desc()
        ).first().input_snapshot_hash

        assert first_hash != second_hash

    def test_snapshot_evaluated_as_of_matches_as_of(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        for i in range(5):
            pred = _prediction(session, fix, calibrated_probability=0.60)
            _settlement(session, pred, outcome=SettlementOutcome.WIN,
                        settled_at=SETTLED - timedelta(hours=i))

        rebuild_reliability_snapshots(session, as_of=NOW, code_commit="abc1234")
        snap = session.query(ReliabilitySnapshot).first()
        assert snap is not None
        assert snap.evaluated_as_of.replace(tzinfo=UTC) == NOW


class TestWorkerTriggersRebuild:
    """Verify that run_settlement() invokes rebuild_reliability_snapshots."""

    def test_run_settlement_writes_reliability_snapshot(self, session):
        from backend.workers.settlement_worker import run_settlement

        comp = _competition(session)
        fix = _fixture(session, comp)
        _prediction(session, fix, calibrated_probability=0.65, executable_odds=1.80)
        session.flush()

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 1
        snaps = session.query(ReliabilitySnapshot).all()
        assert len(snaps) > 0, "reliability snapshot must be written after settlement"
        assert snaps[0].input_snapshot_ref == "settlement-worker-rebuild"

    def test_run_settlement_no_new_settlements_skips_rebuild(self, session):
        # No finished fixtures → total_settled stays 0 → no snapshot written.
        from backend.workers.settlement_worker import run_settlement

        run = run_settlement(session, now=NOW)

        assert run.total_settled == 0
        snaps = session.query(ReliabilitySnapshot).all()
        assert snaps == []
