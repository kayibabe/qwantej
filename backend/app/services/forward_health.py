"""Read-only health checks for the frozen forward paper experiments.

Both the CLI (``scripts/forward_health.py``) and the scheduled operational
monitor use this module, so "healthy" has exactly one definition. It never
calls an odds provider and never writes; the monitor turns the returned
problems into deduplicated automation alerts.

The checks answer the questions that decide whether the forward sample is
trustworthy, not whether it is profitable:

- Are the paper-rule ticks alive, and is each rule still capturing?
- Are qualified picks arriving, and do settled picks have valid CLV?
- Will an imminent pick actually get a closing quote before kickoff?
- Did the last shadow-learning run populate, and did the market gate run?
- Are new predictions getting a de-vigged probability?
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    MarketLearningProfile,
    Match,
    ModelLearningRun,
    OddsSnapshot,
    PaperRuleEvent,
    Prediction,
)
from app.services.clv import CLV_INVALID, CLV_UNMEASURED, valid_clv_condition

# The date the strict CLV rule and the no-vig field went live. Earlier picks
# are not blamed for missing closing quotes.
CLV_FIX_DATE = date(2026, 11, 13)
CLOSING_HORIZON = timedelta(hours=3)
# A pick this close to kickoff should already have a quote newer than its entry
# quote. Checking before the match catches a broken capture path the same day
# instead of after settlement.
CAPTURE_DEADLINE = timedelta(minutes=30)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def next_learning_run(now: datetime) -> datetime:
    days = (6 - now.weekday()) % 7
    candidate = (now + timedelta(days=days)).replace(
        hour=4, minute=30, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


_WEEKDAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}


def last_learning_slot(now: datetime) -> datetime:
    """The most recent scheduled weekly learning slot, in UTC.

    ``next_learning_run`` always returns a future date, which hides a slot that
    silently passed while the scheduler was down: the answer looks normal next
    to a stale run. This computes the slot that should already have fired so a
    missed week is detectable.
    """
    weekday = _WEEKDAYS.get(str(settings.learning_shadow_cron_day).strip().lower(), 6)
    days_back = (now.weekday() - weekday) % 7
    slot = (now - timedelta(days=days_back)).replace(
        hour=settings.learning_shadow_cron_hour,
        minute=settings.learning_shadow_cron_minute,
        second=0,
        microsecond=0,
    )
    if slot > now:
        slot -= timedelta(days=7)
    return slot


def _problem(key: str, title: str, detail: str, **context) -> dict:
    return {"key": key, "title": title, "detail": detail, "context": context}


# A settled pick with no closing line has two very different causes, and only
# one of them is a bug in this codebase:
#
# - no_post_entry_quote: the capture path never observed a second price at all.
#   That is lost uptime, quota exhaustion or a dead worker, not a fault in the
#   pick, and no amount of CLV code would have produced a close.
# - quote_without_derived_close: a post-entry, pre-kickoff quote was stored but
#   no CLV was derived from it. That is a real defect and must be fixed.
#
# Both still make the sample incomplete, so both keep the alert.
def classify_missing_clv(
    picks: list[tuple[int, str, str, datetime | None]],
    later_quotes: set[tuple[int, str, str]],
) -> dict[str, list[int]]:
    """Split unmeasured picks by whether a usable quote ever existed."""
    capture_gap: set[int] = set()
    derive_gap: set[int] = set()
    unclassified: set[int] = set()
    for match_id, market, selection, entry_at in picks:
        if not market or not selection or entry_at is None:
            unclassified.add(match_id)
        elif (match_id, market, selection) in later_quotes:
            derive_gap.add(match_id)
        else:
            capture_gap.add(match_id)
    return {
        "no_post_entry_quote": sorted(capture_gap),
        "quote_without_derived_close": sorted(derive_gap),
        "unclassified": sorted(unclassified),
    }


async def post_entry_quotes(
    db: AsyncSession, picks: list[tuple[int, str, str, datetime | None]]
) -> set[tuple[int, str, str]]:
    """Which picks got an odds snapshot later than entry and before kickoff.

    One grouped query for the whole rule; the snapshot table is large and the
    monitor runs every fifteen minutes.
    """
    keys = [
        (match_id, market, selection)
        for match_id, market, selection, entry_at in picks
        if market and selection and entry_at is not None
    ]
    if not keys:
        return set()
    latest_pre_kickoff = {
        (match_id, market, selection): captured_at
        for match_id, market, selection, captured_at in (await db.execute(
            select(
                OddsSnapshot.match_id,
                OddsSnapshot.market,
                OddsSnapshot.selection,
                func.max(OddsSnapshot.captured_at).filter(
                    OddsSnapshot.captured_at <= Match.kickoff_at
                ),
            )
            .select_from(OddsSnapshot)
            .join(Match, Match.id == OddsSnapshot.match_id)
            .where(tuple_(
                OddsSnapshot.match_id,
                OddsSnapshot.market,
                OddsSnapshot.selection,
            ).in_(keys))
            .group_by(
                OddsSnapshot.match_id, OddsSnapshot.market, OddsSnapshot.selection
            )
        )).all()
    }
    later: set[tuple[int, str, str]] = set()
    for match_id, market, selection, entry_at in picks:
        captured_at = latest_pre_kickoff.get((match_id, market, selection))
        if captured_at is None:
            continue
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        if entry_at is not None and captured_at > entry_at:
            later.add((match_id, market, selection))
    return later


async def _paper_health(db: AsyncSession, now: datetime) -> tuple[list[dict], list[dict]]:
    rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("decision:policy%"))
    )).scalars().all()
    settlement_rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("settlement:policy%"))
    )).scalars().all()
    run_rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("run:policy%"))
    )).scalars().all()

    qualified_ids = {
        int(row.payload.get("match_id"))
        for row in rows
        if row.payload.get("qualified") and str(row.payload.get("match_id", "")).isdigit()
    }
    matches = {}
    if qualified_ids:
        matches = {
            match.id: match
            for match in (await db.execute(
                select(Match).where(Match.id.in_(qualified_ids))
            )).scalars().all()
        }

    latest_settlement: dict[tuple[str, int], PaperRuleEvent] = {}
    for row in settlement_rows:
        rule = row.event_key.split(":", 2)[1]
        match_id = row.payload.get("match_id")
        if not str(match_id).isdigit():
            continue
        key = (rule, int(match_id))
        current = latest_settlement.get(key)
        if current is None or (row.payload.get("revision") or 0) > (current.payload.get("revision") or 0):
            latest_settlement[key] = row

    latest_run: dict[str, datetime] = {}
    for row in run_rows:
        rule = row.event_key.split(":", 2)[1]
        at = parse_timestamp(row.payload.get("at"))
        if at and (rule not in latest_run or at > latest_run[rule]):
            latest_run[rule] = at

    # One snapshot query covers every imminent pick, instead of one per pick.
    imminent_match_ids = set()
    rules = sorted({row.event_key.split(":", 2)[1] for row in rows})
    for row in rows:
        if not row.payload.get("qualified"):
            continue
        kickoff = parse_timestamp(row.payload.get("kickoff_at"))
        if kickoff and now < kickoff <= now + CAPTURE_DEADLINE:
            match_id = row.payload.get("match_id")
            if str(match_id).isdigit():
                imminent_match_ids.add(int(match_id))
    latest_snapshot: dict[int, datetime] = {}
    if imminent_match_ids:
        latest_snapshot = {
            match_id: captured_at
            for match_id, captured_at in (await db.execute(
                select(OddsSnapshot.match_id, func.max(OddsSnapshot.captured_at))
                .where(OddsSnapshot.match_id.in_(imminent_match_ids))
                .group_by(OddsSnapshot.match_id)
            )).all()
        }

    report, problems = [], []
    for rule in rules:
        decisions = [row for row in rows if row.event_key.startswith(f"decision:{rule}:")]
        reason_counts: dict[str, int] = {}
        for row in decisions:
            for reason in (row.payload.get("reasons") or []):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        qualified = [row for row in decisions if row.payload.get("qualified")]
        decision_by_match: dict[int, dict] = {}
        for row in decisions:
            decision_match_id = row.payload.get("match_id")
            if str(decision_match_id).isdigit():
                decision_by_match[int(decision_match_id)] = row.payload
        settled = [
            event for (event_rule, _), event in latest_settlement.items()
            if event_rule == rule
        ]
        settled_results = [event.payload.get("result") for event in settled]
        upcoming = []
        for row in qualified:
            payload = row.payload
            kickoff = parse_timestamp(payload.get("kickoff_at"))
            if not kickoff or kickoff <= now:
                continue
            age = None
            source_odds_at = parse_timestamp(payload.get("source_odds_at"))
            if source_odds_at:
                age = now - source_odds_at
            due = kickoff <= now + CLOSING_HORIZON
            captured_after_entry = None
            if source_odds_at and str(payload.get("match_id", "")).isdigit():
                captured_at = latest_snapshot.get(int(payload.get("match_id")))
                if captured_at is not None:
                    if captured_at.tzinfo is None:
                        captured_at = captured_at.replace(tzinfo=timezone.utc)
                    captured_after_entry = captured_at > source_odds_at
            upcoming.append({
                "match_id": payload.get("match_id"),
                "kickoff_at": kickoff.isoformat(),
                "hours_to_kickoff": round((kickoff - now).total_seconds() / 3600, 2),
                "market": payload.get("market"),
                "odds": payload.get("odds"),
                "closing_capture_due": due,
                "quote_captured_after_entry": captured_after_entry,
                "entry_quote_age_hours": round(age.total_seconds() / 3600, 2) if age else None,
            })
            if (
                kickoff <= now + CAPTURE_DEADLINE
                and source_odds_at is not None
                and captured_after_entry is False
            ):
                problems.append(_problem(
                    f"capture_missing:{rule}",
                    "Imminent paper pick has no closing quote",
                    f"{rule} pick {payload.get('match_id')} ({payload.get('market')}) "
                    f"kicks off in {round((kickoff - now).total_seconds() / 60)} min "
                    "with no quote newer than its entry quote",
                    match_id=payload.get("match_id"),
                    market=payload.get("market"),
                ))

        missing_clv: list[int] = []
        measured_unmeasured: set[int] = set()
        measured_invalid: set[int] = set()
        to_classify: list[tuple[int, str, str, datetime | None]] = []
        for event in settled:
            if event.payload.get("result") not in {"won", "lost"}:
                continue
            if event.payload.get("clv_valid") is True:
                continue
            match_id = int(event.payload.get("match_id") or 0)
            match = matches.get(match_id)
            if not (
                match and match.kickoff_at and match.kickoff_at.date() >= CLV_FIX_DATE
            ):
                continue
            missing_clv.append(match_id)
            # The settlement ledger records the cause when it settles, so this
            # does not have to re-derive it. Older rows predate that field and
            # fall back to inspecting the snapshot table.
            label = event.payload.get("clv_measurement")
            if label == CLV_UNMEASURED:
                measured_unmeasured.add(match_id)
                continue
            if label == CLV_INVALID:
                measured_invalid.add(match_id)
                continue
            decision = decision_by_match.get(match_id) or {}
            to_classify.append((
                match_id,
                decision.get("market") or "",
                decision.get("selection") or decision.get("market") or "",
                parse_timestamp(event.payload.get("entry_odds_at")),
            ))
        fallback = classify_missing_clv(
            to_classify, await post_entry_quotes(db, to_classify)
        )
        causes = {
            "no_post_entry_quote": sorted(
                measured_unmeasured | set(fallback["no_post_entry_quote"])
            ),
            "quote_without_derived_close": sorted(
                measured_invalid | set(fallback["quote_without_derived_close"])
            ),
            "unclassified": fallback["unclassified"],
        }
        if missing_clv:
            problems.append(_problem(
                f"missing_clv:{rule}",
                "Settled paper pick has no valid closing line",
                f"{rule} settled without valid CLV after the fix: "
                f"{len(causes['no_post_entry_quote'])} never got a quote after entry "
                f"(capture gap, not a CLV defect), "
                f"{len(causes['quote_without_derived_close'])} got one but no close "
                f"(CLV defect), {len(causes['unclassified'])} unclassified. "
                f"Picks: {sorted(missing_clv)}",
                match_ids=sorted(missing_clv),
                **causes,
            ))

        last = latest_run.get(rule)
        age_minutes = round((now - last).total_seconds() / 60, 1) if last else None
        if age_minutes is not None and age_minutes > 15:
            problems.append(_problem(
                f"tick_stale:{rule}",
                "Paper rule tick is stale",
                f"{rule} last tick was {age_minutes} minutes ago",
                tick_age_minutes=age_minutes,
            ))

        report.append({
            "rule": rule,
            "decisions": len(decisions),
            "qualified": len(qualified),
            "settled": sum(1 for result in settled_results if result in {"won", "lost"}),
            "pending": sum(1 for result in settled_results if result == "pending"),
            "wins": settled_results.count("won"),
            "losses": settled_results.count("lost"),
            "last_tick_at": last.isoformat() if last else None,
            "tick_age_minutes": age_minutes,
            "rejection_reasons": dict(sorted(
                reason_counts.items(), key=lambda item: (-item[1], item[0])
            )),
            "upcoming_qualified": sorted(upcoming, key=lambda item: item["kickoff_at"])[:10],
            "settled_without_valid_clv_since_fix": sorted(missing_clv),
            "missing_clv_causes": causes,
        })
    return report, problems


async def _clv_health(db: AsyncSession) -> dict:
    """Aggregate in SQL; the table is too large to load every monitor tick."""
    valid_condition = valid_clv_condition(Match)
    total, valid, mean_clv, beat_close, latest = (await db.execute(
        select(
            func.count().filter(Prediction.closing_decimal_odds.is_not(None)),
            func.count().filter(valid_condition),
            func.avg(Prediction.clv_percentage).filter(valid_condition),
            func.avg(case((Prediction.clv_percentage > 0, 1), else_=0)).filter(valid_condition),
            func.max(Prediction.closing_odds_at).filter(valid_condition),
        )
        .select_from(Prediction)
        .outerjoin(Match, Match.id == Prediction.match_id)
    )).one()
    total = int(total or 0)
    valid = int(valid or 0)
    return {
        "valid_rows": valid,
        "invalid_rows": total - valid,
        "mean_clv_fraction": round(float(mean_clv), 6) if mean_clv is not None else None,
        "beat_close_rate": round(float(beat_close), 4) if beat_close is not None else None,
        "latest_capture_at": latest.isoformat() if latest else None,
    }


async def _learning_health(db: AsyncSession, now: datetime) -> dict:
    run = (await db.execute(
        select(ModelLearningRun).order_by(ModelLearningRun.id.desc()).limit(1)
    )).scalar_one_or_none()

    # A weekly job that never fired leaves no row at all, so the absence has to
    # be measured against the schedule, not against the last run's age.
    slot = last_learning_slot(now)
    # The trigger only queues the work; give it an hour before calling it lost.
    slot_is_due = now >= slot + timedelta(hours=1)
    started_since = None
    if settings.learning_shadow_schedule_enabled and slot_is_due:
        started_since = bool(await db.scalar(
            select(func.count())
            .select_from(ModelLearningRun)
            .where(ModelLearningRun.created_at >= slot)
        ))

    if run is None:
        return {
            "last_run": None,
            "last_weekly_slot": slot.isoformat(),
            "run_started_since_last_slot": started_since,
        }
    profiles = (await db.execute(
        select(MarketLearningProfile).where(MarketLearningProfile.learning_run_id == run.id)
    )).scalars().all()
    with_baseline = [p for p in profiles if (p.validation_metrics or {}).get("market_baseline")]
    return {
        "last_run": {
            "id": run.id,
            "challenger": run.challenger_version,
            "status": str(run.status),
            "train": [run.train_start.isoformat(), run.train_end.isoformat()],
            "validation": [run.validation_start.isoformat(), run.validation_end.isoformat()],
            "summary": run.summary,
            "profiles": len(profiles),
            "profiles_with_market_baseline": len(with_baseline),
            "shadow_ready": sum(1 for p in profiles if p.status == "shadow_ready"),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        },
        "last_weekly_slot": slot.isoformat(),
        "run_started_since_last_slot": started_since,
    }


async def _fair_probability_health(db: AsyncSession) -> dict:
    cutoff = datetime.combine(CLV_FIX_DATE, datetime.min.time(), tzinfo=timezone.utc)
    total, covered = (await db.execute(
        select(
            func.count(),
            func.count().filter(Prediction.source_fair_probability.is_not(None)),
        ).where(Prediction.created_at >= cutoff)
    )).one()
    total = int(total or 0)
    covered = int(covered or 0)
    return {
        "predictions_since_fix": total,
        "with_fair_probability": covered,
        "coverage_fraction": round(covered / total, 4) if total else None,
    }


async def forward_experiment_snapshot(
    db: AsyncSession, now: datetime | None = None
) -> dict:
    """Return the full read-only snapshot, including structured problems."""
    now = now or datetime.now(timezone.utc)
    paper, problems = await _paper_health(db, now)
    clv = await _clv_health(db)
    learning = await _learning_health(db, now)
    fair = await _fair_probability_health(db)

    if learning.get("run_started_since_last_slot") is False:
        problems.append(_problem(
            "learning_slot_missed",
            "Weekly shadow learning run never started",
            f"No learning run started since the {learning['last_weekly_slot']} "
            "weekly slot. The scheduler was not running when it was due, so the "
            f"week's evidence was lost; the next slot is {next_learning_run(now).isoformat()}.",
            last_weekly_slot=learning["last_weekly_slot"],
        ))

    if clv["invalid_rows"] > 0:
        problems.append(_problem(
            "clv_invalid_rows",
            "Closing lines fail the strict CLV rule",
            f"{clv['invalid_rows']} rows have closing odds that are not a genuine "
            "post-entry pre-kickoff quote",
            invalid_rows=clv["invalid_rows"],
        ))

    return {
        "checked_at": now.isoformat(),
        "paper_rules_enabled": settings.paper_rules_tracking_enabled,
        "paper_rules": paper,
        "clv": clv,
        "fair_probability": fair,
        "learning": learning,
        "next_learning_run_utc": next_learning_run(now).isoformat(),
        "problems": problems,
    }
