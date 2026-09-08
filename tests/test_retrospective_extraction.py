"""Tests for the retrospective feature extractor using a seeded SQLite session.

Verifies the isolation rules:
  - Future fixtures not affecting features (kickoff_utc >= target excluded)
  - Same-kickoff fixtures excluded (strictly less than, not less-or-equal)
  - Unfinished / null-goal fixtures excluded
  - Competition isolation (fixtures from other competitions ignored)
  - Changed mutable goals produce a different retrospective_fixture_hash
  - extract_retrospective_features returns correct historical count and features
  - retrospective_fixture_hash is deterministic across calls with same inputs
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import Base, Competition, Fixture, FixtureStatus, Season, Team
from backend.services.retrospective_extraction import (
    RetrospectiveResult,
    extract_retrospective_features,
    retrospective_dataset_hash,
    retrospective_fixture_hash,
)

# ---------------------------------------------------------------------------
# Fixtures (pytest)
# ---------------------------------------------------------------------------

KICKOFF_BASE = datetime(2025, 9, 1, 15, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    tx = conn.begin()
    sess = Session(bind=conn)
    try:
        yield sess
    finally:
        sess.close()
        tx.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


def _competition(session: Session, name: str = "Test League") -> Competition:
    comp = Competition(name=name)
    session.add(comp)
    session.flush()
    return comp


def _season(session: Session, competition: Competition, label: str = "2025") -> Season:
    s = Season(competition=competition, label=label)
    session.add(s)
    session.flush()
    return s


def _team(session: Session, name: str) -> Team:
    t = Team(name=name)
    session.add(t)
    session.flush()
    return t


def _fixture(
    session: Session,
    competition: Competition,
    season: Season,
    home: Team,
    away: Team,
    kickoff: datetime,
    *,
    home_goals: int | None = None,
    away_goals: int | None = None,
    status: FixtureStatus = FixtureStatus.FINISHED,
) -> Fixture:
    f = Fixture(
        competition=competition,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=kickoff,
        status=status,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    session.add(f)
    session.flush()
    return f


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetrospectiveExclusions:
    def test_future_fixture_not_included_in_history(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Home FC")
        away = _team(session, "Away FC")
        third = _team(session, "Third FC")

        # Past result
        past = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=7),
            home_goals=2, away_goals=1,
        )
        # Target fixture
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=0,
        )
        # Future result — must NOT appear in target's training history
        _fixture(
            session, comp, s, home, third,
            KICKOFF_BASE + timedelta(days=7),
            home_goals=0, away_goals=3,
        )

        _, hist = extract_retrospective_features(session, target)
        ids = {str(r.fixture_id) for r in hist}
        assert str(past.id) in ids
        assert str(target.id) not in ids
        assert all(
            r.kickoff_utc < KICKOFF_BASE for r in hist
        ), "Future fixture leaked into training history"

    def test_same_kickoff_fixture_excluded(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Same Home")
        away = _team(session, "Same Away")
        third = _team(session, "Same Third")

        # Another fixture at the SAME kickoff time (common on matchdays)
        _fixture(
            session, comp, s, third, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=1,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=2, away_goals=0,
        )

        _, hist = extract_retrospective_features(session, target)
        # No same-kickoff result should appear (strict less-than, not <=)
        assert all(r.kickoff_utc < KICKOFF_BASE for r in hist)

    def test_unfinished_fixture_excluded(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Unfinished Home")
        away = _team(session, "Unfinished Away")

        # Scheduled (no goals) in the past
        _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=3),
            status=FixtureStatus.SCHEDULED,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=0,
        )

        _, hist = extract_retrospective_features(session, target)
        assert len(hist) == 0

    def test_non_finished_with_goals_excluded(self, session: Session) -> None:
        """A fixture with non-null goals but status != FINISHED must not enter history."""
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Status Home")
        away = _team(session, "Status Away")

        # Goals populated but fixture is only live — must be excluded
        _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=1),
            status=FixtureStatus.LIVE,
            home_goals=2,
            away_goals=1,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=0, away_goals=0,
        )

        _, hist = extract_retrospective_features(session, target)
        assert len(hist) == 0, "Non-FINISHED fixture with goals leaked into training history"

    def test_null_goals_fixture_excluded(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Null Home")
        away = _team(session, "Null Away")

        # Marked finished but goals not recorded
        _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=2),
            status=FixtureStatus.FINISHED,
            home_goals=None,
            away_goals=None,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=0, away_goals=2,
        )

        _, hist = extract_retrospective_features(session, target)
        assert len(hist) == 0

    def test_competition_isolation(self, session: Session) -> None:
        """Results from a different competition must not affect the target's features."""
        comp_a = _competition(session, "League A")
        comp_b = _competition(session, "League B")
        s_a = _season(session, comp_a)
        s_b = _season(session, comp_b)
        home = _team(session, "Comp Iso Home")
        away = _team(session, "Comp Iso Away")

        # Past result in League B
        _fixture(
            session, comp_b, s_b, home, away,
            KICKOFF_BASE - timedelta(days=7),
            home_goals=3, away_goals=0,
        )
        target = _fixture(
            session, comp_a, s_a, home, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=1,
        )

        _, hist = extract_retrospective_features(session, target)
        # League B result must not appear
        assert len(hist) == 0


