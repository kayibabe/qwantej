"""Phase 9 — current_reliability_for_fixture unit tests.

Tests the DB lookup function that wires per-fixture reliability scores into the
signal pipeline.  Uses an in-memory SQLite DB seeded directly (no Alembic
migration runner needed — Base.metadata.create_all is sufficient for pure-unit
test isolation of a single service function).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.models.base import Base
from backend.models.reliability import ReliabilitySnapshot, ReliabilityState
from backend.services.reliability import ReliabilityLookupResult, current_reliability_for_fixture


@pytest.fixture()
def session():
    from backend.core.db import make_engine

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _snap(
    session: Session,
    competition_id: uuid.UUID,
    market_family: str,
    evaluated_as_of: datetime,
    *,
    league_reliability: float = 75.0,
    market_reliability: float = 72.0,
    segment_reliability: float = 73.5,
    status: ReliabilityState = ReliabilityState.QUALIFIED,
    policy_version: str = "reliability-v1",
) -> ReliabilitySnapshot:
    # Seed a minimal valid ReliabilitySnapshot without an FK Competition row —
    # SQLite does not enforce foreign keys by default.
    # created_at is set to evaluated_as_of so the PIT filter (created_at <= as_of)
    # behaves correctly regardless of when the test actually runs.
    row = ReliabilitySnapshot(
        competition_id=competition_id,
        competition_class="tier-1",
        market_family=market_family,
        evaluated_as_of=evaluated_as_of,
        window_start=evaluated_as_of - timedelta(days=90),
        window_end=evaluated_as_of,
        policy_version=policy_version,
        observation_count=120,
        effective_sample_size=110.0,
        shrinkage_weight=0.52,
        league_reliability=league_reliability,
        market_reliability=market_reliability,
        segment_reliability=segment_reliability,
        posterior_standard_deviation=0.04,
        conservative_lower_bound=0.67,
        status=status,
        grade="A",
        components={
            "calibration": 0.82,
            "roi": 0.60,
            "clv": 0.55,
            "variance": 0.70,
            "drawdown": 0.65,
            "stability": 0.80,
        },
        diagnostics={"raw_score": 0.69},
        future_rows_excluded=0,
        input_snapshot_ref="snap-ref-001",
        input_snapshot_hash="a" * 64,
        code_commit="abc1234",
        created_at=evaluated_as_of,  # anchored so created_at <= as_of holds
    )
    session.add(row)
    session.flush()
    return row


NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


class TestCurrentReliabilityForFixture:
    def test_no_snapshot_returns_none(self, session):
        comp_id = uuid.uuid4()
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is None

    def test_returns_lookup_result_type(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              league_reliability=80.0, market_reliability=68.0, segment_reliability=74.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert isinstance(result, ReliabilityLookupResult)

    def test_returns_league_and_market_reliability(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              league_reliability=80.0, market_reliability=68.0, segment_reliability=74.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.league_reliability == pytest.approx(80.0)
        assert result.market_reliability == pytest.approx(68.0)
        assert result.segment_reliability == pytest.approx(74.0)
        assert result.status == "qualified"

    def test_snapshot_id_is_populated(self, session):
        comp_id = uuid.uuid4()
        row = _snap(session, comp_id, "1X2", NOW - timedelta(days=1))
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.snapshot_id == row.id

    def test_snapshot_at_future_evaluated_as_of_excluded(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW + timedelta(hours=1))
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is None

    def test_snapshot_with_future_created_at_excluded(self, session):
        # Even with a historical evaluated_as_of, a snapshot inserted after as_of
        # must not be used — that is the PIT-safety invariant.
        comp_id = uuid.uuid4()
        past_eval = NOW - timedelta(days=30)
        row = ReliabilitySnapshot(
            competition_id=comp_id,
            competition_class="tier-1",
            market_family="1X2",
            evaluated_as_of=past_eval,
            window_start=past_eval - timedelta(days=90),
            window_end=past_eval,
            policy_version="reliability-v1",
            observation_count=100,
            effective_sample_size=95.0,
            shrinkage_weight=0.49,
            league_reliability=78.0,
            market_reliability=74.0,
            segment_reliability=76.0,
            posterior_standard_deviation=0.05,
            conservative_lower_bound=0.66,
            status=ReliabilityState.QUALIFIED,
            grade="A",
            components={"calibration": 0.80, "roi": 0.58, "clv": 0.52,
                        "variance": 0.68, "drawdown": 0.64, "stability": 0.79},
            diagnostics={"raw_score": 0.67},
            future_rows_excluded=0,
            input_snapshot_ref="snap-future-created",
            input_snapshot_hash="b" * 64,
            code_commit="abc1234",
            # Simulates a backdated snapshot inserted after the decision cutoff.
            created_at=NOW + timedelta(hours=1),
        )
        session.add(row)
        session.flush()
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is None

    def test_exact_cutoff_boundary_included(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW, league_reliability=77.0, market_reliability=74.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.league_reliability == pytest.approx(77.0)
        assert result.market_reliability == pytest.approx(74.0)

    def test_returns_most_recent_valid_snapshot(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=30),
              league_reliability=60.0, market_reliability=58.0)
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              league_reliability=82.0, market_reliability=79.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.league_reliability == pytest.approx(82.0)
        assert result.market_reliability == pytest.approx(79.0)

    def test_different_market_family_not_returned(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "O2.5", NOW - timedelta(days=1))
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is None

    def test_different_competition_not_returned(self, session):
        comp_a = uuid.uuid4()
        comp_b = uuid.uuid4()
        _snap(session, comp_a, "1X2", NOW - timedelta(days=1))
        result = current_reliability_for_fixture(session, comp_b, "1X2", as_of=NOW)
        assert result is None

    def test_different_policy_version_not_returned(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              policy_version="reliability-v2")
        # Default policy is "reliability-v1"
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is None

    def test_explicit_policy_version_filter(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              policy_version="reliability-v2",
              league_reliability=88.0, market_reliability=85.0)
        result = current_reliability_for_fixture(
            session, comp_id, "1X2", as_of=NOW, policy_version="reliability-v2"
        )
        assert result is not None
        assert result.league_reliability == pytest.approx(88.0)

    def test_blacklisted_status_propagated(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              status=ReliabilityState.BLACKLISTED,
              league_reliability=42.0, market_reliability=40.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.status == "blacklisted"

    def test_restricted_status_propagated(self, session):
        comp_id = uuid.uuid4()
        _snap(session, comp_id, "1X2", NOW - timedelta(days=1),
              status=ReliabilityState.RESTRICTED,
              league_reliability=50.0, market_reliability=48.0)
        result = current_reliability_for_fixture(session, comp_id, "1X2", as_of=NOW)
        assert result is not None
        assert result.status == "restricted"

    def test_naive_as_of_raises(self, session):
        with pytest.raises(ValueError, match="as_of must be timezone-aware"):
            current_reliability_for_fixture(
                session, uuid.uuid4(), "1X2", as_of=datetime(2026, 9, 10, 12)
            )
