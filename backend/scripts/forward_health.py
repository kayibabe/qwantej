"""CLI wrapper for the forward-experiment health snapshot.

The checks themselves live in ``app.services.forward_health`` so the scheduled
operational monitor and this command cannot drift apart.

    python scripts/forward_health.py
    python scripts/forward_health.py --json

Exits non-zero when the snapshot reports a problem, so it is safe to use from
a shell loop or an external watchdog.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.database import AsyncSessionLocal, engine
from app.services.forward_health import forward_experiment_snapshot


def _print(payload: dict) -> None:
    print(f"checked_at: {payload['checked_at']}")
    print(f"paper tracking enabled: {payload['paper_rules_enabled']}")
    for rule in payload["paper_rules"]:
        print(
            f"{rule['rule']}: {rule['qualified']}/{rule['decisions']} qualified, "
            f"{rule['settled']} settled ({rule['wins']}W {rule['losses']}L), "
            f"tick age {rule['tick_age_minutes']} min"
        )
        for pick in rule["upcoming_qualified"]:
            due = "closing capture due" if pick["closing_capture_due"] else "not yet due"
            captured = pick.get("quote_captured_after_entry")
            captured_note = "" if captured is None else f", quote after entry: {captured}"
            print(
                f"  upcoming {pick['match_id']} {pick['market']} @ {pick['odds']} "
                f"in {pick['hours_to_kickoff']}h ({due}{captured_note})"
            )
        if rule["settled_without_valid_clv_since_fix"]:
            print(f"  missing valid CLV: {rule['settled_without_valid_clv_since_fix']}")
            causes = rule.get("missing_clv_causes") or {}
            print(
                f"    never quoted after entry (capture gap): "
                f"{len(causes.get('no_post_entry_quote') or [])} "
                f"{causes.get('no_post_entry_quote') or ''}".rstrip()
            )
            print(
                f"    quoted but no derived close (CLV defect): "
                f"{len(causes.get('quote_without_derived_close') or [])} "
                f"{causes.get('quote_without_derived_close') or ''}".rstrip()
            )
            if causes.get("unclassified"):
                print(f"    unclassified: {causes['unclassified']}")
        counts = rule.get("rejection_reasons") or {}
        if counts:
            compact = ", ".join(
                f"{reason} {count}" for reason, count in list(counts.items())[:4]
            )
            print(f"  rejected: {compact}")
    clv = payload["clv"]
    print(
        f"CLV: {clv['valid_rows']} valid / {clv['invalid_rows']} invalid, "
        f"mean {clv['mean_clv_fraction']}, beat-close {clv['beat_close_rate']}"
    )
    fair = payload["fair_probability"]
    print(
        f"fair probability: {fair['with_fair_probability']}/{fair['predictions_since_fix']} "
        f"new predictions ({fair['coverage_fraction']})"
    )
    last = payload["learning"].get("last_run")
    if last:
        print(
            f"learning: run {last['id']} {last['challenger']} {last['status']}, "
            f"{last['profiles_with_market_baseline']}/{last['profiles']} with market baseline, "
            f"{last['shadow_ready']} ready"
        )
    else:
        print("learning: no runs")
    print(f"next learning run (UTC): {payload['next_learning_run_utc']}")
    learning = payload["learning"]
    print(
        f"last weekly slot (UTC): {learning.get('last_weekly_slot')} "
        f"started: {learning.get('run_started_since_last_slot')}"
    )
    if payload["problems"]:
        print("PROBLEMS:")
        for problem in payload["problems"]:
            print(f"  - {problem['detail']}")
    else:
        print("no problems detected")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    engine.echo = False

    async with AsyncSessionLocal() as db:
        payload = await forward_experiment_snapshot(db)
    # Release pooled connections before the event loop closes, so a cron wrapper
    # does not see spurious "Event loop is closed" noise or a non-zero exit.
    await engine.dispose()

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print(payload)
    return 1 if payload["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