class TestRetrospectiveHash:
    def test_hash_deterministic(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Hash Home")
        away = _team(session, "Hash Away")
        _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=7),
            home_goals=1, away_goals=0,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=2, away_goals=1,
        )
        _, hist1 = extract_retrospective_features(session, target)
        _, hist2 = extract_retrospective_features(session, target)
        assert retrospective_fixture_hash(hist1) == retrospective_fixture_hash(hist2)

    def test_changed_goals_changes_hash(self, session: Session) -> None:
        """Mutating canonical home_goals changes the content hash."""
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Mutable Home")
        away = _team(session, "Mutable Away")
        prior = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=7),
            home_goals=2, away_goals=0,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=1,
        )

        _, hist_before = extract_retrospective_features(session, target)
        hash_before = retrospective_fixture_hash(hist_before)

        # Mutate the mutable canonical row
        prior.home_goals = 0
        session.flush()

        _, hist_after = extract_retrospective_features(session, target)
        hash_after = retrospective_fixture_hash(hist_after)

        assert hash_before != hash_after

    def test_fixture_hash_includes_team_ids(self) -> None:
        """Changing team IDs in the result changes the fixture hash."""
        team_a = uuid.uuid4()
        team_b = uuid.uuid4()
        team_c = uuid.uuid4()
        r1 = RetrospectiveResult(
            fixture_id=uuid.uuid4(),
            home_team_id=team_a,
            away_team_id=team_b,
            kickoff_utc=KICKOFF_BASE,
            home_goals=1,
            away_goals=0,
        )
        r2 = RetrospectiveResult(
            fixture_id=r1.fixture_id,
            home_team_id=team_c,  # different team
            away_team_id=team_b,
            kickoff_utc=KICKOFF_BASE,
            home_goals=1,
            away_goals=0,
        )
        assert retrospective_fixture_hash([r1]) != retrospective_fixture_hash([r2])

    def test_hash_starts_with_sha256(self) -> None:
        results = [
            RetrospectiveResult(
                fixture_id=uuid.uuid4(),
                home_team_id=uuid.uuid4(),
                away_team_id=uuid.uuid4(),
                kickoff_utc=KICKOFF_BASE,
                home_goals=1,
                away_goals=0,
            )
        ]
        h = retrospective_fixture_hash(results)
        assert h.startswith("sha256:")

    def test_empty_results_produces_stable_hash(self) -> None:
        h1 = retrospective_fixture_hash([])
        h2 = retrospective_fixture_hash([])
        assert h1 == h2


class TestRetrospectiveDatasetHash:
    """Tests for the observation-level dataset hash (covers target fixtures)."""

    def _make_obs(self, idx: int, outcome: int = 1):
        from datetime import timedelta

        from qwantej.performance.calibration_backtest import CalibrationObservationRow

        base = KICKOFF_BASE + timedelta(days=idx)
        return CalibrationObservationRow(
            observation_id=f"obs-{idx:04d}",
            decision_as_of=base - timedelta(hours=2),
            feature_as_of=base - timedelta(hours=2),
            outcome_observed_at=base + timedelta(hours=2),
            model_version="m:1.0",
            raw_probability=0.6,
            outcome=outcome,
        )

    def test_hash_starts_with_sha256_prefix(self) -> None:
        h = retrospective_dataset_hash([self._make_obs(0)])
        assert h.startswith("sha256:")

    def test_full_digest_stored(self) -> None:
        h = retrospective_dataset_hash([self._make_obs(0)])
        # sha256: + 64 hex chars
        assert len(h) == len("sha256:") + 64

    def test_different_outcome_produces_different_hash(self) -> None:
        h_win = retrospective_dataset_hash([self._make_obs(0, outcome=1)])
        h_loss = retrospective_dataset_hash([self._make_obs(0, outcome=0)])
        assert h_win != h_loss

    def test_deterministic(self) -> None:
        obs = [self._make_obs(i) for i in range(5)]
        assert retrospective_dataset_hash(obs) == retrospective_dataset_hash(obs)

    def test_empty_list_stable(self) -> None:
        h1 = retrospective_dataset_hash([])
        h2 = retrospective_dataset_hash([])
        assert h1 == h2


class TestRetrospectiveFeatures:
    def test_historical_count_matches_qualified_fixtures(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Feature Home")
        away = _team(session, "Feature Away")

        for i in range(5):
            _fixture(
                session, comp, s, home, away,
                KICKOFF_BASE - timedelta(days=i + 1),
                home_goals=i % 3,
                away_goals=(i + 1) % 3,
            )

        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=1, away_goals=0,
        )

        features, hist = extract_retrospective_features(session, target)
        assert len(hist) == 5
        assert features.home_matches <= 5
        assert features.away_matches <= 5

    def test_features_have_positive_xg(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "XG Home")
        away = _team(session, "XG Away")

        _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE - timedelta(days=7),
            home_goals=2, away_goals=1,
        )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=0, away_goals=0,
        )

        features, _ = extract_retrospective_features(session, target)
        assert features.home_xg > 0
        assert features.away_xg > 0

    def test_target_fixture_excluded_from_its_own_history(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Self Home")
        away = _team(session, "Self Away")
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=2, away_goals=0,
        )

        _, hist = extract_retrospective_features(session, target)
        assert all(str(r.fixture_id) != str(target.id) for r in hist)

    def test_ordering_ascending_by_kickoff(self, session: Session) -> None:
        comp = _competition(session)
        s = _season(session, comp)
        home = _team(session, "Order Home")
        away = _team(session, "Order Away")

        for i in [3, 1, 5, 2, 4]:
            _fixture(
                session, comp, s, home, away,
                KICKOFF_BASE - timedelta(days=i),
                home_goals=1, away_goals=0,
            )
        target = _fixture(
            session, comp, s, home, away,
            KICKOFF_BASE,
            home_goals=0, away_goals=1,
        )

        _, hist = extract_retrospective_features(session, target)
        kickoffs = [r.kickoff_utc for r in hist]
        assert kickoffs == sorted(kickoffs)
