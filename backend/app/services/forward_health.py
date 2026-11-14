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

from sqlalchemy import and_, case, func, select
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


def _problem(key: str, title: str, detail: str, **context) -> dict:
    return {"key": key, "title": title, "detail": detail, "context": context}


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
        qualified = [row for row in decisions if row.payload.get("qualified")]
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

        missing_clv = []
        for event in settled:
            if event.payload.get("result") not in {"won", "lost"}:
                continue
            if event.payload.get("clv_valid") is True:
                continue
            match = matches.get(int(event.payload.get("match_id") or 0))
            if match and match.kickoff_at and match.kickoff_at.date() >= CLV_FIX_DATE:
                missing_clv.append(event.payload.get("match_id"))
        if missing_clv:
            problems.append(_problem(
                f"missing_clv:{rule}",
                "Settled paper pick has no valid closing line",
                f"{rule} settled without valid CLV after the fix: {sorted(missing_clv)}",
                match_ids=sorted(missing_clv),
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
            "upcoming_qualified": sorted(upcoming, key=lambda item: item["kickoff_at"])[:10],
            "settled_without_valid_clv_since_fix": sorted(missing_clv),
        })
    return report, problems


async def _clv_health(db: AsyncSession) -> dict:
    """Aggregate in SQL; the table is too large to load every monitor tick."""
    valid_condition = and_(
        Prediction.closing_decimal_odds.is_not(None),
        Prediction.source_odds_at.is_not(None),
        Prediction.closing_odds_at.is_not(None),
        Prediction.closing_odds_at > Prediction.source_odds_at,
    )
    total, valid, mean_clv, beat_close, latest = (await db.execute(
        select(
            func.count().filter(Prediction.closing_decimal_odds.is_not(None)),
            func.count().filter(valid_condition),
            func.avg(Prediction.clv_percentage).filter(valid_condition),
            func.avg(case((Prediction.clv_percentage > 0, 1), else_=0)).filter(valid_condition),
            func.max(Prediction.closing_odds_at).filter(valid_condition),
        )
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


async def _learning_health(db: AsyncSession) -> dict:
    run = (await db.execute(
        select(ModelLearningRun).order_by(ModelLearningRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return {"last_run": None}
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
        }
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
    learning = await _learning_health(db)
    fair = await _fair_probability_health(db)

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
