"""Live smoke test for the API-Football ingestion pipeline.

Fetches one week of Premier League fixtures (and optionally odds) using
your real API key, ingests them into the dev Postgres DB, and prints a
summary. Commits on success so you can inspect the rows; rolls back on
any error so partial state never persists.

Usage:
    python scripts/smoke_api_football.py [--league LEAGUE_ID] [--season YEAR]
        [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--with-odds] [--dry-run]

Defaults: Premier League (39), current calendar year, past 7 days.
--dry-run rolls back the transaction instead of committing (safe to run repeatedly).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from backend.core.config import get_settings
from backend.core.db import make_engine, session_scope
from backend.services.api_football_client import ApiFootballClient
from backend.services.api_football_ingestion import ingest_walk_forward_window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke")


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--league", type=int, default=39, metavar="ID",
                        help="API-Football league id (default: 39 = Premier League)")
    parser.add_argument("--season", type=int, default=today.year,
                        metavar="YEAR", help="Season year (default: current year)")
    parser.add_argument("--from", dest="start", type=date.fromisoformat,
                        default=today - timedelta(days=7), metavar="YYYY-MM-DD")
    parser.add_argument("--to", dest="end", type=date.fromisoformat,
                        default=today, metavar="YYYY-MM-DD")
    parser.add_argument("--with-odds", action="store_true",
                        help="Also fetch pre-match odds (uses extra quota)")
    parser.add_argument("--with-statistics", action="store_true",
                        help="Also fetch fixture statistics (one request per fixture)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Roll back after ingestion — nothing is persisted")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    if not settings.api_football_key.strip():
        log.error("API_FOOTBALL_KEY is not set — add it to your .env file")
        sys.exit(1)

    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL does not point at Postgres — update your .env file")
        sys.exit(1)

    log.info("League %d  Season %d  %s → %s", args.league, args.season, args.start, args.end)
    log.info("Odds: %s  Statistics: %s  Dry-run: %s",
             args.with_odds, args.with_statistics, args.dry_run)

    client = ApiFootballClient.from_settings(settings)
    engine = make_engine(settings.database_url)

    captured_at = datetime.now(UTC)

    with session_scope(engine) as session:
        try:
            summary = ingest_walk_forward_window(
                session,
                client,
                league_id=args.league,
                season=args.season,
                start_date=args.start,
                end_date=args.end,
                captured_at=captured_at,
                include_fixture_statistics=args.with_statistics,
            )

            if args.with_odds:
                from backend.services.api_football_ingestion import ingest_odds  # noqa: PLC0415
                odds_payloads = client.odds(league=args.league, season=args.season)
                from backend.services.api_football_ingestion import IngestionSummary  # noqa: PLC0415
                odds_summary = ingest_odds(session, odds_payloads)
                summary = IngestionSummary(
                    fixtures_created=summary.fixtures_created,
                    fixtures_updated=summary.fixtures_updated,
                    fixture_snapshots_created=summary.fixture_snapshots_created,
                    statistics_snapshots_created=summary.statistics_snapshots_created,
                    odds_quotes_created=odds_summary.odds_quotes_created,
                    odds_quotes_deduplicated=odds_summary.odds_quotes_deduplicated,
                    odds_quotes_unsupported=odds_summary.odds_quotes_unsupported,
                )

            log.info("--- Ingestion summary ---")
            log.info("  fixtures created:              %d", summary.fixtures_created)
            log.info("  fixtures updated:              %d", summary.fixtures_updated)
            log.info("  fixture snapshots:             %d", summary.fixture_snapshots_created)
            log.info("  statistics snapshots:          %d", summary.statistics_snapshots_created)
            log.info("  odds quotes created:           %d", summary.odds_quotes_created)
            log.info("  odds quotes deduplicated:      %d", summary.odds_quotes_deduplicated)
            log.info("  odds quotes unsupported:       %d", summary.odds_quotes_unsupported)

            # Spot-check: confirm rows are actually in the DB within this transaction
            fixture_count = session.execute(text("SELECT COUNT(*) FROM fixtures")).scalar_one()
            odds_count = session.execute(text("SELECT COUNT(*) FROM odds_quotes")).scalar_one()
            stats_count = session.execute(text("SELECT COUNT(*) FROM stats_snapshots")).scalar_one()
            log.info("--- DB row counts (this transaction) ---")
            log.info("  fixtures total:      %d", fixture_count)
            log.info("  odds_quotes total:   %d", odds_count)
            log.info("  stats_snapshots total: %d", stats_count)

            if args.dry_run:
                log.info("Dry-run: rolling back — no rows persisted")
                session.rollback()
            else:
                log.info("Committing %d fixture(s) to %s", fixture_count, settings.database_url)

        except Exception:
            log.exception("Ingestion failed — rolling back")
            sys.exit(1)

    log.info("Smoke test complete.")


if __name__ == "__main__":
    main()
