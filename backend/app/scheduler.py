"""
scheduler.py — APScheduler jobs for automatic fixture + odds sync.
Runs sync_and_compute() at configured times (default: 06:00, 14:00, 18:00, 23:30 UTC).

Startup behaviour
-----------------
On startup:
  1. Catch-up sync: re-pulls any past dates that have pending bets with non-final
     fixture statuses in the DB. This handles the case where the backend was offline
     when yesterday's matches finished, leaving fixtures stuck at "2H"/"1H" in DB.
  2. Today sync: full ingestion + signal compute + settlement for today.

Dev override
------------
Set SKIP_STARTUP_SYNC=true in backend/.env to suppress the startup sync entirely.
This costs zero API calls on hot-reload restarts during development.
The scheduled jobs still run normally — only the one-shot startup pull is skipped.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, distinct

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models import TrackedBet, Fixture
from app.services import ingestion
from app.services.ensemble_service import compute_snapshots_for_date as compute_ensemble_snapshots
from app.services.settlement import settle_bets_for_date, FINAL_STATUSES
from app.services.telegram import (
    push_kickoff_alerts,
    check_and_push_pending_results,
    push_morning_digest,
    push_tomorrow_digest,
    push_value_band_alert,
    push_ingestion_alert,
)

logger = logging.getLogger("Qwantej.scheduler")
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


async def catchup_past_dates() -> int:
    """
    Re-sync any past dates that have Pending bets whose fixture status is not yet
    final in the DB. Returns the number of bets settled.

    This is the fix for the common scenario where the backend was offline (or a
    scheduled sync failed) when yesterday's matches finished, leaving fixture rows
    stuck at "2H" / "HT" / "1H" in the database.  Without this, settlement never
    triggers because _fixture_is_final() returns False for those stale statuses.

    Uses force=True on ingestion so the 2-hour cooldown and all-final cache guards
    are bypassed — we explicitly need fresh data for these past-date fixtures.
    """
    async with AsyncSessionLocal() as db:
        today = date.today()

        # Find distinct past dates that still have Pending bets.
        # Cap lookback to 60 days to avoid burning API quota on a DB restore with
        # many old pending bets that will never settle (cancelled leagues, stale data).
        lookback_cutoff = today - timedelta(days=60)
        pending_dates_result = await db.execute(
            select(distinct(TrackedBet.event_date))
            .where(
                TrackedBet.result_status == "Pending",
                TrackedBet.event_date < today,
                TrackedBet.event_date >= lookback_cutoff,
                TrackedBet.event_date.isnot(None),
            )
        )
        past_dates = [row[0] for row in pending_dates_result.all() if row[0]]

        if not past_dates:
            return 0

        for d in past_dates:
            # Only re-sync if at least one fixture for that date is NOT yet final in DB.
            stale_result = await db.execute(
                select(Fixture.id)
                .where(
                    Fixture.event_date == d,
                    Fixture.status.notin_(list(FINAL_STATUSES)),
                )
                .limit(1)
            )
            has_stale = stale_result.scalar() is not None

            if not has_stale:
                # All fixtures already final in DB — skip re-sync, just settle.
                logger.info(
                    "Catch-up: %s fixtures all final in DB — skipping API, running settlement.", d
                )
                continue

            logger.info(
                "Catch-up: %s has pending bets with non-final fixtures — force-syncing.", d
            )
            try:
                run = await ingestion.sync_date(db, d, force=True)
                logger.info(
                    "Catch-up sync %s: status=%s fixtures=%s",
                    d, run.status, run.fixtures_pulled,
                )
            except Exception as e:
                logger.error("Catch-up sync failed for %s: %s", d, e)

        # Settle all pending bets now that fixture statuses are refreshed.
        n_settled = (await settle_bets_for_date(db, None))["settled"]
        if n_settled:
            logger.info("Catch-up settlement: %d pending bet(s) settled.", n_settled)
            # Push results for any fully-settled date after catch-up.
            try:
                n_results = await check_and_push_pending_results(db)
                if n_results:
                    logger.info("Catch-up results report: pushed results for %d date(s)", n_results)
            except Exception:
                logger.exception("Catch-up results push failed — continuing normally")
        return n_settled


async def sync_and_compute(run_date: date | None = None, *, morning_extras: bool = False, evening_extras: bool = False) -> None:
    if run_date is None:
        run_date = date.today()
    async with AsyncSessionLocal() as db:
        try:
            logger.info("Scheduler: syncing %s", run_date)
            run = await ingestion.sync_date(db, run_date)
            if run.status != "success":
                try:
                    await push_ingestion_alert(db, run_date, run.status, getattr(run, "error_message", None))
                except Exception:
                    logger.exception("Ingestion alert failed — non-fatal")
            if run.status == "success":
                # Run ensemble engine: produces ForecastSnapshot rows.
                try:
                    ens = await compute_ensemble_snapshots(db, run_date, horizon="D-0")
                    logger.info(
                        "Ensemble: %s — %d snapshots (%d signals, %d no-signal)",
                        run_date, ens["total"], ens["signals"], ens["no_signals"],
                    )
                except Exception:
                    logger.exception("Ensemble snapshot failed for %s — continuing normally", run_date)

                # Settle every pending bet with a final fixture (any event_date), not only run_date.
                n_settled = (await settle_bets_for_date(db, None))["settled"]
                logger.info(
                    "Scheduler: %s done — %d fixtures, %d bets settled",
                    run_date, run.fixtures_pulled, n_settled,
                )
                # Push results for any fully-settled date (today + last 2 days).
                try:
                    n_results = await check_and_push_pending_results(db)
                    if n_results:
                        logger.info("Results report: pushed results for %d date(s)", n_results)
                except Exception:
                    logger.exception("Telegram results push failed — continuing normally")

                # ── Morning extras (first daily sync only) ────────────────────
                if morning_extras:
                    try:
                        n_sent = await push_morning_digest(db)
                        if n_sent:
                            logger.info("Morning digest: sent to %d channel(s)", n_sent)
                    except Exception:
                        logger.exception("Morning digest failed — continuing normally")

                # ── Evening extras (19:00 UTC sync only) ─────────────────────
                # Tomorrow pre-sync at peak odds availability + advisory + ACCA + Telegram.
                if evening_extras:
                    tomorrow = run_date + timedelta(days=1)
                    try:
                        t_run = await ingestion.sync_date(db, tomorrow)
                        if t_run.status == "success":
                            n_sig = await compute_signals_for_date(db, tomorrow)
                            await db.commit()
                            logger.info("Tomorrow pre-sync: %s — %d fixtures, %d signals", tomorrow, t_run.fixtures_pulled, n_sig)
                            try:
                                ens_t = await compute_ensemble_snapshots(db, tomorrow, horizon="D-1")
                                logger.info(
                                    "Ensemble (D-1): %s — %d snapshots (%d signals, %d no-signal)",
                                    tomorrow, ens_t["total"], ens_t["signals"], ens_t["no_signals"],
                                )
                            except Exception:
                                logger.exception("Ensemble D-1 snapshot for %s failed — continuing normally", tomorrow)
                        else:
                            logger.warning("Tomorrow pre-sync: %s status=%s", tomorrow, t_run.status)
                    except Exception:
                        logger.exception("Tomorrow pre-sync failed — continuing normally")
                    try:
                        n_sent = await push_tomorrow_digest(db, tomorrow)
                        if n_sent:
                            logger.info("Tomorrow digest: sent to %d channel(s) for %s", n_sent, tomorrow)
                    except Exception:
                        logger.exception("Tomorrow digest push failed — continuing normally")
                    try:
                        vb_sent = await push_value_band_alert(db, tomorrow)
                        if vb_sent:
                            logger.info("Value Band alert sent for %s", tomorrow)
                    except Exception:
                        logger.exception("Value Band alert failed — continuing normally")

        except Exception:
            logger.exception("Scheduler error for %s", run_date)
            raise


async def startup_sync() -> None:
    """
    On startup:
      1. Catch-up: re-sync past dates with pending bets that have stale fixture statuses.
         This is the primary fix for bets stuck as Pending after the backend was offline.
      2. Today: full ingestion + signals + settlement.

    Skipped entirely when SKIP_STARTUP_SYNC=true (for local dev — avoids quota burn
    on hot-reload restarts). When skipped, catch-up settlement still runs from DB state.
    """
    if os.getenv("SKIP_STARTUP_SYNC", "").lower() in ("1", "true", "yes"):
        logger.info(
            "SKIP_STARTUP_SYNC is set — skipping startup sync. "
            "Running catch-up settlement from existing DB scores."
        )
        # Even when skipping the full sync, run catch-up so stale past-date fixtures
        # are refreshed and pending bets can settle.
        await catchup_past_dates()
        return

    # Step 1: housekeeping — purge stale snapshots + deactivate redundant proposals.
    await _cleanup_old_snapshots()

    # Step 2: resolve any pending bets from past dates before syncing today.
    await catchup_past_dates()

    # Step 3: sync today normally.
    logger.info("Startup sync: pulling today (%s)", date.today())
    await sync_and_compute(date.today())

    # Step 4: run calibration audit + isotonic refit so knots are current immediately
    # after a deploy, without waiting for the 05:00 UTC scheduled window.
    try:
        await _daily_calibration_job()
        logger.info("Startup calibration: audit + isotonic refit complete")
    except Exception:
        logger.exception("Startup calibration failed — continuing normally")


async def _cleanup_old_snapshots() -> None:
    """
    Weekly housekeeping — deletes market_snapshots rows for fixtures older than
    30 days.  These odds are no longer needed for signal computation or settlement
    and are the primary driver of DB growth (1.15 M rows → ~300 MB).

    Also deactivates learning proposals whose change_type is no longer consumed
    by the current signal engine (tier_suppression, quality_threshold) or whose
    target is already covered by a hard-coded ban in DISABLED_MARKETS /
    DISABLED_LEAGUES.
    """
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        try:
            # Purge stale market snapshots (fixtures older than 30 days).
            result = await db.execute(text("""
                DELETE FROM market_snapshots
                WHERE fixture_id IN (
                    SELECT id FROM fixtures WHERE event_date < CURRENT_DATE - INTERVAL '30 days'
                )
            """))
            deleted_snaps = result.rowcount
            await db.commit()
            if deleted_snaps:
                logger.info("Cleanup: removed %d stale market_snapshots rows.", deleted_snaps)

        except Exception:
            logger.exception("Cleanup job failed — continuing normally")


async def _kickoff_alert_job() -> None:
    """Scheduler wrapper — sends pre-kickoff Telegram alerts every 30 min."""
    async with AsyncSessionLocal() as db:
        try:
            n = await push_kickoff_alerts(db)
            if n:
                logger.info("Kickoff alert job: pushed to %d channel(s)", n)
        except Exception:
            logger.exception("Kickoff alert job failed — continuing normally")



async def _daily_calibration_job() -> None:
    """
    Daily calibration audit — runs at 05:00 UTC every day.

    Computes Brier skill score, ECE, and per-market calibration gaps over the
    last 90 days of settled bets.  Saves a snapshot for trend tracking and logs
    a WARNING for every market that fails the health threshold (skill < +0.05).

    Also writes a market_suppression LearningProposal for any market whose
    brier_skill is below BRIER_SKILL_TARGET in BOTH the current snapshot AND the
    immediately prior saved snapshot (two consecutive windows), indicating
    sustained calibration failure rather than one-off noise.  Each proposal is
    validated through the in-process backtester before persisting.
    """
    from app.services.calibration import (
        compute_calibration_metrics, save_snapshot,
    )
    async with AsyncSessionLocal() as db:
        try:
            report = await compute_calibration_metrics(db, days=90)
            if report.signal_join_bets < 30:
                logger.info(
                    "Calibration: too few settled bets (%d) — skipping snapshot",
                    report.signal_join_bets,
                )
                return
            await save_snapshot(db, report)
            for line in report.summary_lines():
                logger.info(line)
            for mkt in report.flagged_markets:
                logger.warning(
                    "Calibration FLAGGED: %s -- brier_skill below target or gap > 7pp",
                    mkt,
                )

            # ── Refit isotonic calibration knots ─────────────────────────────
            # After audit, refresh CalibrationRecord rows so ensemble_service
            # picks up updated knots on the next prediction run.
            try:
                from app.services.calibration_service import run_calibration
                new_cal_records = await run_calibration(db)
                if new_cal_records:
                    logger.info(
                        "Calibration: refitted isotonic knots for %d market(s): %s",
                        len(new_cal_records),
                        ", ".join(r.market for r in new_cal_records),
                    )
                else:
                    logger.info("Calibration: no markets had enough samples for isotonic refit")
            except Exception:
                logger.exception("Isotonic calibration refit failed — continuing normally")

        except Exception:
            logger.exception("Calibration job failed")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        # 04:00 UTC — morning extras only: today refresh + settlement +
        #   morning Telegram ("Confirmed" if evening already ran, else full digest).
        # 19:00 UTC — evening extras only: tomorrow ingestion + signals (peak odds
        #   availability) + advisory + ACCA + "Tomorrow's Picks" Telegram digest.
        # 23:00 UTC — settlement-only: core ingest + settle + learning pipelines.
        for i, (hour, minute) in enumerate(settings.sync_times_list):
            _scheduler.add_job(
                sync_and_compute,
                CronTrigger(hour=hour, minute=minute),
                id=f"sync-{hour:02d}{minute:02d}",
                replace_existing=True,
                misfire_grace_time=300,
                kwargs={"morning_extras": i == 0, "evening_extras": i == 1},
            )
        # Pre-kickoff alert — runs every 60 min, 04:00–22:00 UTC (06:00–00:00 CAT).
        # Sends a compact Telegram message for High+Both signals kicking off
        # within 90 minutes that haven't already been alerted today.
        # No-op when TELEGRAM_BOT_TOKEN is not set.
        _scheduler.add_job(
            _kickoff_alert_job,
            CronTrigger(hour="4-22", minute="0"),
            id="kickoff-alerts",
            replace_existing=True,
            misfire_grace_time=120,
        )
        # Daily calibration audit — every day 05:00 UTC.
        # Computes Brier skill, ECE, per-market calibration gaps over the last 90 days.
        # Daily re-runs are cheap (90-day window) and catch model drift faster than weekly.
        # Writes a market_suppression LearningProposal when the same market fails
        # in two consecutive snapshots AND shows negative ROI (two-window guard).
        _scheduler.add_job(
            _daily_calibration_job,
            CronTrigger(hour=5, minute=0),
            id="daily-calibration",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        # Weekly housekeeping -- every Wednesday 02:00 UTC.
        # Purges market_snapshots for fixtures >30 days old and deactivates
        # stale learning proposals whose targets are already hard-banned.
        _scheduler.add_job(
            _cleanup_old_snapshots,
            CronTrigger(day_of_week="wed", hour=2, minute=0),
            id="weekly-cleanup",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "Scheduler configured: %d syncs "
            "(04:00=morning-confirm, 19:00=evening-tomorrow, 23:00=settle-only) "
            "+ kickoff alerts 04:00-22:00 UTC + daily calibration + weekly cleanup",
            len(settings.sync_times_list),
        )
    return _scheduler
