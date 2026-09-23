"""Scheduled API-Football ingestion worker.

Runs one ingestion loop iteration: fetches fixtures and optionally odds for
a configured set of leagues/seasons, committing each league-season window
independently so a partial failure does not roll back earlier successes.

League tiers
------------
**Production mode (default):** ingest only the four leagues whose calibration
and reliability evidence is established — Premier League (39), Bundesliga (78),
Ligue 1 (61), and La Liga (140).  The season is derived from today's date
using the European convention: seasons that start in July–August use the
calendar year of their start (e.g. the 2026/27 season → season=2026).

**Research mode (opt-in):** pass ``--all-leagues`` to discover the current
season's leagues from the API. The managed scheduler ingests a deterministic,
bounded batch each hour so its full rotation completes in about one day
without bursting the provider. ``Competition.validated`` remains the hard
public-signal and value-ticket gate. Unvalidated leagues may be forecast in a
separate ``research_mode`` archive only, where they cannot be published as
signals, selected for value tickets, or staked; the only consumer outside
research is the labelled, unstaked Daily Picks line (ACCUMULATOR_POLICY.md).

Quota management
----------------
The API-Football Pro plan provides a finite request budget. The managed
all-league mode therefore rotates a small batch at the hourly cadence and
stops immediately if the provider returns a rate-limit response.

The worker aborts league processing early when ``quota_stop_below`` remaining
requests are observed (default 100) so that settlement and signal workers
retain headroom.

Usage (one-shot):
    python -m backend.workers.ingestion_worker              # 4-league default
    python -m backend.workers.ingestion_worker --all-leagues
    python -m backend.workers.ingestion_worker --league 39 --league 78

Usage (continuous):
    python -m backend.workers.ingestion_worker --loop
    python -m backend.workers.ingestion_worker --loop --all-leagues --interval 3600
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from backend.services.api_football_ingestion import VALIDATED_PRODUCTION_EXTERNAL_IDS

log = logging.getLogger(__name__)

# Leagues whose calibration and reliability evidence is established.
# Only these are ingested in production mode. Derive this from the canonical
# ingestion allow-list so ingestion and publication scope cannot drift.
SUPPORTED_LEAGUE_IDS: tuple[int, ...] = tuple(
    sorted(int(league_id) for league_id in VALIDATED_PRODUCTION_EXTERNAL_IDS)
)

# Default interval (seconds) for production 4-league mode.
_DEFAULT_INTERVAL_SINGLE = 3600
# Managed all-league research rotates a bounded batch each hour.
_DEFAULT_INTERVAL_ALL = 3600


class _LeagueDiscoveryClient(Protocol):
    """Minimal client interface required by :func:`discover_leagues`."""

    def leagues(self, *, current: str, season: int) -> tuple[dict[str, Any], ...]:
        ...


def current_season() -> int:
    """Return the API-Football season year for today's date.

    European football seasons start in July–August.  The season year is the
    calendar year in which the season begins, so:
    - January–June  → season started the *previous* calendar year
    - July–December → season started *this* calendar year
    """
    today = date.today()
    return today.year if today.month >= 7 else today.year - 1


def _default_leagues() -> list[tuple[int, int]]:
    """Four supported league IDs paired with the current season."""
    season = current_season()
    return [(lid, season) for lid in SUPPORTED_LEAGUE_IDS]


@dataclass
class WorkerConfig:
    """What to fetch on each scheduled run.

    ``leagues`` defaults to the four validated competitions at the current
    season.  Pass ``None`` to enable all-leagues discovery (research/opt-in).
    """

    leagues: list[tuple[int, int]] | None = field(default_factory=_default_leagues)
    season: int = field(default_factory=current_season)
    lookback_days: int = 7
    lookahead_days: int = 7
    include_odds: bool = True
    include_statistics: bool = False
    interval_seconds: int = _DEFAULT_INTERVAL_SINGLE
    # Abort remaining leagues when API quota falls to or below this threshold.
    quota_stop_below: int = 100
    # ``None`` keeps the CLI one-shot all-league mode. The managed scheduler
    # supplies a bounded batch size for quota-safe broad coverage.
    max_leagues_per_run: int | None = None
    # These league ids are refreshed on every bounded research pass so the
    # production dashboard's price-freshness signal cannot be starved by the
    # research rotation.
    priority_league_ids: tuple[int, ...] = ()


@dataclass
class RunSummary:
    """Aggregated results across all league-season windows."""

    leagues_attempted: int = 0
    leagues_skipped_quota: int = 0
    fixtures_created: int = 0
    fixtures_updated: int = 0
    odds_quotes_created: int = 0
    errors: int = 0
    rate_limited: bool = False


def select_research_batch(
    leagues: list[tuple[int, int]],
    *,
    batch_size: int,
    now: datetime,
    interval_seconds: int,
    priority_league_ids: tuple[int, ...] = (),
) -> list[tuple[int, int]]:
    """Return one deterministic all-league batch for this UTC scheduler slot.

    Restarts select the same time slot instead of resetting to the first
    league, and every discovered league appears once in each full rotation.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be positive")
    if not leagues:
        return []
    priority_ids = set(priority_league_ids)
    priority = [item for item in leagues if item[0] in priority_ids]
    if len(priority) > batch_size:
        raise ValueError("batch_size cannot be smaller than priority league count")
    rotating = [item for item in leagues if item[0] not in priority_ids]
    if not rotating:
        return priority
    rotating_capacity = batch_size - len(priority)
    if rotating_capacity == 0:
        return priority
    batch_count = math.ceil(len(rotating) / rotating_capacity)
    batch_index = (int(now.timestamp()) // interval_seconds) % batch_count
    start = batch_index * rotating_capacity
    return priority + rotating[start:start + rotating_capacity]


def discover_leagues(client: _LeagueDiscoveryClient, season: int) -> list[tuple[int, int]]:
    """Fetch all leagues with a current season from the API.

    Returns a list of ``(league_id, season)`` pairs sorted by league_id.
    Logs the count but not individual names to keep output concise.
    """
    payloads = client.leagues(current="true", season=season)
    result: list[tuple[int, int]] = []
    for item in payloads:
        league_id = item.get("league", {}).get("id")
        if league_id is not None:
            result.append((int(league_id), season))
    result.sort()
    log.info("ingestion_worker: discovered %d leagues for season %d", len(result), season)
    return result


def run_once(config: WorkerConfig | None = None) -> RunSummary:
    """Execute one scheduled ingestion pass.  Returns an aggregated summary."""
    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.core.logging import configure_logging
    from backend.services.api_football_client import ApiFootballClient, ApiFootballRateLimitError
    from backend.services.api_football_ingestion import IngestionSummary, ingest_walk_forward_window

    configure_logging()
    settings = get_settings()
    cfg = config or WorkerConfig()

    if not settings.api_football_key.strip():
        log.error("API_FOOTBALL_KEY is not set - ingestion aborted")
        return RunSummary(errors=1)

    client = ApiFootballClient.from_settings(settings)
    engine = make_engine(settings.database_url)

    # Resolve league list — discover if all-leagues mode requested.
    leagues = cfg.leagues
    if leagues is None:
        leagues = discover_leagues(client, cfg.season)
        if cfg.max_leagues_per_run is not None:
            discovered_count = len(leagues)
            leagues = select_research_batch(
                leagues,
                batch_size=cfg.max_leagues_per_run,
                now=datetime.now(UTC),
                interval_seconds=cfg.interval_seconds,
                priority_league_ids=cfg.priority_league_ids,
            )
            log.info(
                "ingestion_worker: selected research batch %d/%d leagues",
                len(leagues), discovered_count,
            )

    today = date.today()
    start = today - timedelta(days=cfg.lookback_days)
    end = today + timedelta(days=cfg.lookahead_days)
    captured_at = datetime.now(UTC)

    aggregate = RunSummary()
    log.info(
        "ingestion_worker: starting run - %d league-season windows, window %s->%s",
        len(leagues), start, end,
    )

    for league_id, season in leagues:
        # Quota guard: stop early if remaining requests are critically low.
        remaining = client.last_requests_remaining
        if remaining is not None and remaining <= cfg.quota_stop_below:
            log.warning(
                "ingestion_worker: quota guard triggered (%d remaining ≤ %d) — "
                "stopping after %d/%d leagues",
                remaining, cfg.quota_stop_below,
                aggregate.leagues_attempted, len(leagues),
            )
            aggregate.leagues_skipped_quota = len(leagues) - aggregate.leagues_attempted
            break

        aggregate.leagues_attempted += 1
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

                if (
                    summary.fixtures_created
                    or summary.fixtures_updated
                    or summary.odds_quotes_created
                ):
                    log.info(
                        "ingestion_worker: league=%d season=%d — "
                        "fixtures +%d/~%d, odds +%d (deduped %d)",
                        league_id, season,
                        summary.fixtures_created, summary.fixtures_updated,
                        summary.odds_quotes_created,
                        summary.odds_quotes_deduplicated,
                    )

                aggregate.fixtures_created += summary.fixtures_created
                aggregate.fixtures_updated += summary.fixtures_updated
                aggregate.odds_quotes_created += summary.odds_quotes_created

        except ApiFootballRateLimitError:
            aggregate.rate_limited = True
            aggregate.leagues_skipped_quota = len(leagues) - aggregate.leagues_attempted
            log.warning(
                "ingestion_worker: provider rate limit reached — stopping after %d/%d leagues",
                aggregate.leagues_attempted, len(leagues),
            )
            break
        except Exception:
            log.exception(
                "ingestion_worker: league=%d season=%d — ingestion failed",
                league_id, season,
            )
            aggregate.errors += 1

    log.info(
        "ingestion_worker: run complete — "
        "leagues=%d/%d skipped_quota=%d "
        "fixtures_created=%d fixtures_updated=%d odds_created=%d rate_limited=%s errors=%d",
        aggregate.leagues_attempted, len(leagues),
        aggregate.leagues_skipped_quota,
        aggregate.fixtures_created,
        aggregate.fixtures_updated,
        aggregate.odds_quotes_created,
        aggregate.rate_limited,
        aggregate.errors,
    )
    return aggregate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    league_group = parser.add_mutually_exclusive_group()
    league_group.add_argument(
        "--all-leagues", action="store_true", default=False,
        help=(
            "Research mode: discover and ingest all current-season leagues. "
            f"Recommended interval: {_DEFAULT_INTERVAL_ALL}s. "
            "Signals are NOT publication-gated for unvalidated competitions "
            "(temporary barrier only — see DEVELOPMENT.md §4)."
        ),
    )
    league_group.add_argument(
        "--league", type=int, action="append", dest="leagues",
        metavar="ID",
        help=(
            "Restrict to this league id (repeatable). "
            f"Default: the {len(SUPPORTED_LEAGUE_IDS)} supported leagues."
        ),
    )
    parser.add_argument(
        "--season", type=int, default=None, metavar="YEAR",
        help=f"Season year. Default: derived from today ({current_season()}).",
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
        "--quota-stop-below", type=int, default=100, metavar="N",
        help="Stop processing leagues when remaining quota falls to N (default: 100)",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously on --interval schedule",
    )
    parser.add_argument(
        "--interval", type=int, default=None, metavar="SECONDS",
        help=(
            f"Loop interval in seconds "
            f"(default: {_DEFAULT_INTERVAL_SINGLE}s for production mode, "
            f"{_DEFAULT_INTERVAL_ALL}s for --all-leagues)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()
    season = args.season if args.season is not None else current_season()

    if args.leagues:
        # Explicit league IDs provided.
        leagues: list[tuple[int, int]] | None = [(lid, season) for lid in args.leagues]
        default_interval = _DEFAULT_INTERVAL_SINGLE
    elif args.all_leagues:
        # Research/all-leagues mode.
        leagues = None  # discover at runtime
        default_interval = _DEFAULT_INTERVAL_ALL
    else:
        # Production default: four supported leagues.
        leagues = [(lid, season) for lid in SUPPORTED_LEAGUE_IDS]
        default_interval = _DEFAULT_INTERVAL_SINGLE

    interval = args.interval if args.interval is not None else default_interval

    config = WorkerConfig(
        leagues=leagues,
        season=season,
        lookback_days=args.lookback,
        lookahead_days=args.lookahead,
        include_odds=not args.no_odds,
        include_statistics=args.with_statistics,
        interval_seconds=interval,
        quota_stop_below=args.quota_stop_below,
    )

    if args.loop:
        log.info("ingestion_worker: loop mode — every %ds", config.interval_seconds)
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
