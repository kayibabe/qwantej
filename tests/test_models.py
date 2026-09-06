"""Structural tests for the Phase 1 canonical ORM models. Runs against an
in-memory SQLite engine — this checks constraints/relationships/typing, not
Postgres-specific behaviour (JSONB indexing, etc.), which is exercised
separately once a real Postgres instance is available (see
docs/DATA_DICTIONARY.md and the Alembic migration under
backend/models/migrations/).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    Competition,
    EntityType,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Provider,
    Season,
    SourceMapping,
    StatsSnapshot,
    StatsSubjectType,
    Team,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


@pytest.fixture()
def fixture(session: Session) -> Fixture:
    comp = Competition(name="Premier League", country="England", tier=1)
    season = Season(competition=comp, label="2025/2026")
    home = Team(name="Arsenal")
    away = Team(name="Chelsea")
    fx = Fixture(
        competition=comp,
        season=season,
        home_team=home,
        away_team=away,
        kickoff_utc=datetime.now(UTC),
        status=FixtureStatus.SCHEDULED,
    )
    session.add_all([comp, season, home, away, fx])
    session.flush()
    return fx


class TestFixture:
    def test_round_trips_status_as_lowercase_value(
        self, session: Session, fixture: Fixture
    ) -> None:
        session.commit()
        session.expire_all()
        reloaded = session.get(Fixture, fixture.id)
        assert reloaded is not None
        assert reloaded.status is FixtureStatus.SCHEDULED

    def test_rejects_fixture_against_itself(self, session: Session, fixture: Fixture) -> None:
        fixture.away_team_id = fixture.home_team_id
        with pytest.raises(IntegrityError):
            session.commit()


class TestSourceMapping:
    def test_maps_provider_entity_to_canonical_id(self, session: Session, fixture: Fixture) -> None:
        provider = Provider(name="API-Football", kind="fixtures")
        mapping = SourceMapping(
            provider=provider,
            entity_type=EntityType.FIXTURE,
            external_id="12345",
            canonical_id=fixture.id,
            confidence=0.98,
        )
        session.add_all([provider, mapping])
        session.commit()
        session.expire_all()

        reloaded = session.query(SourceMapping).one()
        assert reloaded.entity_type is EntityType.FIXTURE
        assert reloaded.canonical_id == fixture.id

    def test_rejects_duplicate_mapping_for_same_provider(
        self, session: Session, fixture: Fixture
    ) -> None:
        provider = Provider(name="API-Football", kind="fixtures")
        session.add(provider)
        session.flush()
        session.add(
            SourceMapping(
                provider=provider, entity_type=EntityType.FIXTURE,
                external_id="12345", canonical_id=fixture.id,
            )
        )
        session.commit()

        session.add(
            SourceMapping(
                provider=provider, entity_type=EntityType.FIXTURE,
                external_id="12345", canonical_id=fixture.id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


class TestOddsQuote:
    def test_stores_a_timestamped_quote(self, session: Session, fixture: Fixture) -> None:
        quote = OddsQuote(
            fixture=fixture, bookmaker="Pinnacle", market="1X2", selection="home",
            decimal_odds=2.10, captured_at=datetime.now(UTC), source="Pinnacle",
        )
        session.add(quote)
        session.commit()
        assert session.query(OddsQuote).count() == 1


class TestStatsSnapshot:
    def test_team_snapshot_requires_team_id_and_no_fixture_id(
        self, session: Session, fixture: Fixture
    ) -> None:
        snapshot = StatsSnapshot(
            subject_type=StatsSubjectType.TEAM,
            team_id=fixture.home_team_id,
            as_of_timestamp=datetime.now(UTC),
            payload={"xg_for_last5": 1.8},
            source="StatsBomb",
        )
        session.add(snapshot)
        session.commit()
        assert session.query(StatsSnapshot).count() == 1

    def test_rejects_team_snapshot_with_fixture_id_set(
        self, session: Session, fixture: Fixture
    ) -> None:
        snapshot = StatsSnapshot(
            subject_type=StatsSubjectType.TEAM,
            team_id=fixture.home_team_id,
            fixture_id=fixture.id,  # invalid: team-subject rows must not carry a fixture_id
            as_of_timestamp=datetime.now(UTC),
            payload={},
            source="StatsBomb",
        )
        session.add(snapshot)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_rejects_snapshot_with_neither_id_set(self, session: Session) -> None:
        snapshot = StatsSnapshot(
            subject_type=StatsSubjectType.TEAM,
            as_of_timestamp=datetime.now(UTC),
            payload={},
            source="StatsBomb",
        )
        session.add(snapshot)
        with pytest.raises(IntegrityError):
            session.commit()
