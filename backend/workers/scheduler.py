"""Multi-worker scheduler.

Runs ingestion, signal pipeline, and settlement on configurable fixed
intervals using daemon threads.  Each worker is fully isolated: an
exception in one thread does not affect the others.

Usage:
    python -m backend.workers.scheduler
    python -m backend.workers.scheduler --all-leagues
    python -m backend.workers.scheduler --all-leagues \\
        --ingest-interval 18000 --signal-interval 3600 --settle-interval 900

League modes
------------
``--all-leagues`` (default) discovers all ~785 current-season leagues from
the API at the start of each ingestion run and sets the ingest interval to
18,000 s (5 h) unless overridden — this keeps daily quota usage within the
7,500-request Pro plan limit.

Omit ``--all-leagues`` to fall back to the leagues listed via ``--league``
(repeatable) with a 3,600 s default interval.

Intervals:
    --ingest-interval  N   seconds between ingestion runs
                           (default: 18000 with --all-leagues, 3600 without)
    --signal-interval  N   seconds between signal pipeline  (default 3600)
    --settle-interval  N   seconds between settlement runs  (default 900)
    --signal-offset    N   seconds to delay first signal run after ingestion
                           so fresh odds are available      (default 120)

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

_DEFAULT_INGEST_INTERVAL_ALL = 18000
_DEFAULT_INGEST_INTERVAL_SINGLE = 3600


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


def _make_ingestion_run(*, all_leagues: bool, leagues: list[int], season: int) -> object:
    """Return a zero-argument callable for the ingestion worker loop."""
    from backend.workers.ingestion_worker import WorkerConfig

    if all_leagues:
        config = WorkerConfig(leagues=None, season=season)
    else:
        config = WorkerConfig(
            leagues=[(lid, season) for lid in leagues] if leagues else None,
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
        "--all-leagues", action="store_true", default=True,
        help=(
            "Discover all current-season leagues each ingestion run "
            f"(default interval: {_DEFAULT_INGEST_INTERVAL_ALL}s)"
        ),
    )
    league_group.add_argument(
        "--league", type=int, action="append", dest="leagues", metavar="ID",
        help="Restrict ingestion to this league id (repeatable; disables auto-discovery)",
    )

    p.add_argument(
        "--season", type=int, default=None, metavar="YEAR",
        help="Season year (default: current calendar year)",
    )
    p.add_argument("--ingest-interval", type=int, default=None, metavar="S",
                   help=(
                       f"Ingest interval in seconds "
                       f"(default: {_DEFAULT_INGEST_INTERVAL_ALL} with --all-leagues, "
                       f"{_DEFAULT_INGEST_INTERVAL_SINGLE} without)"
                   ))
    p.add_argument("--signal-interval", type=int, default=3600, metavar="S")
    p.add_argument("--settle-interval", type=int, default=900, metavar="S")
    p.add_argument("--signal-offset", type=int, default=120, metavar="S",
                   help="Seconds to wait before first signal-pipeline run (default 120)")
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

    from datetime import date
    season = args.season if args.season is not None else date.today().year

    # Determine whether we're in all-leagues mode.
    # --league explicitly given → single/explicit mode; otherwise → all-leagues.
    explicit_leagues: list[int] = args.leagues or []
    all_leagues_mode = not explicit_leagues  # all-leagues when no explicit IDs given

    ingest_interval = args.ingest_interval
    if ingest_interval is None:
        ingest_interval = (
            _DEFAULT_INGEST_INTERVAL_ALL if all_leagues_mode
            else _DEFAULT_INGEST_INTERVAL_SINGLE
        )

    ingestion_run = _make_ingestion_run(
        all_leagues=all_leagues_mode,
        leagues=explicit_leagues,
        season=season,
    )

    mode_label = "all-leagues" if all_leagues_mode else f"leagues={explicit_leagues}"
    log.info(
        "scheduler: mode=%s season=%d ingest_interval=%ds",
        mode_label, season, ingest_interval,
    )

    workers = [
        ("ingestion",       ingestion_run,         ingest_interval,       0),
        ("signal-pipeline", _signal_pipeline_run,  args.signal_interval,  args.signal_offset),
        ("settlement",      _settlement_run,        args.settle_interval,  0),
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
