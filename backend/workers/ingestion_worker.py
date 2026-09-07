"""Scheduled API-Football ingestion worker.

Runs one ingestion loop iteration: fetches fixtures and optionally odds for
a configured set of leagues/seasons, commits each league-season window
independently so a partial failure does not roll back earlier successes.

Usage (one-shot):
    python -m backend.workers.ingestion_worker

Usage (continuous, every N seconds):
    python -m backend.workers.ingestion_worker --loop --interval 3600
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Sentinel for leagues param when unset
_DEFAULT_LEAGUES = [(39, 2026)]  # Premier League 2026 season


@dataclass
class WorkerConfig:
    """What to fetch on each scheduled run."""

    leagues: list[tuple[int, int]] = field(default_factory=lambda: list(_DEFAULT_LEAGUES))
    lookback_days: int = 7
    lookahead_days: int = 7
    include_odds: bool = True
    include_statistics: bool = False
    interval_seconds: int = 3600  # for --loop mode


@dataclass
class RunSummary:
    """Aggregated results across all league-season windows."""

    fixtures_created: int = 0
    fixtures_updated: int = 0
    odds_quotes_created: int = 0
    errors: int = 0


def run_once(config: WorkerConfig | None = None) -> RunSummary:
    """Execute one scheduled ingestion pass.  Returns an aggregated summary."""
    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.core.logging import configure_logging
    from backend.services.api_football_client import ApiFootballClient
    from backend.services.api_football_ingestion import IngestionSummary, ingest_walk_forward_window

    configure_logging()
    settings = get_settings()
    cfg = config or WorkerConfig()

    if not settings.api_football_key.strip():
        log.error("API_FOOTBALL_KEY is not set - ingestion aborted")
        return RunSummary(errors=1)

    client = ApiFootballClient.from_settings(settings)
    engine = make_engine(settings.database_url)

    today = date.today()
    start = today - timedelta(days=cfg.lookback_days)
    end = today + timedelta(days=cfg.lookahead_days)
    captured_at = datetime.now(UTC)

    aggregate = RunSummary()
    log.info(
        "ingestion_worker: starting run for %d league-season windows, window %s->%s",
        len(cfg.leagues), start, end,
    )

    for league_id, season in cfg.leagues:
        try:
            with session_scope(engine) as session:
                summary: IngestionSummary = ingest_walk_forward_window(
                    session,
                    client,
                    league_id=league_id,
                    season=season,
                    start_date=start,
                    end_date=end,
                    captured_at=captured_at,
                    include_fixture_statistics=cfg.include_statistics,
                    include_odds=cfg.include_odds,
                )

                log.info(
                    "ingestion_worker: league=%d season=%d - "
                    "fixtures +%d/~%d, odds +%d (deduped %d)",
                    league_id, season,
                    summary.fixtures_created, summary.fixtures_updated,
                    summary.odds_quotes_created,
                    summary.odds_quotes_deduplicated,
                )
                aggregate.odds_quotes_created += summary.odds_quotes_created

                aggregate.fixtures_created += summary.fixtures_created
                aggregate.fixtures_updated += summary.fixtures_updated

        except Exception:
            log.exception(
                "ingestion_worker: league=%d season=%d - ingestion failed",
                league_id, season,
            )
            aggregate.errors += 1

    log.info(
        "ingestion_worker: run complete - "
        "fixtures_created=%d fixtures_updated=%d odds_created=%d errors=%d",
        aggregate.fixtures_created,
        aggregate.fixtures_updated,
        aggregate.odds_quotes_created,
        aggregate.errors,
    )
    return aggregate


def _parse_args() -> argparse.Namespace:
    today_year = date.today().year
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--league", type=int, action="append", dest="leagues",
        metavar="ID", help="League id to ingest (repeatable). Default: 39",
    )
    parser.add_argument(
        "--season", type=int, default=today_year, metavar="YEAR",
        help=f"Season year (default: {today_year})",
    )
    parser.add_argument(
        "--lookback", type=int, default=7, metavar="DAYS",
        help="Days to look back for finished fixtures (default: 7)",
    )
    parser.add_argument(
        "--lookahead", type=int, default=7, metavar="DAYS",
        help="Days to look ahead for upcoming fixtures (default: 7)",
    )
    parser.add_argument(
        "--no-odds", action="store_true",
        help="Skip odds ingestion (saves quota)",
    )
    parser.add_argument(
        "--with-statistics", action="store_true",
        help="Also fetch fixture statistics (one request per fixture)",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously on --interval-second schedule",
    )
    parser.add_argument(
        "--interval", type=int, default=3600, metavar="SECONDS",
        help="Loop interval in seconds (default: 3600 = 1 hour)",
    )
    return parser.parse_args()


def main() -> None:
    # Make the repo root importable when run as a script
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()
    leagues_raw = args.leagues or [39]
    config = WorkerConfig(
        leagues=[(lid, args.season) for lid in leagues_raw],
        lookback_days=args.lookback,
        lookahead_days=args.lookahead,
        include_odds=not args.no_odds,
        include_statistics=args.with_statistics,
        interval_seconds=args.interval,
    )

    if args.loop:
        log.info("ingestion_worker: loop mode - running every %ds", config.interval_seconds)
        while True:
            summary = run_once(config)
            if summary.errors:
                log.warning("ingestion_worker: %d error(s) in this run", summary.errors)
            log.info("ingestion_worker: sleeping %ds until next run", config.interval_seconds)
            time.sleep(config.interval_seconds)
    else:
        summary = run_once(config)
        sys.exit(1 if summary.errors else 0)


if __name__ == "__main__":
    main()
