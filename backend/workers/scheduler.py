"""Multi-worker scheduler.

Runs ingestion, signal pipeline, and settlement on configurable fixed
intervals using daemon threads.  Each worker is fully isolated: an
exception in one thread does not affect the others.

Usage:
    python -m backend.workers.scheduler
    python -m backend.workers.scheduler --ingest-interval 3600 \\
        --signal-interval 3600 --settle-interval 900

Intervals:
    --ingest-interval  N   seconds between ingestion runs   (default 3600)
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
import time
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_STOP = threading.Event()


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


def _ingestion_run() -> None:
    from backend.workers.ingestion_worker import WorkerConfig, run_once
    run_once(WorkerConfig())


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
    p.add_argument("--ingest-interval", type=int, default=3600, metavar="S")
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

    workers = [
        ("ingestion",       _ingestion_run,       args.ingest_interval, 0),
        ("signal-pipeline", _signal_pipeline_run, args.signal_interval, args.signal_offset),
        ("settlement",      _settlement_run,       args.settle_interval, 0),
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
