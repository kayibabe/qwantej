"""Read-only forward-experiment health check.

Answers the operational questions that matter between now and the review date:

- Are the paper-rule ticks alive, and is each rule still capturing?
- Are qualified picks arriving, and do settled picks have valid CLV?
- Is the closing-quote refresh able to see recent picks before kickoff?
- Did the last shadow-learning run populate, and did the market gate run?
- Are new predictions getting a de-vigged probability?

It never calls the odds provider and never writes to the database.

Run inside the backend container:

    python scripts/forward_health.py
    python scripts/forward_health.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models import MarketLearningProfile, Match, ModelLearningRun, PaperRuleEvent, Prediction

# The date the strict CLV rule and the no-vig field went live. Earlier picks
# are not blamed for missing closing quotes.
CLV_FIX_DATE = date(2026, 11, 13)
CLOSING_HORIZON = timedelta(hours=3)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _next_sunday(now: datetime) -> datetime:
    days = (6 - now.weekday()) % 7
    candidate = (now + timedelta(days=days)).replace(hour=4, minute=30, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


async def _paper_health(db, now: datetime) -> list[dict]:
    rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("decision:policy%"))
    )).scalars().all()
    settlement_rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("settlement:policy%"))
    )).scalars().all()
    run_rows = (await db.execute(
        select(PaperRuleEvent).where(PaperRuleEvent.event_key.like("run:policy%"))
    )).scalars().all()

    match_ids = {
        int(row.payload.get("match_id"))
        for row in rows
        if row.payload.get("qualified") and str(row.payload.get("match_id", "")).isdigit()
    }
    matches = {}
    if match_ids:
        matches = {
            match.id: match
            for match in (await db.execute(select(Match).where(Match.id.in_(match_ids)))).scalars().all()
        }

    latest_settlement: dict[tuple[str, int], PaperRuleEvent] = {}
    for row in settlement_rows:
        rule = row.event_key.split(":", 2)[1]
        match_id = row.payload.get("match_id")
        key = (rule, int(match_id))
        current = latest_settlement.get(key)
        if current is None or (row.payload.get("revision") or 0) > (current.payload.get("revision") or 0):
            latest_settlement[key] = row

    latest_run: dict[str, datetime] = {}
    for row in run_rows:
        rule = row.event_key.split(":", 2)[1]
        at = _parse(row.payload.get("at"))
        if at and (rule not in latest_run or at > latest_run[rule]):
            latest_run[rule] = at

    rules = sorted({row.event_key.split(":", 2)[1] for row in rows})
    report = []
    for rule in rules:
        decisions = [row for row in rows if row.event_key.startswith(f"decision:{rule}:")]
        qualified = [row for row in decisions if row.payload.get("qualified")]
        settled = [event for (event_rule, _), event in latest_settlement.items() if event_rule == rule]
        settled_results = [event.payload.get("result") for event in settled]
        upcoming = []
        for row in qualified:
            payload = row.payload
            kickoff = _parse(payload.get("kickoff_at"))
            if kickoff and kickoff > now:
                age = now - _parse(payload.get("source_odds_at")) if payload.get("source_odds_at") else None
                upcoming.append({
                    "match_id": payload.get("match_id"),
                    "kickoff_at": kickoff.isoformat(),
                    "hours_to_kickoff": round((kickoff - now).total_seconds() / 3600, 2),
                    "market": payload.get("market"),
                    "odds": payload.get("odds"),
                    "closing_capture_due": kickoff <= now + CLOSING_HORIZON,
                    "entry_quote_age_hours": round(age.total_seconds() / 3600, 2) if age else None,
                })
        missing_clv = [
            event.payload.get("match_id")
            for event in settled
            if event.payload.get("result") in {"won", "lost"}
            and event.payload.get("clv_valid") is not True
            and (match := matches.get(int(event.payload.get("match_id"))))
            and match.kickoff_at
            and (match.kickoff_at.date() if match.kickoff_at.tzinfo else match.kickoff_at.date()) >= CLV_FIX_DATE
        ]
        last = latest_run.get(rule)
        report.append({
            "rule": rule,
            "decisions": len(decisions),
            "qualified": len(qualified),
            "settled": sum(1 for result in settled_results if result in {"won", "lost"}),
            "pending": sum(1 for result in settled_results if result == "pending"),
            "wins": settled_results.count("won"),
            "losses": settled_results.count("lost"),
            "last_tick_at": last.isoformat() if last else None,
            "tick_age_minutes": round((now - last).total_seconds() / 60, 1) if last else None,
            "upcoming_qualified": sorted(upcoming, key=lambda item: item["kickoff_at"])[:10],
            "settled_without_valid_clv_since_fix": sorted(missing_clv),
        })
    return report


async def _clv_health(db) -> dict:
    predictions = (await db.execute(
        select(Prediction).where(Prediction.closing_decimal_odds.is_not(None))
    )).scalars().all()
    valid, invalid = [], []
    for row in predictions:
        if row.closing_odds_at and row.source_odds_at and row.closing_odds_at > row.source_odds_at:
            valid.append(row)
        else:
            invalid.append(row)
    clv_values = [row.clv_percentage for row in valid if row.clv_percentage is not None]
    latest = max((row.closing_odds_at for row in valid if row.closing_odds_at), default=None)
    return {
        "valid_rows": len(valid),
        "invalid_rows": len(invalid),
        "mean_clv_fraction": round(sum(clv_values) / len(clv_values), 6) if clv_values else None,
        "beat_close_rate": (round(sum(1 for value in clv_values if value > 0) / len(clv_values), 4)
                            if clv_values else None),
        "latest_capture_at": latest.isoformat() if latest else None,
    }


async def _learning_health(db) -> dict:
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


async def _fair_probability_health(db) -> dict:
    cutoff = datetime.combine(CLV_FIX_DATE, datetime.min.time(), tzinfo=timezone.utc)
    rows = (await db.execute(
        select(Prediction.source_fair_probability).where(Prediction.created_at >= cutoff)
    )).scalars().all()
    return {
        "predictions_since_fix": len(rows),
        "with_fair_probability": sum(1 for value in rows if value is not None),
        "coverage_fraction": round(sum(1 for value in rows if value is not None) / len(rows), 4)
        if rows else None,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-stale-tick-minutes", type=float, default=15.0)
    args = parser.parse_args()
    engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        paper = await _paper_health(db, now)
        clv = await _clv_health(db)
        learning = await _learning_health(db)
        fair = await _fair_probability_health(db)

    next_run = _next_sunday(now)
    problems = []
    if clv["invalid_rows"] > 0:
        problems.append(f"{clv['invalid_rows']} invalid CLV rows")
    for rule in paper:
        age = rule["tick_age_minutes"]
        if age is not None and age > args.fail_on_stale_tick_minutes:
            problems.append(f"{rule['rule']} tick is {age:.1f} minutes old")
        if rule["settled_without_valid_clv_since_fix"]:
            problems.append(
                f"{rule['rule']} settled without valid CLV since fix: "
                f"{rule['settled_without_valid_clv_since_fix']}"
            )

    payload = {
        "checked_at": now.isoformat(),
        "paper_rules_enabled": settings.paper_rules_tracking_enabled,
        "paper_rules": paper,
        "clv": clv,
        "fair_probability": fair,
        "learning": learning,
        "next_learning_run_utc": next_run.isoformat(),
        "problems": problems,
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"checked_at: {payload['checked_at']}")
        print(f"paper tracking enabled: {payload['paper_rules_enabled']}")
        for rule in paper:
            print(
                f"{rule['rule']}: {rule['qualified']}/{rule['decisions']} qualified, "
                f"{rule['settled']} settled ({rule['wins']}W {rule['losses']}L), "
                f"tick age {rule['tick_age_minutes']} min"
            )
            for pick in rule["upcoming_qualified"]:
                due = "closing capture due" if pick["closing_capture_due"] else "not yet due"
                print(f"  upcoming {pick['match_id']} {pick['market']} @ {pick['odds']} "
                      f"in {pick['hours_to_kickoff']}h ({due})")
            if rule["settled_without_valid_clv_since_fix"]:
                print(f"  missing valid CLV: {rule['settled_without_valid_clv_since_fix']}")
        print(f"CLV: {clv['valid_rows']} valid / {clv['invalid_rows']} invalid, "
              f"mean {clv['mean_clv_fraction']}, beat-close {clv['beat_close_rate']}")
        print(f"fair probability: {fair['with_fair_probability']}/{fair['predictions_since_fix']} "
              f"new predictions ({fair['coverage_fraction']})")
        last = learning.get("last_run")
        if last:
            print(f"learning: run {last['id']} {last['challenger']} {last['status']}, "
                  f"{last['profiles_with_market_baseline']}/{last['profiles']} with market baseline, "
                  f"{last['shadow_ready']} ready")
        else:
            print("learning: no runs")
        print(f"next learning run (UTC): {payload['next_learning_run_utc']}")
        if problems:
            print("PROBLEMS:")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("no problems detected")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
