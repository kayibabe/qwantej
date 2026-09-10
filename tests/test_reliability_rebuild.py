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
    calibrated_probability: float = 0.62,
    market: str = "1X2",
) -> Prediction:
    pred = Prediction(
        fixture_id=fixture.id,
        prediction_timestamp=DECISION,
        decision_as_of=DECISION,
        market=market,
        selection="home",
        calibrated_probability=calibrated_probability,
        conservative_probability=0.58,
    )
    session.add(pred)
    session.flush()
    return pred


def _settlement(
    session: Session,
    prediction: Prediction,
    *,
    outcome: SettlementOutcome = SettlementOutcome.WIN,
    taken_probability: float = 0.50,
    clv: float | None = 0.05,
    supersedes_id: uuid.UUID | None = None,
    settled_at: datetime = SETTLED,
) -> Settlement:
    s = Settlement(
        subject_type="prediction",
        subject_id=prediction.id,
        outcome=outcome,
        settled_at=settled_at,
        taken_probability=taken_probability,
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
        _settlement(session, pred, outcome=SettlementOutcome.WIN, taken_probability=0.50)

        obs, comp_map = query_reliability_observations(session, as_of=NOW)
        assert len(obs) == 1
        o = obs[0]
        assert o.observation_id == str(pred.id)
        assert o.league == "Premier League"
        assert o.market_family == "1X2"
        assert o.competition_class == "tier-1"
        assert o.outcome == 1
        assert o.predicted_probability == pytest.approx(0.62)
        # profit for win at taken_probability=0.50 → 1/0.5 - 1 = 1.0
        assert o.profit_units == pytest.approx(1.0)
        assert o.closing_line_value == pytest.approx(0.05)
        assert comp_map == {"Premier League": comp.id}

    def test_loss_produces_observation(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, outcome=SettlementOutcome.LOSS, taken_probability=0.45)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert len(obs) == 1
        o = obs[0]
        assert o.outcome == 0
        assert o.profit_units == pytest.approx(-1.0)

    def test_void_settlement_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        _settlement(session, pred, outcome=SettlementOutcome.VOID, taken_probability=0.50)

        obs, _ = query_reliability_observations(session, as_of=NOW)
        assert obs == []

    def test_superseded_settlement_excluded(self, session):
        comp = _competition(session)
        fix = _fixture(session, comp)
        pred = _prediction(session, fix)
        original = _settlement(session, pred, outcome=SettlementOutcome.LOSS)
        # Correction row supersedes the original
        correction = _settlement(
            session,
            pred,
            outcome=SettlementOutcome.WIN,
            supersedes_id=original.id,
            settled_at=SETTLED + timedelta(hours=1),
        )

        obs, _ = query_reliability_observations(session, as_of=NOW)
        # Only the correction (WIN) should appear, not the superseded LOSS
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
        # Override the calibrated_probability to None after flush
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
        # Seed 5 wins and 5 losses to exceed minimum_qualified_effective_sample
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
        # evaluated_as_of is stored as naive UTC in SQLite
        assert snap.evaluated_as_of.replace(tzinfo=UTC) == NOW
