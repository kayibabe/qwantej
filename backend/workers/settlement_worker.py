"""Settlement worker: fetches finished fixtures and settles pending predictions.

Invoke via ``main()`` as a scheduled job (cron, APScheduler, or management
command).  All logic lives in ``run_settlement()`` so tests can call it with
an injected session without spawning a process.

The worker:
  1. Queries the local DB for FINISHED fixtures with unsettled predictions in
     the lookback window.
  2. Resolves each prediction's outcome (``resolve_outcome``) and looks up
     the latest post-kickoff odds quote for CLV.
  3. Calls ``settle_prediction()`` and flushes per-fixture so a single bad
     fixture does not block the rest of the batch.
  4. After all fixtures, runs calibration and execution drift detection on the
     most recent settled window and logs warnings when thresholds are exceeded.
     Drift detection is evidence-gathering only — no automated model swap is
     triggered here (champion-challenger governance is human-reviewed, §43).

Session contract: ``run_settlement()`` accepts an open session, flushes
after each fixture's batch, but does NOT commit.  The caller (``main()`` or
a test) controls the commit boundary, following the service-layer convention
used throughout this codebase.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.db import session_scope
from backend.models import (
    Fixture,
    FixtureStatus,
    Prediction,
    Settlement,
)
from backend.models import (
    SettlementOutcome as OrmSettlementOutcome,
)
from backend.services.performance import performance_report
from backend.services.reliability import rebuild_reliability_snapshots
from backend.services.settlement import (
    SettlementError,
    find_closing_odds,
    resolve_outcome,
    settle_prediction,
)
from qwantej.notifications.types import Notification, NotificationEvent, NotificationLevel
from qwantej.performance.drift import detect_calibration_drift, detect_execution_drift
from qwantej.settlement.types import SettlementOutcome as EngineOutcome

log = logging.getLogger(__name__)

_LOOKBACK_DAYS = 7
_DRIFT_MIN_SAMPLES = 30
_RESULT_SOURCE = "api-football"

# Markers that identify a settlement-table uniqueness violation in the error
# string — the only IntegrityError that is safe to treat as an idempotent skip.
# PostgreSQL includes the constraint name; SQLite includes the column path.
_SETTLEMENT_UNIQUE_MARKERS: tuple[str, ...] = (
    "uq_settlements_active_subject",      # PG partial unique index
    "uq_settlements_subject_settled_at",  # PG / SQLite named unique constraint
    "settlements.subject_type",           # SQLite UNIQUE constraint failed message
)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class FixtureBatch:
    fixture_id: uuid.UUID
    settled: int = 0
    skipped_already_settled: int = 0
    skipped_no_result: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkerRun:
    started_at: datetime
    batches: list[FixtureBatch] = field(default_factory=list)
    drift_checked: bool = False

    @property
    def total_settled(self) -> int:
        return sum(b.settled for b in self.batches)

    @property
    def total_errors(self) -> int:
        return sum(len(b.errors) for b in self.batches)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _finished_fixtures_with_predictions(
    session: Session, *, since: datetime
) -> list[Fixture]:
    """Return FINISHED fixtures that have at least one unsettled prediction."""
    settled_ids = (
        select(Settlement.subject_id)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.supersedes_id.is_(None),
        )
    )
    has_unsettled = (
        select(Prediction.fixture_id)
        .where(Prediction.id.not_in(settled_ids))
        .distinct()
    )
    stmt = (
        select(Fixture)
        .where(
            Fixture.status == FixtureStatus.FINISHED,
            Fixture.kickoff_utc >= since,
            Fixture.id.in_(has_unsettled),
        )
        .order_by(Fixture.kickoff_utc)
    )
    return list(session.scalars(stmt))


def _unsettled_predictions(
    session: Session, fixture_id: uuid.UUID
) -> list[Prediction]:
    """Return Prediction rows for *fixture_id* with no settlement row yet."""
    settled_ids = (
        select(Settlement.subject_id)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.supersedes_id.is_(None),
        )
    )
    stmt = select(Prediction).where(
        Prediction.fixture_id == fixture_id,
        Prediction.id.not_in(settled_ids),
    )
    return list(session.scalars(stmt))


def _drift_inputs(
    session: Session,
    *,
    limit: int = 500,
) -> tuple[list[float], list[float], list[float]]:
    """Collect ``(probabilities, binary_outcomes, clv_values)`` for drift detection.

    Uses the *effective* settlement for each prediction — the one that has
    not been superseded by a correction.  A row whose ``id`` appears in
    another row's ``supersedes_id`` has been corrected and is excluded; only
    the correcting row (with the right outcome) is included.

    Only WIN/LOSS rows with a recorded ``taken_probability`` contribute to
    calibration metrics; voids and pushes carry no Brier signal.
    """
    # Rows that have been corrected: their id appears in supersedes_id of another row.
    superseded_ids = (
        select(Settlement.supersedes_id)
        .where(Settlement.supersedes_id.is_not(None))
    )
    stmt = (
        select(Settlement)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.id.not_in(superseded_ids),
            Settlement.taken_probability.is_not(None),
            Settlement.outcome.in_(
                [OrmSettlementOutcome.WIN, OrmSettlementOutcome.LOSS]
            ),
        )
        .order_by(Settlement.settled_at.desc())
        .limit(limit)
    )
    rows = list(session.scalars(stmt))
    probs = [float(r.taken_probability) for r in rows if r.taken_probability is not None]
    outcomes = [1.0 if r.outcome == OrmSettlementOutcome.WIN else 0.0 for r in rows]
    clv_vals = [float(r.clv) for r in rows if r.clv is not None]
    return probs, outcomes, clv_vals


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_settlement(session: Session, *, now: datetime | None = None) -> WorkerRun:
    """Settle all pending predictions for FINISHED fixtures.

    See module docstring for session-commit contract.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=_LOOKBACK_DAYS)
    run = WorkerRun(started_at=now)

    fixtures = _finished_fixtures_with_predictions(session, since=since)
    log.info("settlement_worker: %d fixture(s) to process", len(fixtures))

    for fixture in fixtures:
        batch = FixtureBatch(fixture_id=fixture.id)
        run.batches.append(batch)
        predictions = _unsettled_predictions(session, fixture.id)

        for prediction in predictions:
            line = float(prediction.line) if prediction.line is not None else None

            try:
                outcome = resolve_outcome(
                    fixture,
                    prediction.market,
                    prediction.selection,
                    line=line,
                )
            except SettlementError as exc:
                batch.errors.append(
                    f"prediction {prediction.id}: resolve_outcome: {exc}"
                )
                continue

            # Fixture is FINISHED in the DB but goals not yet ingested.
            if outcome is EngineOutcome.VOID and (
                fixture.home_goals is None or fixture.away_goals is None
            ):
                batch.skipped_no_result += 1
                continue

            closing_odds, _, closing_quote_id = find_closing_odds(
                session,
                fixture_id=fixture.id,
                market=prediction.market,
                selection=prediction.selection,
                line=line,
                after=fixture.kickoff_utc,
            )

            try:
                with session.begin_nested():
                    settle_prediction(
                        session,
                        prediction,
                        outcome=outcome,
                        settled_at=now,
                        closing_odds=closing_odds,
                        closing_quote_id=closing_quote_id,
                        result_source=_RESULT_SOURCE,
                    )
                batch.settled += 1
            except IntegrityError as exc:
                # Only suppress settlement-table uniqueness conflicts — the
                # signal that a concurrent worker won the race.  Any other
                # IntegrityError (FK violation, NOT NULL failure, wrong table)
                # is a real bug and must not be silently swallowed.
                err_str = str(exc).lower()
                if not any(m in err_str for m in _SETTLEMENT_UNIQUE_MARKERS):
                    raise
                log.debug(
                    "settlement_worker: prediction %s already settled (concurrent write)",
                    prediction.id,
                )
                batch.skipped_already_settled += 1
            except SettlementError as exc:
                if "already settled" in str(exc):
                    batch.skipped_already_settled += 1
                else:
                    batch.errors.append(f"prediction {prediction.id}: {exc}")
            except ValueError as exc:
                # settle_prediction can raise ValueError for malformed probability
                # or odds fields (e.g. p > 1 stored in error).  Isolate so one
                # bad prediction does not abort the whole fixture's batch.
                batch.errors.append(
                    f"prediction {prediction.id}: invalid field value: {exc}"
                )

        session.flush()
        log.info(
            "settlement_worker: fixture %s — settled=%d skipped=%d errors=%d",
            fixture.id,
            batch.settled,
            batch.skipped_already_settled + batch.skipped_no_result,
            len(batch.errors),
        )
        for err in batch.errors:
            log.error("settlement_worker: %s", err)

    # Post-run drift detection (logging only; no automated action here).
    probs, outcomes, clv_vals = _drift_inputs(session)

    if len(probs) >= _DRIFT_MIN_SAMPLES:
        try:
            calib = detect_calibration_drift(probs, outcomes)
            if calib.is_drifted:
                log.warning(
                    "settlement_worker: CALIBRATION DRIFT — "
                    "MCE=%.4f threshold=%.4f n=%d",
                    calib.mean_calibration_error,
                    calib.threshold,
                    calib.n_samples,
                )
            else:
                log.info(
                    "settlement_worker: calibration OK — MCE=%.4f n=%d",
                    calib.mean_calibration_error,
                    calib.n_samples,
                )
        except ValueError as exc:
            log.debug("settlement_worker: calibration check skipped: %s", exc)

    if len(clv_vals) >= _DRIFT_MIN_SAMPLES:
        half = len(clv_vals) // 2
        try:
            exec_drift = detect_execution_drift(clv_vals[half:], clv_vals[:half])
            if exec_drift.is_drifted:
                log.warning(
                    "settlement_worker: EXECUTION DRIFT — "
                    "CLV shift=%.4f threshold=%.4f ref_n=%d cur_n=%d",
                    exec_drift.clv_shift,
                    exec_drift.threshold,
                    exec_drift.n_reference,
                    exec_drift.n_current,
                )
        except ValueError as exc:
            log.debug("settlement_worker: execution drift check skipped: %s", exc)

    run.drift_checked = True

    # Rebuild reliability snapshots so the next signal pipeline run uses
    # up-to-date lrs/mrs scores.  Only trigger when new settlements landed;
    # no-op otherwise to avoid writing redundant snapshot rows.
    if run.total_settled > 0:
        import subprocess
        try:
            code_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            code_commit = "unknown"
        try:
            n_snaps = rebuild_reliability_snapshots(
                session, as_of=now, code_commit=code_commit
            )
            if n_snaps:
                log.info(
                    "settlement_worker: reliability rebuilt — %d snapshot(s) written",
                    n_snaps,
                )
            else:
                log.info(
                    "settlement_worker: reliability rebuild skipped — no qualifying observations"
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("settlement_worker: reliability rebuild failed: %s", exc)

    # KPI snapshot logged after each run so trends are visible in structured logs.
    try:
        kpis = performance_report(session)
        log.info(
            "settlement_worker: KPI snapshot — "
            "n=%d hit_rate=%s brier=%s roi=%s mean_clv=%s",
            kpis.n_settled,
            f"{kpis.hit_rate:.4f}" if kpis.hit_rate is not None else "n/a",
            f"{kpis.brier_score:.4f}" if kpis.brier_score is not None else "n/a",
            f"{kpis.roi:.4f}" if kpis.roi is not None else "n/a",
            f"{kpis.mean_clv:.4f}" if kpis.mean_clv is not None else "n/a",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("settlement_worker: KPI snapshot failed: %s", exc)

    log.info(
        "settlement_worker: run complete — settled=%d errors=%d",
        run.total_settled,
        run.total_errors,
    )
    return run


def _notify_run(run: WorkerRun) -> None:
    """Send a Telegram summary of the settlement run if notifications are configured."""
    try:
        from backend.core.config import get_settings
        from backend.services.notifier import TelegramNotifier

        notifier = TelegramNotifier.from_settings(get_settings())
        if not notifier.enabled:
            return

        level = NotificationLevel.ERROR if run.total_errors else NotificationLevel.INFO
        body = (
            f"Settled: {run.total_settled} | "
            f"Fixtures: {len(run.batches)} | "
            f"Errors: {run.total_errors}"
        )
        notifier.send(
            Notification(
                event=NotificationEvent.SETTLEMENT_BATCH_DONE,
                title="Settlement batch complete",
                body=body,
                level=level,
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("settlement_worker: notification failed: %s", exc)


def main() -> None:
    """Entry point for scheduled invocation."""
    from backend.core.config import get_settings
    from backend.core.logging import configure_logging

    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    with session_scope() as session:
        run = run_settlement(session)
    _notify_run(run)


if __name__ == "__main__":
    main()
