"""Ticket-level accumulator results, tallied by product and calendar period.

A ticket's result is always *derived* from its legs' effective settlement
outcomes; the settlement worker records that derived result as the ticket's
own ``Settlement`` row the moment it is decided:

- any leg lost                        -> ``lost`` (even while others are open)
- otherwise any leg still unsettled   -> ``pending``
- otherwise every leg void/push       -> ``void``
- otherwise                           -> ``won`` (void/push legs drop out of
  the ticket, the standard bookmaker treatment)

A ticket whose own status is ``void`` is ``void`` regardless of its legs.

Results are grouped by the ticket's publication date in a caller-chosen time
zone (UTC by default; the API uses the Africa/Blantyre product day so every
page agrees on which day a ticket belongs to) at year (``2026``), month
(``2026-09``) or day (``2026-09-27``) granularity.

Pure functions only; no database access.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Literal

TicketResult = Literal["won", "lost", "void", "pending"]
Granularity = Literal["year", "month", "day"]

GRANULARITIES: tuple[Granularity, ...] = ("year", "month", "day")

_LEG_WIN = "win"
_LEG_LOSS = "loss"
_LEG_NEUTRAL = frozenset({"void", "push"})
_KNOWN_LEG_OUTCOMES = frozenset({_LEG_WIN, _LEG_LOSS, *_LEG_NEUTRAL})


def derive_ticket_result(
    leg_outcomes: Sequence[str | None], *, ticket_voided: bool = False
) -> TicketResult:
    """Return a ticket's result from its legs' settlement outcomes.

    ``leg_outcomes`` holds one entry per leg: ``"win"``, ``"loss"``,
    ``"void"``, ``"push"``, or ``None`` when the leg is not settled yet.
    A ticket with no legs has nothing that could win, so it is ``void``.
    """
    unknown = {o for o in leg_outcomes if o is not None} - _KNOWN_LEG_OUTCOMES
    if unknown:
        raise ValueError(f"unknown leg outcome(s): {sorted(unknown)}")
    if ticket_voided:
        return "void"
    if _LEG_LOSS in leg_outcomes:
        return "lost"
    if None in leg_outcomes:
        return "pending"
    if all(o in _LEG_NEUTRAL for o in leg_outcomes):
        return "void"
    return "won"


def ticket_settlement_odds(
    legs: Sequence[tuple[str | None, float]], result: TicketResult
) -> float | None:
    """Decimal odds a decided ticket is settled at, one unit staked.

    ``legs`` holds ``(outcome, decimal_odds)`` per leg.  A won ticket pays the
    product of its *winning* legs' odds (void/push legs drop out, the
    standard bookmaker treatment); a lost ticket is recorded at its full
    published price.  Void and pending tickets have no settlement price.
    """
    if result == "won":
        odds = [price for outcome, price in legs if outcome == _LEG_WIN]
    elif result == "lost":
        odds = [price for _, price in legs]
    else:
        return None
    if not odds or any(price <= 1 for price in odds):
        raise ValueError("a decided ticket needs leg odds greater than 1")
    return math.prod(odds)


def flat_unit_profit(result: TicketResult, settlement_odds: float | None) -> float | None:
    """Profit on a flat one-unit stake: odds − 1 won, −1 lost, 0 void.

    Pending tickets have no profit yet (``None``).  ``settlement_odds`` is
    what :func:`ticket_settlement_odds` returns and is required for a win.
    """
    if result == "won":
        if settlement_odds is None:
            raise ValueError("a won ticket needs its settlement odds")
        return settlement_odds - 1.0
    if result == "lost":
        return -1.0
    if result == "void":
        return 0.0
    return None


def period_key(ts: datetime, granularity: Granularity, tz: tzinfo = UTC) -> str:
    """Return the calendar bucket label for *ts* in time zone *tz*.

    Naive datetimes are treated as UTC (SQLite test databases drop tzinfo).
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ts = ts.astimezone(tz)
    if granularity == "year":
        return f"{ts.year:04d}"
    if granularity == "month":
        return f"{ts.year:04d}-{ts.month:02d}"
    if granularity == "day":
        return ts.date().isoformat()
    raise ValueError(f"granularity must be one of {GRANULARITIES}")


@dataclass(frozen=True)
class TicketRecord:
    """One accumulator ticket reduced to what the tally needs."""

    product: str
    published_at: datetime
    result: TicketResult
    #: Flat one-unit profit (see :func:`flat_unit_profit`); None while pending.
    profit_units: float | None = None


@dataclass(frozen=True)
class ProductTally:
    """Result counts for one product within one period."""

    product: str
    won: int
    lost: int
    void: int
    pending: int
    #: Summed flat one-unit profit of the decided tickets.
    profit_units: float = 0.0

    @property
    def total(self) -> int:
        return self.won + self.lost + self.void + self.pending

    @property
    def win_rate(self) -> float | None:
        """Wins over decided (won + lost) tickets; None until one is decided."""
        decided = self.won + self.lost
        return self.won / decided if decided else None


@dataclass(frozen=True)
class PeriodTally:
    """All products' result counts for one calendar period."""

    period: str
    products: tuple[ProductTally, ...]


def tally_by_period(
    records: Iterable[TicketRecord], granularity: Granularity, tz: tzinfo = UTC
) -> list[PeriodTally]:
    """Group ticket results by period and product.

    Periods are returned newest first; products within a period are sorted
    alphabetically.  Only products that published in a period appear in it.
    """
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}")
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"won": 0, "lost": 0, "void": 0, "pending": 0})
    )
    profits: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for record in records:
        key = period_key(record.published_at, granularity, tz)
        counts[key][record.product][record.result] += 1
        if record.profit_units is not None:
            profits[key][record.product] += record.profit_units

    return [
        PeriodTally(
            period=period,
            products=tuple(
                ProductTally(product=product, **c, profit_units=profits[period][product])
                for product, c in sorted(counts[period].items())
            ),
        )
        for period in sorted(counts, reverse=True)
    ]
