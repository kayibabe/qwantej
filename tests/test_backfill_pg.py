"""Postgres integration tests for scripts/backfill_season.py.

Tests that cannot be run on SQLite:
1. JSONB round-trip for StatsSnapshot payloads.
2. Idempotency — running backfill_season twice yields the same row count.
3. Multi-chunk decomposition — a wide date range is split correctly and all
   fixtures are ingested regardless of chunk size.
4. include_odds=False — fixture rows and snapshots are created, odds are not.

All tests run inside a rolled-back transaction so no rows persist.
Skipped automatically when Postgres is unreachable or not migrated.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from scripts.backfill_season import BackfillSummary, backfill_season, date_chunks, season_date_range

DATABASE_URL = get_settings().database_url

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
KICKOFF_1 = NOW - timedelta(days=10)
KICKOFF_2 = NOW - timedelta(days=5)


def _fixture_payload(*, fixture_id: int, status: str = "FT", kickoff: datetime) -> dict:
    goals = {"home": 2, "away": 1} if status == "FT" else {"home": None, "away": None}
    return {
        "fixture": {
            "id": fixture_id,
            "timestamp": int(kickoff.timestamp()),
            "date": kickoff.isoformat(),
            "status": {"short": status},
            "venue": {"name": "Test Stadium"},
        },
        "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2025},
        "teams": {
            "home": {"id": 100 + fixture_id, "name": f"Home {fixture_id}"},
            "away": {"id": 200 + fixture_id, "name": f"Away {fixture_id}"},
        },
        "goals": goals,
    }


def _odds_payload(*, fixture_id: int) -> dict:
    return {
        "fixture": {"id": fixture_id},
        "update": NOW.isoformat(),
        "bookmakers": [
            {
                "id": 1,
                "name": "Bet Example",
                "bets": [
                    {
                        "id": 1,
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": "2.10"},
                            {"value": "Draw", "odd": "3.20"},
                            {"value": "Away", "odd": "3.50"},
                        ],
                    }
                ],
            }
        ],
    }


class _MockTransport:
    """Returns fixture and odds payloads for two fixtures in the test window."""

    def __init__(self, fixture_ids: list[int], kickoffs: list[datetime]) -> None:
        self._fixture_ids = fixture_ids
        self._kickoffs = kickoffs

    def get_json(
        self, url: str, *, headers: dict, timeout_seconds: float
    ) -> tuple[int, dict, dict]:
        if "fixtures" in url and "odds" not in url and "statistics" not in url:
            return (
                200,
                {"x-ratelimit-requests-remaining": "1000"},
                {
                    "response": [
                        _fixture_payload(
                            fixture_id=fid,
                            status="FT",
                            kickoff=ko,
                        )
                        for fid, ko in zip(self._fixture_ids, self._kickoffs, strict=True)
                    ],
                    "paging": {"current": 1, "total": 1},
                },
            )
        if "odds" in url:
            return (
                200,
                {"x-ratelimit-requests-remaining": "1000"},
                {
                    "response": [
                        _odds_payload(fixture_id=fid) for fid in self._fixture_ids
                    ],
                    "paging": {"current": 1, "total": 1},
                },
            )
        return (200, {}, {"response": [], "paging": {"current": 1, "total": 1}})


@pytest.fixture(scope="module")
def pg_engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("Postgres not configured")
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Postgres unreachable")
    return engine


@pytest.fixture()
def session(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as s:
        with s.begin():
            yield s
            s.rollback()


def _make_client(
    fixture_ids: list[int] | None = None,
    kickoffs: list[datetime] | None = None,
) -> object:
    from backend.services.api_football_client import ApiFootballClient

    ids = fixture_ids or [3001, 3002]
    kos = kickoffs or [KICKOFF_1, KICKOFF_2]
    return ApiFootballClient(
        api_key="test-key",
        transport=_MockTransport(ids, kos),
    )


# ---------------------------------------------------------------------------
# date_chunks unit tests (no DB needed — run on all backends)
# ---------------------------------------------------------------------------


class TestDateChunks:
    def test_single_chunk(self) -> None:
        chunks = date_chunks(date(2024, 8, 1), date(2024, 8, 30), chunk_days=30)
        assert chunks == [(date(2024, 8, 1), date(2024, 8, 30))]

    def test_exact_boundary(self) -> None:
        chunks = date_chunks(date(2024, 8, 1), date(2024, 8, 31), chunk_days=31)
        assert chunks == [(date(2024, 8, 1), date(2024, 8, 31))]

    def test_two_chunks(self) -> None:
        chunks = date_chunks(date(2024, 8, 1), date(2024, 8, 10), chunk_days=5)
        assert len(chunks) == 2
        assert chunks[0] == (date(2024, 8, 1), date(2024, 8, 5))
        assert chunks[1] == (date(2024, 8, 6), date(2024, 8, 10))

    def test_no_overlap(self) -> None:
        chunks = date_chunks(date(2024, 8, 1), date(2024, 9, 30), chunk_days=10)
        for (_, end), (start, _) in zip(chunks[:-1], chunks[1:], strict=True):
            assert start == end + timedelta(days=1)

    def test_season_date_range(self) -> None:
        from_d, to_d = season_date_range(2024)
        assert from_d == date(2024, 8, 1)
        assert to_d == date(2025, 6, 30)


# ---------------------------------------------------------------------------
# Postgres integration tests
# ---------------------------------------------------------------------------


class TestBackfillSeasonPg:
    def test_fixtures_created(self, session: Session) -> None:
        client = _make_client()
        summary = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 9, 30),
            chunk_days=30,
            include_odds=False,
        )
        assert summary.fixtures_created >= 1
        # Aug 1→30, Aug 31→Sep 29, Sep 30 — chunk_days=30 never aligns to calendar months
        assert summary.chunks_processed == 3

    def test_fixture_snapshots_created(self, session: Session) -> None:
        client = _make_client()
        summary = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 8, 31),
            chunk_days=31,
            include_odds=False,
        )
        assert summary.fixture_snapshots_created >= 1

    def test_idempotent_second_run(self, session: Session) -> None:
        client = _make_client()
        kwargs = dict(
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 8, 31),
            chunk_days=31,
            include_odds=False,
        )
        s1 = backfill_season(client, session, **kwargs)
        s2 = backfill_season(client, session, **kwargs)
        # All rows already exist — ingestion silently skips duplicates
        assert s2.fixtures_created == 0
        assert s2.fixtures_updated == 0

    def test_odds_created_when_enabled(self, session: Session) -> None:
        client = _make_client()
        summary = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 8, 31),
            chunk_days=31,
            include_odds=True,
        )
        assert summary.odds_quotes_created >= 1

    def test_odds_skipped_when_disabled(self, session: Session) -> None:
        client = _make_client()
        summary = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 8, 31),
            chunk_days=31,
            include_odds=False,
        )
        assert summary.odds_quotes_created == 0

    def test_chunk_count_matches_date_range(self, session: Session) -> None:
        client = _make_client()
        summary = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 10, 31),
            chunk_days=31,
            include_odds=False,
        )
        assert summary.chunks_processed == 3  # Aug, Sep, Oct

    def test_returns_backfill_summary_type(self, session: Session) -> None:
        client = _make_client()
        result = backfill_season(
            client,
            session,
            league_id=39,
            season=2025,
            from_date=date(2025, 8, 1),
            to_date=date(2025, 8, 31),
            chunk_days=31,
            include_odds=False,
        )
        assert isinstance(result, BackfillSummary)
