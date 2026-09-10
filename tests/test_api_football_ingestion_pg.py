"""Postgres integration tests for the API-Football ingestion layer.

Three concerns that SQLite cannot exercise:

1. JSONB round-trip — StatsSnapshot.payload is stored as JSONB in Postgres.
   The deduplication guard in _append_stats_snapshot compares the Python dict
   read back from the DB to the incoming payload. If Postgres reorders JSONB
   keys the comparison fails falsely; these tests confirm it does not.

2. NUMERIC precision — OddsQuote.decimal_odds and line are NUMERIC columns.
   The tests confirm Decimal values survive a DB round-trip without float drift,
   and that the SQL deduplication query matches on exact Decimal equality.

3. Conflicting-payload guard — two different payloads sharing the same
   (fixture_id, as_of_timestamp, source) must raise ApiFootballIngestionError,
   which requires a real DB to verify the uniqueness lookup.

All tests run inside a rolled-back transaction so no rows persist.
Skipped automatically when Postgres is unreachable or not migrated.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import EntityType, Fixture, OddsQuote, Provider, SourceMapping, StatsSnapshot
from backend.services.api_football_ingestion import (
    ApiFootballIngestionError,
    ingest_fixture_statistics,
    ingest_fixtures,
    ingest_odds,
)

DATABASE_URL = get_settings().database_url

# Must match the provider name written by the ingestion service.
_PROVIDER_NAME = "API-Football"

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


def _fixture_payload(*, fixture_id: int, status: str = "NS") -> dict:
    return {
        "fixture": {
            "id": fixture_id,
            "timestamp": int(KICKOFF.timestamp()),
            "date": KICKOFF.isoformat(),
            "status": {"short": status},
            "venue": {"name": "Postgres Stadium"},
        },
        "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026},
        "teams": {
            "home": {"id": 10, "name": "Home FC"},
            "away": {"id": 20, "name": "Away FC"},
        },
        "goals": {"home": None, "away": None},
    }


def _odds_payload(*, fixture_id: int) -> dict:
    return {
        "fixture": {"id": fixture_id},
        "update": "2026-09-06T12:30:00+00:00",
        "bookmakers": [
            {
                "id": 1,
                "name": "Bet Example",
                "bets": [
                    {
                        "id": 5,
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "1.850"},
                            {"value": "Under 2.5", "odd": "2.100"},
                        ],
                    }
                ],
            }
        ],
    }


def _fixture_uuid(session: Session, external_id: str) -> object:
    """Return the canonical UUID for the given external fixture ID.

    Scoped to the API-Football provider so a mapping written by a different
    provider for the same numeric ID cannot shadow the row created in the
    current test transaction.  The mapping itself is written by ingest_fixtures
    inside the same rolled-back connection, so it is visible to this query but
    vanishes at teardown.
    """
    provider_id_sq = (
        select(Provider.id).where(Provider.name == _PROVIDER_NAME).scalar_subquery()
    )
    mapping = session.scalar(
        select(SourceMapping).where(
            SourceMapping.entity_type == EntityType.FIXTURE,
            SourceMapping.external_id == external_id,
            SourceMapping.provider_id == provider_id_sq,
        )
    )
    assert mapping is not None, (
        f"SourceMapping for fixture {external_id!r} (provider={_PROVIDER_NAME!r}) not found; "
        "did ingest_fixtures run in this session?"
    )
    return mapping.canonical_id


@pytest.fixture(scope="module")
def engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("API-Football Postgres integration tests require a PostgreSQL database")
    eng = create_engine(DATABASE_URL)
    try:
        with eng.connect() as conn:
            present = conn.execute(
                text("select count(*) from information_schema.tables "
                     "where table_name = 'source_mappings'")
            ).scalar_one()
    except OperationalError:
        pytest.skip("Postgres not reachable (docker compose up -d db or CI service not ready)")
    if not present:
        pytest.skip("source_mappings table absent; run: alembic upgrade head")
    return eng


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    outer = conn.begin()
    sess = Session(bind=conn)
    try:
        yield sess
    finally:
        sess.close()
        outer.rollback()
        conn.close()


@pytest.fixture()
def ext_id(request: pytest.FixtureRequest) -> int:
    """Deterministic external fixture ID stable across runs.

    Derived from a SHA-256 of the pytest node ID (which includes the module
    path, class name, and method name) truncated into [10_000_000, 99_999_999]
    — a range real API-Football IDs have never reached.  Using SHA-256 rather
    than Python's built-in hash() keeps the value stable across interpreter
    restarts and processes, so a failing run always names the same ID and can
    be reproduced without capturing run-time state.
    """
    digest = int(hashlib.sha256(request.node.nodeid.encode()).hexdigest(), 16)
    return 10_000_000 + (digest % 90_000_000)


class TestJsonbRoundTrip:
    def test_stats_snapshot_payload_survives_jsonb_round_trip(
        self, session: Session, ext_id: int
    ) -> None:
        """JSONB stores payload as binary; the dict read back must equal the dict written."""
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        fid = _fixture_uuid(session, str(ext_id))
        snapshot = session.scalar(select(StatsSnapshot).where(StatsSnapshot.fixture_id == fid))
        assert snapshot is not None
        expected = {"endpoint": "fixtures", "record": _fixture_payload(fixture_id=ext_id)}
        assert snapshot.payload == expected

    def test_duplicate_fixture_ingestion_is_idempotent_under_jsonb(
        self, session: Session, ext_id: int
    ) -> None:
        """The second ingest must see the JSONB payload as equal and skip the snapshot."""
        first = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        second = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert first.fixtures_created == 1, "fixture already existed — ext_id collision"
        assert first.fixture_snapshots_created == 1
        assert second.fixture_snapshots_created == 0
        fid = _fixture_uuid(session, str(ext_id))
        assert (
            session.query(StatsSnapshot).filter(StatsSnapshot.fixture_id == fid).count() == 1
        )

    def test_conflicting_payload_at_same_timestamp_raises(
        self, session: Session, ext_id: int
    ) -> None:
        """Two different payloads for the same (fixture, timestamp, source) must be rejected."""
        ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        altered = _fixture_payload(fixture_id=ext_id)
        altered["fixture"]["venue"] = {"name": "Different Stadium"}
        with pytest.raises(ApiFootballIngestionError, match="conflicting provider payloads"):
            ingest_fixture_statistics(
                session,
                external_fixture_id=str(ext_id),
                statistics=({"team": {"id": 10}, "statistics": [{"type": "Shots", "value": 5}]},),
                captured_at=NOW,
            )
            # Manufacture the conflict by directly re-ingesting with a mutated payload
            ingest_fixtures(session, [altered], captured_at=NOW)


class TestNumericPrecision:
    def test_decimal_odds_survive_round_trip_without_float_drift(
        self, session: Session, ext_id: int
    ) -> None:
        """NUMERIC(8,3) must return the exact Decimal written, not a float approximation."""
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        ingest_odds(session, [_odds_payload(fixture_id=ext_id)])
        fid = _fixture_uuid(session, str(ext_id))
        quotes = list(
            session.scalars(
                select(OddsQuote)
                .where(OddsQuote.fixture_id == fid)
                .order_by(OddsQuote.decimal_odds)
            )
        )
        assert len(quotes) == 2
        assert quotes[0].decimal_odds == Decimal("1.850")
        assert quotes[1].decimal_odds == Decimal("2.100")
        assert isinstance(quotes[0].decimal_odds, Decimal)

    def test_line_survives_round_trip(self, session: Session, ext_id: int) -> None:
        """NUMERIC(6,2) line column must return exact Decimal, not float."""
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        ingest_odds(session, [_odds_payload(fixture_id=ext_id)])
        fid = _fixture_uuid(session, str(ext_id))
        quotes = list(session.scalars(select(OddsQuote).where(OddsQuote.fixture_id == fid)))
        assert all(q.line == Decimal("2.5") for q in quotes)
        assert all(isinstance(q.line, Decimal) for q in quotes)

    def test_odds_deduplication_matches_on_exact_decimal(
        self, session: Session, ext_id: int
    ) -> None:
        """The SQL deduplication query must find an exact Decimal match, not a float near-miss."""
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        first = ingest_odds(session, [_odds_payload(fixture_id=ext_id)])
        second = ingest_odds(session, [_odds_payload(fixture_id=ext_id)])
        assert first.odds_quotes_created == 2
        assert second.odds_quotes_created == 0
        assert second.odds_quotes_deduplicated == 2


class TestTimezoneHandling:
    def test_kickoff_utc_is_returned_tz_aware(self, session: Session, ext_id: int) -> None:
        """Fixture.kickoff_utc must be tz-aware after a Postgres round-trip."""
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        fid = _fixture_uuid(session, str(ext_id))
        fixture = session.scalar(select(Fixture).where(Fixture.id == fid))
        assert fixture is not None
        assert fixture.kickoff_utc.tzinfo is not None
        assert fixture.kickoff_utc.astimezone(UTC) == KICKOFF

    def test_stats_snapshot_as_of_timestamp_is_tz_aware(
        self, session: Session, ext_id: int
    ) -> None:
        result = ingest_fixtures(session, [_fixture_payload(fixture_id=ext_id)], captured_at=NOW)
        assert result.fixtures_created == 1, "fixture already existed — ext_id collision"
        fid = _fixture_uuid(session, str(ext_id))
        snapshot = session.scalar(select(StatsSnapshot).where(StatsSnapshot.fixture_id == fid))
        assert snapshot is not None
        assert snapshot.as_of_timestamp.tzinfo is not None
        assert snapshot.as_of_timestamp.astimezone(UTC) == NOW
