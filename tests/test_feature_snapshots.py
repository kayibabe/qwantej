"""Feature-store contract and point-in-time leakage regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Season,
    StatsSnapshot,
    StatsSubjectType,
    Team,
)
from backend.services.features import (
    FeatureSnapshotError,
    create_feature_snapshot,
    verify_feature_snapshot,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def _seed(session: Session):
    competition = Competition(name="Feature League")
    season = Season(competition=competition, label="2026")
    home, away, outsider = Team(name="Home"), Team(name="Away"), Team(name="Other")
    fixture = Fixture(
        competition=competition,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=NOW + timedelta(hours=3),
        status=FixtureStatus.SCHEDULED,
    )
    session.add_all([competition, season, home, away, outsider, fixture])
    session.flush()
    stats = StatsSnapshot(
        subject_type=StatsSubjectType.TEAM,
        team_id=home.id,
        as_of_timestamp=NOW - timedelta(hours=1),
        payload={"rolling_xg": 1.4},
        source="api-football",
    )
    odds = OddsQuote(
        fixture_id=fixture.id,
        bookmaker="Example",
        market="totals",
        selection="over",
        line=2.5,
        decimal_odds=2.1,
        captured_at=NOW,
        source="api-football",
    )
    session.add_all([stats, odds])
    session.flush()
    return fixture, outsider, stats, odds


def _create(session: Session, **overrides):
    fixture, outsider, stats, odds = _seed(session)
    kwargs = {
        "fixture_id": fixture.id,
        "feature_version": "baseline-v1",
        "as_of_timestamp": NOW,
        "features": {"home_rolling_xg": 1.4, "away_rolling_xg": None},
        "stats_snapshot_ids": [stats.id],
        "odds_quote_ids": [odds.id],
        "imputation_policy_version": "explicit-null-v1",
        "code_commit": "abc123",
    }
    kwargs.update(overrides)
    return create_feature_snapshot(session, **kwargs), (fixture, outsider, stats, odds)


def test_creates_content_addressed_point_in_time_snapshot(session: Session) -> None:
    snapshot, (_, _, stats, odds) = _create(session)
    assert snapshot.features == {
        "away_rolling_xg": None,
        "home_rolling_xg": 1.4,
    }
    assert snapshot.stats_snapshot_ids == [str(stats.id)]
    assert snapshot.odds_quote_ids == [str(odds.id)]
    assert snapshot.snapshot_ref == f"feature-snapshot:{snapshot.id}"
    assert snapshot.source_data_hash.startswith("sha256:")
    assert snapshot.feature_hash.startswith("sha256:")
    assert verify_feature_snapshot(session, snapshot)


def test_exact_retry_is_idempotent(session: Session) -> None:
    first, (_, _, stats, odds) = _create(session)
    second = create_feature_snapshot(
        session,
        fixture_id=first.fixture_id,
        feature_version=first.feature_version,
        as_of_timestamp=NOW,
        features={"away_rolling_xg": None, "home_rolling_xg": 1.4},
        stats_snapshot_ids=[stats.id],
        odds_quote_ids=[odds.id],
        imputation_policy_version=first.imputation_policy_version,
        code_commit=first.code_commit,
    )
    assert second.id == first.id
    assert session.query(type(first)).count() == 1


def test_future_source_snapshot_is_rejected(session: Session) -> None:
    fixture, _, stats, _ = _seed(session)
    stats.as_of_timestamp = NOW + timedelta(minutes=1)
    session.flush()
    with pytest.raises(FeatureSnapshotError, match="after as_of_timestamp"):
        create_feature_snapshot(
            session,
            fixture_id=fixture.id,
            feature_version="v1",
            as_of_timestamp=NOW,
            features={"x": 1.0},
            stats_snapshot_ids=[stats.id],
            imputation_policy_version="none-v1",
            code_commit="abc123",
        )


def test_nonparticipant_team_snapshot_is_rejected(session: Session) -> None:
    fixture, outsider, _, _ = _seed(session)
    stats = StatsSnapshot(
        subject_type=StatsSubjectType.TEAM,
        team_id=outsider.id,
        as_of_timestamp=NOW,
        payload={"xg": 2.0},
        source="api-football",
    )
    session.add(stats)
    session.flush()
    with pytest.raises(FeatureSnapshotError, match="does not belong"):
        create_feature_snapshot(
            session,
            fixture_id=fixture.id,
            feature_version="v1",
            as_of_timestamp=NOW,
            features={"x": 1.0},
            stats_snapshot_ids=[stats.id],
            imputation_policy_version="none-v1",
            code_commit="abc123",
        )


def test_decision_at_or_after_kickoff_is_rejected(session: Session) -> None:
    fixture, _, stats, _ = _seed(session)
    with pytest.raises(FeatureSnapshotError, match="before fixture kickoff"):
        create_feature_snapshot(
            session,
            fixture_id=fixture.id,
            feature_version="v1",
            as_of_timestamp=fixture.kickoff_utc,
            features={"x": 1.0},
            stats_snapshot_ids=[stats.id],
            imputation_policy_version="none-v1",
            code_commit="abc123",
        )


@pytest.mark.parametrize(
    "features,message",
    [({}, "non-empty"), ({"nested": {"x": 1}}, "scalar"), ({"bad": float("nan")}, "finite")],
)
def test_invalid_feature_vectors_are_rejected(
    session: Session, features: dict, message: str
) -> None:
    fixture, _, stats, _ = _seed(session)
    with pytest.raises(ValueError, match=message):
        create_feature_snapshot(
            session,
            fixture_id=fixture.id,
            feature_version="v1",
            as_of_timestamp=NOW,
            features=features,
            stats_snapshot_ids=[stats.id],
            imputation_policy_version="none-v1",
            code_commit="abc123",
        )


def test_source_free_snapshot_is_rejected(session: Session) -> None:
    fixture, _, _, _ = _seed(session)
    with pytest.raises(FeatureSnapshotError, match="at least one source"):
        create_feature_snapshot(
            session,
            fixture_id=fixture.id,
            feature_version="v1",
            as_of_timestamp=NOW,
            features={"x": 1.0},
            imputation_policy_version="none-v1",
            code_commit="abc123",
        )


def test_hash_verification_detects_tampering(session: Session) -> None:
    snapshot, _ = _create(session)
    snapshot.features = {"home_rolling_xg": 9.9}
    assert not verify_feature_snapshot(session, snapshot)
