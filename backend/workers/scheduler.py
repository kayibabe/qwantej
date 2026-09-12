"""Multi-worker scheduler.

Runs ingestion, signal pipeline, and settlement on configurable fixed
intervals using daemon threads.  Each worker is fully isolated: an
exception in one thread does not affect the others.

League tiers
------------
**Production mode (default):** ingests only the four calibrated leagues
(Premier League 39, Bundesliga 78, Ligue 1 61, La Liga 140).  Interval
defaults to 3,600 s.

**Research mode (opt-in):** ``--all-leagues`` discovers all ~785 current-
season leagues each run.  Interval defaults to 18,000 s (5 h) to stay within
the 7,500-request/day Pro quota.  Fixtures and odds are stored for all
leagues, and the signal pipeline enforces the ``Competition.validated``
publication gate before feature extraction or inference.

.. warning::
    Research runs may ingest all leagues, but unvalidated competitions cannot
    publish signals because the signal pipeline checks the validation flag.

Intervals:
    --ingest-interval  N   override the ingestion interval
    --signal-interval  N   seconds between signal pipeline  (default 3600)
    --settle-interval  N   seconds between settlement runs  (default 900)
    --signal-offset    N   delay before first signal run so fresh odds are
                           available after each ingest tick (default 120)

Stop with Ctrl-C or SIGTERM.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_STOP = threading.Event()

_DEFAULT_INGEST_INTERVAL_PRODUCTION = 3600
_DEFAULT_INGEST_INTERVAL_ALL = 18000


def _worker_loop(
    name: str,
    run_fn,
    interval: int,
    initial_delay: int = 0,
) -> None:
    """Run *run_fn* every *interval* seconds in a daemon thread.

    The first call happens after *initial_delay* seconds (default 0 = immediately).
    Exceptions from *run_fn* are logged and swallowed so the loop continues.
    """
    if initial_delay:
        log.info("scheduler: %s first run in %ds", name, initial_delay)
        _STOP.wait(timeout=initial_delay)

    while not _STOP.is_set():
        log.info("scheduler: starting %s run at %s", name, datetime.now(UTC).isoformat())
        try:
            run_fn()
        except Exception:  # noqa: BLE001
            log.exception("scheduler: %s run failed", name)
        log.info("scheduler: %s sleeping %ds", name, interval)
        _STOP.wait(timeout=interval)


def _make_ingestion_run(
    *,
    all_leagues: bool,
    explicit_league_ids: list[int],
    season: int,
) -> object:
    """Return a zero-argument callable for the ingestion worker loop.

    Priority: explicit_league_ids > all_leagues flag > production default (4 leagues).
    ``leagues=None`` in WorkerConfig signals all-leagues discovery mode.
    """
    from backend.workers.ingestion_worker import SUPPORTED_LEAGUE_IDS, WorkerConfig

    if explicit_league_ids:
        config = WorkerConfig(
            leagues=[(lid, season) for lid in explicit_league_ids],
            season=season,
        )
    elif all_leagues:
        # Research mode: discover all leagues at runtime.
        config = WorkerConfig(leagues=None, season=season)
    else:
        # Production default: four supported leagues.
        config = WorkerConfig(
            leagues=[(lid, season) for lid in SUPPORTED_LEAGUE_IDS],
            season=season,
        )

    def _run() -> None:
        from backend.workers.ingestion_worker import run_once
        run_once(config)

    return _run


def _signal_pipeline_run() -> None:
    # run_once lives in a script, not a package — import via importlib.
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_signal_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_signal_pipeline", script)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    mod.run_once()


def _settlement_run() -> None:
    from backend.core.db import session_scope
    from backend.workers.settlement_worker import run_settlement

    with session_scope() as session:
        run_settlement(session)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)

    league_group = p.add_mutually_exclusive_group()
    league_group.add_argument(
        "--all-leagues", action="store_true", default=False,
        help=(
            "Research mode: discover all current-season leagues each ingest run. "
            f"Sets ingest interval to {_DEFAULT_INGEST_INTERVAL_ALL}s unless overridden."
        ),
    )
    league_group.add_argument(
        "--league", type=int, action="append", dest="leagues", metavar="ID",
        help=(
            "Restrict ingestion to this league id (repeatable). "
            "Overrides the production default and --all-leagues."
        ),
    )

    p.add_argument(
        "--season", type=int, default=None, metavar="YEAR",
        help="Season year (default: derived from today's date)",
    )
    p.add_argument(
        "--ingest-interval", type=int, default=None, metavar="S",
        help=(
            f"Ingest interval in seconds "
            f"(default: {_DEFAULT_INGEST_INTERVAL_PRODUCTION}s production, "
            f"{_DEFAULT_INGEST_INTERVAL_ALL}s --all-leagues)"
        ),
    )
    p.add_argument("--signal-interval", type=int, default=3600, metavar="S")
    p.add_argument("--settle-interval", type=int, default=900, metavar="S")
    p.add_argument(
        "--signal-offset", type=int, default=120, metavar="S",
        help="Seconds to wait before first signal-pipeline run (default 120)",
    )
    return p.parse_args()


def main() -> None:
    from backend.core.logging import configure_logging
    configure_logging()

    args = _parse_args()

    def _handle_stop(signum, frame):  # noqa: ANN001
        log.info("scheduler: received signal %s — shutting down", signum)
        _STOP.set()

    signal.signal(signal.SIGINT, _handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_stop)

    from backend.workers.ingestion_worker import current_season
    season = args.season if args.season is not None else current_season()

    explicit_league_ids: list[int] = args.leagues or []
    all_leagues_mode: bool = args.all_leagues  # False by default — opt-in only

    ingest_interval = args.ingest_interval
    if ingest_interval is None:
        ingest_interval = (
            _DEFAULT_INGEST_INTERVAL_ALL if all_leagues_mode
            else _DEFAULT_INGEST_INTERVAL_PRODUCTION
        )

    ingestion_run = _make_ingestion_run(
        all_leagues=all_leagues_mode,
        explicit_league_ids=explicit_league_ids,
        season=season,
    )

    if all_leagues_mode:
        mode_label = "all-leagues (research)"
    elif explicit_league_ids:
        mode_label = f"explicit leagues={explicit_league_ids}"
    else:
        mode_label = "production (4 supported leagues)"

    log.info(
        "scheduler: mode=%s season=%d ingest_interval=%ds",
        mode_label, season, ingest_interval,
    )

    workers = [
        ("ingestion",       ingestion_run,         ingest_interval,      0),
        ("signal-pipeline", _signal_pipeline_run,  args.signal_interval, args.signal_offset),
        ("settlement",      _settlement_run,        args.settle_interval, 0),
    ]

    threads = []
    for name, fn, interval, delay in workers:
        t = threading.Thread(
            target=_worker_loop,
            args=(name, fn, interval, delay),
            name=f"scheduler-{name}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        log.info(
            "scheduler: %s thread started — interval=%ds initial_delay=%ds",
            name, interval, delay,
        )

    log.info("scheduler: running (Ctrl-C to stop)")
    _STOP.wait()
    log.info("scheduler: stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
