"""Compare ticket-shape policies on the same settled history.

Rebuilds each day's Conservative/Balanced tickets with the production
AccumulatorBuilder from the local DB, then settles them, under several
odds-band policies:

  current    - the shipped MARKET_TICKET_SPECS (SAFE ~2.0, BALANCED ~3.5)
  rebanded   - lower odds bands, so each ticket is likelier but pays less
  safe_only  - ship only the Conservative tier (one ticket a day)
  safe_rebanded - one re-banded Conservative ticket a day

Diagnosis only: nothing is written and no production setting is changed.

Usage (inside the backend container):
  python scripts/policy_streak_sweep.py
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from app.config import settings  # noqa: E402
from app.models import TicketType  # noqa: E402
from app.services.accumulator_builder import TicketSpec  # noqa: E402
import app.services.accumulator_builder as ab  # noqa: E402

from honest_pricing_backtest import _Replay as _OldReplay  # noqa: E402
from honest_pricing_backtest import build_days, load_local  # noqa: E402


class _Replay(_OldReplay):
    """Replay the builder on one day's legs, ignoring wall-clock gates."""

    async def _load_qualified_legs(self, target_date, model_run_id, pricing="model"):
        if pricing == "market":
            return [
                ab.market_priced(leg) if leg.fair_probability is not None else leg
                for leg in self._legs
                if leg.best_odds >= ab._MIN_LEG_ODDS
            ]
        return [
            leg for leg in self._legs
            if leg.edge is not None and leg.best_odds >= ab._MIN_LEG_ODDS
        ]


def _specs_current():
    return ab.MARKET_TICKET_SPECS


def _specs_rebanded():
    return (
        TicketSpec(
            TicketType.SAFE, "Conservative", 2, 2, 1.55, 1.80,
            0.0, 0.0, 1, 0.50, 0.05,
            pricing="market", min_leg_odds=1.24, max_leg_odds=1.36,
        ),
        TicketSpec(
            TicketType.BALANCED, "Balanced", 3, 3, 3.00, 3.60,
            0.0, 0.0, 1, 0.26, 0.10,
            pricing="market", min_leg_odds=1.40, max_leg_odds=1.55,
        ),
    )


POLICIES = {
    "current": (_specs_current, (TicketType.SAFE, TicketType.BALANCED)),
    "rebanded": (_specs_rebanded, (TicketType.SAFE, TicketType.BALANCED)),
    "safe_only": (_specs_current, (TicketType.SAFE,)),
    "safe_rebanded": (_specs_rebanded, (TicketType.SAFE,)),
}


def _longest_run(flags: list[bool]) -> int:
    best = run = 0
    for won in flags:
        run = 0 if won else run + 1
        best = max(best, run)
    return best


def _max_drawdown(pnls: list[float]) -> float:
    curve = peak = dd = 0.0
    for pnl in pnls:
        curve += pnl
        peak = max(peak, curve)
        dd = max(dd, peak - curve)
    return dd


def run_policy(days, specs_fn, tiers):
    tickets = []
    with patch.object(ab, "_odds_age_hours", lambda v: 0.0), \
            patch.object(ab, "MARKET_TICKET_SPECS", specs_fn()), \
            patch.object(ab, "PUBLIC_TICKET_TYPES", tiers), \
            patch.object(settings, "leg_probability_source", "market"):
        for day in sorted(days):
            legs, results = days[day]
            built = asyncio.run(_Replay(legs).build(datetime.fromisoformat(day).date()))
            for tier, ticket in (("SAFE", built.conservative), ("BALANCED", built.balanced)):
                if ticket is None or tier.lower() not in {t.value for t in tiers}:
                    continue
                won = all(results[leg.prediction_id] for leg in ticket.legs)
                tickets.append({
                    "date": day,
                    "tier": tier,
                    "legs": len(ticket.legs),
                    "odds": ticket.combined_odds,
                    "p": ticket.adjusted_probability,
                    "ev": ticket.expected_value,
                    "won": won,
                    "pnl": (ticket.combined_odds - 1.0) if won else -1.0,
                })
    return tickets


def summarise(name, tickets):
    if not tickets:
        print(f"   {name:14s} no tickets")
        return
    n = len(tickets)
    wins = sum(t["won"] for t in tickets)
    pnl = sum(t["pnl"] for t in tickets)
    ev = sum(t["ev"] for t in tickets)
    days = sorted({t["date"] for t in tickets})
    by_day = defaultdict(list)
    for t in tickets:
        by_day[t["date"]].append(t["won"])
    day_lost = [not any(w) for _, w in sorted(by_day.items())]
    day_won = [not lost for lost in day_lost]
    nov = [t for t in tickets if t["date"] >= "2026-11-01"]
    print(
        f"   {name:14s} n={n:3d} over {len(days):2d} days | hit {100*wins/n:5.1f}% | "
        f"P&L {pnl:+6.2f}u ({100*pnl/n:+6.1f}%) | EV-sum {ev:+6.2f}u | "
        f"maxDD {_max_drawdown([t['pnl'] for t in tickets]):5.2f}u | "
        f"loss run {_longest_run([t['won'] for t in tickets]):2d} | "
        f"losing days {_longest_run(day_won):2d} | "
        f"avg odds {sum(t['odds'] for t in tickets)/n:4.2f} | "
        f"avg p {sum(t['p'] for t in tickets)/n:4.3f}"
    )
    if nov:
        nw = sum(t["won"] for t in nov)
        print(
            f"   {'':14s} Nov 1-6: {len(nov)} tickets, {nw} won, "
            f"P&L {sum(t['pnl'] for t in nov):+.2f}u, "
            f"longest loss run {_longest_run([t['won'] for t in nov])}"
        )


def main():
    preds, matches, runs = asyncio.run(load_local())
    days = build_days(preds, matches, runs)
    print(f"days with settled legs: {len(days)}  ({min(days)} .. {max(days)})")
    print("\nPolicy comparison (production builder replayed on the same history)")
    for name, (specs_fn, tiers) in POLICIES.items():
        summarise(name, run_policy(days, specs_fn, tiers))


if __name__ == "__main__":
    main()
