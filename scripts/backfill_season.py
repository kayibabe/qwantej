"""Historical season backfill from API-Football.

Iterates through a date range in configurable chunks, ingesting fixture
results and odds into the local database. Fixtures already in the database
are left intact (idempotent). Use this to seed the database before running
``scripts/run_walk_forward.py --skip-ingest``.

Each chunk's ``captured_at`` is set to midnight UTC on the day *after* the
chunk's end date (i.e. ``chunk_end + 1 day, 00:00 UTC``), NOT the
wall-clock time of the API call. Choosing the next-day midnight guarantees
that even fixtures which kicked off late on the chunk's last day (e.g.
23:45 UTC) receive a snapshot whose ``as_of_timestamp`` is strictly after
their kickoff — the constraint that ``fixture_result_observed_after_kickoff``
requires.  Re-runs are idempotent: the same chunk always produces the same
timestamp, so ``_append_stats_snapshot`` deduplicates identical rows.

The timestamps are still NOT the original pre-kickoff capture times, so
use ``--calibration-only`` in ``run_walk_forward.py`` when using backfilled
odds; a full walk-forward requires live snapshots ingested by
``ingestion_worker`` before each match kicks off.

Usage:
    python scripts/backfill_season.py \\
        [--league 39] [--season 2024] \\
        [--from 2024-08-01] [--to 2025-05-31] \\
        [--chunk-days 30] \\
        [--no-odds] [--with-statistics] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill")


@dataclass
class BackfillSummary:
    fixtures_created: int = 0
    fixtures_updated: int = 0
    fixture_snapshots_created: int = 0
    odds_quotes_created: int = 0
    odds_quotes_deduplicated: int = 0
    chunks_processed: int = 0


def season_date_range(season: int) -> tuple[date, date]:
    """Default date range for a season: Aug 1st of *season* to Jun 30th of *season+1*."""
    return date(season, 8, 1), date(season + 1, 6, 30)


def date_chunks(from_date: date, to_date: date, chunk_days: int) -> list[tuple[date, date]]:
    """Split [from_date, to_date] into non-overlapping windows of at most chunk_days."""
    if chunk_days <= 0:
        raise ValueError(f"chunk_days must be >= 1, got {chunk_days}")
    chunks: list[tuple[date, date]] = []
    cursor = from_date
    while cursor <= to_date:
        end = min(cursor + timedelta(days=chunk_days - 1), to_date)
        chunks.append((cursor, end))
        cursor = end + timedelta(days=1)
    return chunks


def backfill_season(
    client: Any,
    session: Any,
    *,
    league_id: int,
    season: int,
    from_date: date,
    to_date: date,
    chunk_days: int = 30,
    include_odds: bool = True,
    include_fixture_statistics: bool = False,
) -> BackfillSummary:
    """Backfill a full season by iterating through the date range in chunks.

    Does NOT commit — the caller controls transaction boundaries.  In normal
    (non-dry-run) use, call this inside a ``session_scope`` so each successful
    chunk is committed when the context exits.  For a dry-run, roll back after.

    The function is pure enough to be called from tests: inject a mock client
    and an in-memory session.
    """
    from backend.services.api_football_ingestion import ingest_walk_forward_window

    chunks = date_chunks(from_date, to_date, chunk_days)
    total = BackfillSummary()

    log.info(
        "Backfill: league=%d season=%d from=%s to=%s chunk_days=%d (%d chunk(s))",
        league_id, season, from_date, to_date, chunk_days, len(chunks),
    )

    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        # Deterministic timestamp: midnight UTC on the day after chunk_end.
        # Choosing next-day midnight ensures the snapshot's as_of_timestamp
        # is strictly after every fixture's kickoff in the chunk — including
        # late-evening kickoffs on the final day — satisfying the constraint
        # that fixture_result_observed_after_kickoff requires.
        captured_at = datetime.combine(
            chunk_end + timedelta(days=1), dt_time(0, 0), tzinfo=UTC
        )
        log.info("  chunk %d/%d: %s → %s", i, len(chunks), chunk_start, chunk_end)
        summary = ingest_walk_forward_window(
            session,
            client,
            league_id=league_id,
            season=season,
            start_date=chunk_start,
            end_date=chunk_end,
            captured_at=captured_at,
            include_odds=include_odds,
            include_fixture_statistics=include_fixture_statistics,
        )
        total.fixtures_created += summary.fixtures_created
        total.fixtures_updated += summary.fixtures_updated
        total.fixture_snapshots_created += summary.fixture_snapshots_created
        total.odds_quotes_created += summary.odds_quotes_created
        total.odds_quotes_deduplicated += summary.odds_quotes_deduplicated
        total.chunks_processed += 1
        log.info(
            "    fixtures +%d/~%d  snapshots=%d  odds +%d (dedup=%d)",
            summary.fixtures_created,
            summary.fixtures_updated,
            summary.fixture_snapshots_created,
            summary.odds_quotes_created,
            summary.odds_quotes_deduplicated,
        )

    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--league", type=int, default=39, metavar="ID",
        help="API-Football league ID (default: 39 = Premier League)",
    )
    parser.add_argument(
        "--season", type=int, default=date.today().year - 1, metavar="YEAR",
        help="Season start year (default: current year - 1)",
    )
    parser.add_argument(
        "--from", dest="from_date", type=date.fromisoformat, metavar="YYYY-MM-DD",
        help="Start date (default: August 1st of --season)",
    )
    parser.add_argument(
        "--to", dest="to_date", type=date.fromisoformat, metavar="YYYY-MM-DD",
        help="End date (default: June 30th of --season + 1)",
    )
    parser.add_argument(
        "--chunk-days", type=int, default=30, metavar="N",
        help="Days per ingestion chunk (default: 30)",
    )
    parser.add_argument(
        "--no-odds", action="store_true",
        help="Skip odds ingestion (faster; use with --calibration-only in run_walk_forward.py)",
    )
    parser.add_argument(
        "--with-statistics", action="store_true",
        help="Include fixture statistics (xG etc.) where available",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Roll back after ingestion — no rows persisted",
    )
    return parser.parse_args()


class _DryRun(Exception):
    """Raised inside session_scope to trigger its rollback path during --dry-run."""


def main() -> None:
    args = parse_args()

    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.services.api_football_client import ApiFootballClient

    settings = get_settings()

    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL must point at Postgres — update your .env file")
        sys.exit(1)

    if not settings.api_football_key:
        log.error("API_FOOTBALL_KEY is not set in .env")
        sys.exit(1)

    from_date = args.from_date
    to_date = args.to_date
    if from_date is None or to_date is None:
        default_from, default_to = season_date_range(args.season)
        from_date = from_date if from_date is not None else default_from
        to_date = to_date if to_date is not None else default_to

    if args.no_odds:
        log.info("Odds ingestion disabled (--no-odds)")
    else:
        log.warning(
            "Odds captured_at will be midnight UTC on the day after each chunk's end "
            "date, NOT the original pre-kickoff timestamp. Use --calibration-only in "
            "run_walk_forward.py with this data, or add --no-odds to skip odds."
        )

    client = ApiFootballClient(
        api_key=settings.api_football_key,
        base_url=settings.api_football_base_url,
        timeout_seconds=settings.api_football_timeout_seconds,
    )
    engine = make_engine(settings.database_url)

    summary: BackfillSummary | None = None
    try:
        with session_scope(engine) as session:
            summary = backfill_season(
                client,
                session,
                league_id=args.league,
                season=args.season,
                from_date=from_date,
                to_date=to_date,
                chunk_days=args.chunk_days,
                include_odds=not args.no_odds,
                include_fixture_statistics=args.with_statistics,
            )
            if args.dry_run:
                # Raise inside session_scope so its except-branch calls rollback.
                raise _DryRun()
            log.info(
                "Backfill complete: %d chunk(s) | fixtures +%d/~%d | "
                "snapshots=%d | odds +%d",
                summary.chunks_processed,
                summary.fixtures_created,
                summary.fixtures_updated,
                summary.fixture_snapshots_created,
                summary.odds_quotes_created,
            )
    except _DryRun:
        log.info("Dry-run: no rows committed")


if __name__ == "__main__":
    main()
