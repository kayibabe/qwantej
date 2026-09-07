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

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import Fixture, OddsQuote, StatsSnapshot
from backend.services.api_football_ingestion import (
    ApiFootballIngestionError,
    ingest_fixture_statistics,
    ingest_fixtures,
    ingest_odds,
)

DATABASE_URL = get_settings().database_url

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


def _fixture_payload(*, fixture_id: int = 2001, status: str = "NS") -> dict:
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


def _odds_payload(*, fixture_id: int = 2001) -> dict:
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


class TestJsonbRoundTrip:
    def test_stats_snapshot_payload_survives_jsonb_round_trip(self, session: Session) -> None:
        """JSONB stores payload as binary; the dict read back must equal the dict written."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        snapshot = session.scalar(select(StatsSnapshot))
        assert snapshot is not None
        expected = {"endpoint": "fixtures", "record": _fixture_payload()}
        assert snapshot.payload == expected

    def test_duplicate_fixture_ingestion_is_idempotent_under_jsonb(
        self, session: Session
    ) -> None:
        """The second ingest must see the JSONB payload as equal and skip the snapshot."""
        first = ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        second = ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        assert first.fixture_snapshots_created == 1
        assert second.fixture_snapshots_created == 0
        assert session.query(StatsSnapshot).count() == 1

    def test_conflicting_payload_at_same_timestamp_raises(self, session: Session) -> None:
        """Two different payloads for the same (fixture, timestamp, source) must be rejected."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        altered = _fixture_payload()
        altered["fixture"]["venue"] = {"name": "Different Stadium"}
        with pytest.raises(ApiFootballIngestionError, match="conflicting provider payloads"):
            ingest_fixture_statistics(
                session,
                external_fixture_id="2001",
                statistics=({"team": {"id": 10}, "statistics": [{"type": "Shots", "value": 5}]},),
                captured_at=NOW,
            )
            # Manufacture the conflict by directly re-ingesting with a mutated payload
            ingest_fixtures(session, [altered], captured_at=NOW)


class TestNumericPrecision:
    def test_decimal_odds_survive_round_trip_without_float_drift(
        self, session: Session
    ) -> None:
        """NUMERIC(8,3) must return the exact Decimal written, not a float approximation."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        ingest_odds(session, [_odds_payload()])
        quotes = list(session.scalars(select(OddsQuote).order_by(OddsQuote.decimal_odds)))
        assert len(quotes) == 2
        assert quotes[0].decimal_odds == Decimal("1.850")
        assert quotes[1].decimal_odds == Decimal("2.100")
        assert isinstance(quotes[0].decimal_odds, Decimal)

    def test_line_survives_round_trip(self, session: Session) -> None:
        """NUMERIC(6,2) line column must return exact Decimal, not float."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        ingest_odds(session, [_odds_payload()])
        quotes = list(session.scalars(select(OddsQuote)))
        assert all(q.line == Decimal("2.5") for q in quotes)
        assert all(isinstance(q.line, Decimal) for q in quotes)

    def test_odds_deduplication_matches_on_exact_decimal(self, session: Session) -> None:
        """The SQL deduplication query must find an exact Decimal match, not a float near-miss."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        first = ingest_odds(session, [_odds_payload()])
        second = ingest_odds(session, [_odds_payload()])
        assert first.odds_quotes_created == 2
        assert second.odds_quotes_created == 0
        assert second.odds_quotes_deduplicated == 2


class TestTimezoneHandling:
    def test_kickoff_utc_is_returned_tz_aware(self, session: Session) -> None:
        """Fixture.kickoff_utc must be tz-aware after a Postgres round-trip."""
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        fixture = session.scalar(select(Fixture))
        assert fixture is not None
        assert fixture.kickoff_utc.tzinfo is not None
        assert fixture.kickoff_utc.astimezone(UTC) == KICKOFF

    def test_stats_snapshot_as_of_timestamp_is_tz_aware(self, session: Session) -> None:
        ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
        snapshot = session.scalar(select(StatsSnapshot))
        assert snapshot is not None
        assert snapshot.as_of_timestamp.tzinfo is not None
        assert snapshot.as_of_timestamp.astimezone(UTC) == NOW
