"""Audit the Analytics 'Accumulator performance' summary for selection bias.

The UI builds each date's 'ticket' from every pick whose market (or
market x model) already cleared an all-time ROI threshold (10% for All
Unique, 5% for Published), then re-summarises the same period. This script
reproduces the table and then repeats it with:

  * no filter (the honest baseline), and
  * a walk-forward filter (thresholds computed only from strictly earlier
    dates), which removes the look-ahead.

Usage (inside the backend container):
  python scripts/accumulator_summary_audit.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.recommendation_ledger import (  # noqa: E402
    recommendation_pick_ledger,
    walk_forward_accumulator_selections,
)

WINDOW_START = "2026-10-01"
WINDOW_END = "2026-11-06"


def metrics(rows):
    priced = [r for r in rows if r.get("odds") and r["odds"] > 1]
    won = sum(r["result"] == "won" for r in priced)
    lost = sum(r["result"] == "lost" for r in priced)
    returned = sum(r["odds"] for r in priced if r["result"] == "won")
    pnl = returned - len(priced)
    return {
        "n": len(rows),
        "priced": len(priced),
        "won": won,
        "lost": lost,
        "roi": (pnl / len(priced)) if priced else None,
        "pnl": pnl,
    }


def summarise(rows, through=WINDOW_END):
    """Replicates the frontend's summarizeAccumulators()."""
    by_date = defaultdict(list)
    for row in rows:
        if WINDOW_START <= row["target_date"] <= through:
            by_date[row["target_date"]].append(row)
    settled = won = lost = pending = 0
    pnl = 0.0
    priced_settled = 0
    legs = []
    for picks in by_date.values():
        has_loss = any(r["result"] == "lost" for r in picks)
        has_pending = any(r["result"] == "pending" for r in picks)
        all_void = all(r["result"] == "void" for r in picks)
        status = "lost" if has_loss else "pending" if has_pending else "void" if all_void else "won"
        if status == "pending":
            pending += 1
            continue
        settled += 1
        won += status == "won"
        lost += status == "lost"
        if not all(r["result"] == "void" or (r.get("odds") and r["odds"] > 1) for r in picks):
            continue
        odds = 1.0
        for r in picks:
            if r["result"] != "void":
                odds *= r["odds"]
        priced_settled += 1
        legs.append(len([r for r in picks if r["result"] != "void"]))
        pnl += (odds - 1.0) if status == "won" else (-1.0 if status == "lost" else 0.0)
    return {
        "settled": settled, "won": won, "lost": lost, "pending": pending,
        "hit": won / settled if settled else None,
        "pnl": pnl, "roi": pnl / priced_settled if priced_settled else None,
        "legs": legs,
    }


def show(label, s):
    if not s["settled"]:
        print(f"   {label:38s} no settled tickets")
        return
    legs = s["legs"]
    print(
        f"   {label:38s} settled {s['settled']:3d} | {s['won']:2d}W {s['lost']:2d}L "
        f"{s['pending']:2d}P | hit {100*s['hit']:5.1f}% | P&L {s['pnl']:+7.2f} | "
        f"ROI {100*s['roi']:+6.1f}% | legs/ticket {sum(legs)/len(legs):4.1f} "
        f"(max {max(legs)})"
    )


async def main():
    async with AsyncSessionLocal() as db:
        snap = await recommendation_pick_ledger(db, stake=1.0, limit=5000)
    rows = snap["rows"]
    print(f"ledger rows: {len(rows)}  ({min(r['target_date'] for r in rows)} .. {max(r['target_date'] for r in rows)})")

    # --- reproduce the shipped table -------------------------------------
    all_markets = {
        c["market"] for c in snap["roi_combinations"]
        if c["source"] == "all" and c["unique_picks"] >= 5 and c["roi"] is not None and c["roi"] >= 0.10
    }
    pub_combos = {
        (c["market"], c["model_version"]) for c in snap["roi_combinations"]
        if c["source"] == "published" and c["unique_picks"] >= 5 and c["roi"] is not None and c["roi"] >= 0.05
    }
    all_unique_rows = [r for r in rows if r["market"] in all_markets]
    published_rows = [
        r for r in rows
        if "published" in r["sources"] and any((r["market"], v) in pub_combos for v in r["model_versions"])
    ]

    print("\n1) Reproduced as shipped (all-time thresholds -> same window)")
    show("All Unique / 10% rule", summarise(all_unique_rows))
    show("Published simulation / 5% rule", summarise(published_rows))

    print(f"\n   qualifying All Unique markets ({len(all_markets)}): {sorted(all_markets)}")
    print(f"   qualifying Published combos ({len(pub_combos)}): {sorted(pub_combos)}")

    # --- what the same window looks like without the filter --------------
    print("\n2) Same window, no ROI filter")
    show("All ledger rows", summarise(rows))
    show("Published rows only", summarise([r for r in rows if "published" in r["sources"]]))

    # --- walk-forward: thresholds from strictly earlier dates ------------
    print("\n3) Walk-forward thresholds (no look-ahead, production helper)")
    selection = walk_forward_accumulator_selections(rows, stake=1.0)
    show("All Unique / 10% walk-forward", summarise(selection["all_unique"]["rows"]))
    show("Published / 5% walk-forward", summarise(selection["published"]["rows"]))
    print(f"   qualifying All Unique markets: {selection['all_unique']['qualifying_markets']}")
    print(f"   qualifying Published combos: {selection['published']['qualifying_combinations']}")

    # --- how much of each set is inside the window? ----------------------
    print("\n4) In-sample share of the qualifying sets")
    for label, subset in (("All Unique", all_unique_rows), ("Published sim", published_rows)):
        inside = [r for r in subset if WINDOW_START <= r["target_date"] <= WINDOW_END]
        print(f"   {label:14s} {len(inside):3d} of {len(subset):3d} picks fall inside Oct 1 - Nov 6")

    # --- all-time metrics of the qualifying markets ----------------------
    print("\n5) All-time ledger metrics for each qualifying All Unique market")
    for m in sorted(all_markets):
        rs = [r for r in rows if r["market"] == m]
        mt = metrics(rs)
        inside = [r for r in rs if WINDOW_START <= r["target_date"] <= WINDOW_END]
        mi = metrics(inside)
        print(
            f"   {m:18s} all-time n={mt['n']:4d} roi={100*mt['roi']:+6.1f}% | "
            f"in-window n={mi['n']:3d} roi={(100*mi['roi'] if mi['roi'] is not None else float('nan')):+6.1f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())
