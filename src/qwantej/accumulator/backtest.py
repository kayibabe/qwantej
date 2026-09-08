"""Walk-forward accumulator backtest (framework §4, Phase 8).

Simulates the accumulator engine over a sequence of historical rounds and
computes hit-rate, ROI, and per-product drawdown — without any live data or
real money.  Uses the same build_accumulator_decision path as production so
the backtest covers the full engine stack, not a simplified proxy.

Leakage rules enforced unconditionally:
1. Any candidate whose `quote_timestamp` is strictly after `as_of` is rejected
   from that round (price-freshness leakage).
2. Any round whose `outcome_observed_at` is at or before `as_of` is skipped
   for outcome evaluation — the result was known at decision time (outcome
   leakage).  The engine still runs so the ticket choice is recorded; only the
   win/loss credit is withheld.
Both classes of violation are counted in `leakage_rows_rejected`.

Output:
- `AccumulatorBacktestReport` with per-product statistics and a flat-stake
  baseline (1 unit on every selected ticket, at the ticket's combined odds).
  The flat-stake baseline isolates ticket selection quality from staking
  decisions; a real de-vigged market baseline requires closing-odds data and
  will be added once outcome settlement is wired.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from qwantej.accumulator.decision import (
    AccumulatorDecision,
    build_accumulator_decision,
)
from qwantej.accumulator.policy import AccumulatorPolicy
from qwantej.accumulator.types import QualifiedSelection
from qwantej.bankroll.state import (
    DEFAULT_RISK_POLICY,
    OperatingState,
    ProductTier,
    RiskPolicy,
)


@dataclass(frozen=True)
class BacktestRound:
    """One decision point in the walk-forward backtest.

    `outcome` maps fixture_id → 1 (leg won) or 0 (leg lost / push).
    A ticket wins iff every leg's fixture_id is in `outcome` with value 1.

    `outcome_observed_at` must be strictly after `as_of`; rounds where
    the outcome was already known at decision time are counted as leakage
    and excluded from win/loss statistics (the engine still runs).
    """

    as_of: datetime
    candidates: list[QualifiedSelection]
    outcome: dict[str, int]
    outcome_observed_at: datetime
    operating_state: OperatingState = OperatingState.NORMAL
    current_bankroll: float = 1000.0
    available_bankroll: float = 1000.0
    committed_daily_exposure: float = 0.0


@dataclass
class AccumulatorProductStats:
    product: ProductTier
    rounds_run: int = 0
    tickets_found: int = 0
    tickets_won: int = 0
    tickets_with_stake: int = 0
    total_stake: float = 0.0
    total_return: float = 0.0
    # Flat-stake baseline: 1 unit on every selected ticket at combined odds.
    # Isolates ticket-selection quality independently of the Kelly staking
    # decision.  Not a de-vigged market baseline — see module docstring.
    flat_stake_units: float = 0.0
    flat_stake_return: float = 0.0
    peak_bankroll: float = 0.0
    trough_bankroll: float = 0.0
    max_drawdown: float = 0.0
    _running_bankroll: float = field(default=0.0, repr=False)

    @property
    def hit_rate(self) -> float | None:
        if self.tickets_found == 0:
            return None
        return self.tickets_won / self.tickets_found

    @property
    def roi(self) -> float | None:
        if self.total_stake == 0:
            return None
        return (self.total_return - self.total_stake) / self.total_stake

    @property
    def flat_stake_roi(self) -> float | None:
        if self.flat_stake_units == 0:
            return None
        return (self.flat_stake_return - self.flat_stake_units) / self.flat_stake_units


@dataclass(frozen=True)
class AccumulatorBacktestReport:
    rounds_total: int
    leakage_rows_rejected: int
    decisions: list[AccumulatorDecision]
    product_stats: dict[ProductTier, AccumulatorProductStats]

    @property
    def summary(self) -> dict:
        return {
            "rounds_total": self.rounds_total,
            "leakage_rows_rejected": self.leakage_rows_rejected,
            "products": {
                product.value: {
                    "rounds_run": s.rounds_run,
                    "tickets_found": s.tickets_found,
                    "hit_rate": s.hit_rate,
                    "roi": s.roi,
                    "flat_stake_roi": s.flat_stake_roi,
                    "max_drawdown": s.max_drawdown,
                }
                for product, s in self.product_stats.items()
            },
        }


def walk_forward_accumulator_backtest(
    rounds: list[BacktestRound],
    *,
    policies: dict[ProductTier, AccumulatorPolicy] | None = None,
    risk_policy: RiskPolicy = DEFAULT_RISK_POLICY,
) -> AccumulatorBacktestReport:
    """Run the accumulator engine over *rounds* and return a backtest report.

    Rounds are processed in as_of order.  For each round the engine runs
    build_accumulator_decision (the same path as production).

    Leakage guard (price): candidates with quote_timestamp > as_of are dropped
    before the engine runs; each such candidate increments leakage_rows_rejected.

    Leakage guard (outcome): if outcome_observed_at <= as_of the outcome was
    already known at decision time; win/loss credit is withheld for that round
    and leakage_rows_rejected is incremented once per affected round.
    """
    rounds_sorted = sorted(rounds, key=lambda r: r.as_of)

    stats: dict[ProductTier, AccumulatorProductStats] = {
        p: AccumulatorProductStats(product=p) for p in ProductTier
    }
    decisions: list[AccumulatorDecision] = []
    leakage_rows_rejected = 0

    for rnd in rounds_sorted:
        # Leakage guard 1: candidate price freshness
        clean_candidates = []
        for c in rnd.candidates:
            if c.quote_timestamp > rnd.as_of:
                leakage_rows_rejected += 1
            else:
                clean_candidates.append(c)

        # Leakage guard 2: outcome observability
        outcome_valid = rnd.outcome_observed_at > rnd.as_of
        if not outcome_valid:
            leakage_rows_rejected += 1

        decision = build_accumulator_decision(
            clean_candidates,
            as_of=rnd.as_of,
            operating_state=rnd.operating_state,
            current_bankroll=rnd.current_bankroll,
            available_bankroll=rnd.available_bankroll,
            committed_daily_exposure=rnd.committed_daily_exposure,
            policies=policies,
            risk_policy=risk_policy,
        )
        decisions.append(decision)

        for pd in decision.products:
            s = stats[pd.product]
            s.rounds_run += 1

            if pd.result.ticket is None:
                continue

            ticket = pd.result.ticket
            s.tickets_found += 1

            # Outcome: ticket wins iff every leg's fixture_id maps to 1.
            # Withheld (not credited) when the outcome was already known at as_of.
            ticket_won = outcome_valid and all(
                rnd.outcome.get(leg.fixture_id, 0) == 1
                for leg in ticket.legs
            )
            if ticket_won:
                s.tickets_won += 1

            combined_odds_float = float(ticket.combined_odds)

            # Flat-stake baseline: 1 unit per ticket found, at combined odds.
            if outcome_valid:
                s.flat_stake_units += 1.0
                s.flat_stake_return += combined_odds_float if ticket_won else 0.0

            # Kelly stake tracking
            if outcome_valid and pd.stake_decision is not None and pd.stake_decision.approved:
                stake = pd.stake_decision.recommended_stake
                s.tickets_with_stake += 1
                s.total_stake += stake
                s.total_return += stake * combined_odds_float if ticket_won else 0.0

                # Running bankroll for drawdown
                if s.peak_bankroll == 0.0:
                    s.peak_bankroll = rnd.current_bankroll
                    s.trough_bankroll = rnd.current_bankroll
                    s._running_bankroll = rnd.current_bankroll

                s._running_bankroll += (
                    stake * combined_odds_float - stake if ticket_won else -stake
                )
                if s._running_bankroll > s.peak_bankroll:
                    s.peak_bankroll = s._running_bankroll
                if s._running_bankroll < s.trough_bankroll:
                    s.trough_bankroll = s._running_bankroll

                if s.peak_bankroll > 0:
                    drawdown = (s.peak_bankroll - s._running_bankroll) / s.peak_bankroll
                    if math.isfinite(drawdown) and drawdown > s.max_drawdown:
                        s.max_drawdown = drawdown

    return AccumulatorBacktestReport(
        rounds_total=len(rounds_sorted),
        leakage_rows_rejected=leakage_rows_rejected,
        decisions=decisions,
        product_stats=stats,
    )
