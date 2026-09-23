"""Daily Picks: a guaranteed minimum of paper tickets per day.

The value-qualified products (CORE/GROWTH/ALPHA, see ``decision.py``) are
allowed to publish nothing — ``NO QUALIFIED ACCA`` is an expected result and
their thresholds must never be lowered to force a ticket
(ACCUMULATOR_POLICY.md). Daily Picks are a *separate, explicitly labelled*
product line that always publishes the best tickets the day's slate allows,
so the product never goes silent. They are:

- **Not value-qualified.** A Daily Pick leg need not pass the Value Gate. The
  ticket is ranked on a shrunk probability estimate (model blended with the
  de-vigged market), not on a claimed edge.
- **Paper-only and unstaked.** No stake is recommended; the persistence layer
  refuses anything but paper tickets.
- **Kept out of value-product KPIs** by their distinct ``daily_*`` product
  labels.

Each product walks a relaxation ladder: rung 0 is the preferred shape, later
rungs widen the leg/odds bands, and the last rung is a shared last resort
that only requires two legs from distinct fixtures. Every ticket records the
rung (``level_version``) it was built at, so a "forced" ticket is always
distinguishable from a preferred one in the archive.

Pure module — no I/O. The service layer supplies candidates and persists.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

DAILY_BUILDER_VERSION = "daily-ticket-v1"

# Weight on the model probability when blending with the de-vigged market
# probability. The market is the stronger single estimator for heavily traded
# 1X2 prices and the model is not yet calibrated on a large settled sample,
# so an equal-weight shrinkage is the conservative research default. Must be
# revisited once settled Daily Pick history exists.
MODEL_WEIGHT = 0.5

# Candidates are ranked by estimated probability and only the top slice is
# searched exhaustively; C(24, 5) = 42,504 keeps the search sub-second.
POOL_CAP = 24
MAX_COMBINATIONS = 250_000


class DailyProduct(StrEnum):
    SAFE = "daily_safe"
    BALANCED = "daily_balanced"
    BOLD = "daily_bold"


# Build order matters: SAFE takes the strongest legs first.
DAILY_PRODUCTS: tuple[DailyProduct, ...] = (
    DailyProduct.SAFE,
    DailyProduct.BALANCED,
    DailyProduct.BOLD,
)


@dataclass(frozen=True)
class DailyCandidate:
    """An archived forecast re-priced against a current market snapshot."""

    prediction_id: str
    fixture_id: str
    league_id: str
    selection: str
    kickoff_utc: datetime
    model_probability: float
    market_probability: float
    decimal_odds: Decimal
    captured_at: datetime
    dqs: float
    bookmaker: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("prediction_id", self.prediction_id),
            ("fixture_id", self.fixture_id),
            ("league_id", self.league_id),
            ("selection", self.selection),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")
        for name, prob in (
            ("model_probability", self.model_probability),
            ("market_probability", self.market_probability),
        ):
            if not math.isfinite(prob) or not 0 < prob < 1:
                raise ValueError(f"{name} must be finite and in (0, 1)")
        if not isinstance(self.decimal_odds, Decimal) or not self.decimal_odds.is_finite():
            raise ValueError("decimal_odds must be a finite Decimal")
        if self.decimal_odds <= 1:
            raise ValueError("decimal_odds must be greater than 1")
        if not math.isfinite(self.dqs) or not 0 <= self.dqs <= 100:
            raise ValueError("dqs must be finite and in [0, 100]")
        for name, ts in (("kickoff_utc", self.kickoff_utc), ("captured_at", self.captured_at)):
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")

    @property
    def estimated_probability(self) -> float:
        return MODEL_WEIGHT * self.model_probability + (1 - MODEL_WEIGHT) * self.market_probability

    @property
    def edge(self) -> float:
        """Estimated probability minus fair market probability (may be negative)."""
        return self.estimated_probability - self.market_probability

    @property
    def model_deficit(self) -> float:
        """How far the model sits *below* the market (positive = model disagrees)."""
        return self.market_probability - self.model_probability


@dataclass(frozen=True)
class DailyTicketLevel:
    """One rung of a product's relaxation ladder."""

    version: str
    min_legs: int
    max_legs: int
    min_combined_odds: Decimal
    max_combined_odds: Decimal
    min_leg_odds: Decimal
    max_leg_odds: Decimal
    min_leg_probability: float
    # Exclude legs where the model is below the market by more than this;
    # ``None`` disables the check (last-resort rung only).
    max_model_deficit: float | None
    max_legs_per_league: int
    maximise: str  # "probability" or "expected_return"
    # Research leagues are re-priced about once a day by the ingestion
    # rotation, so freshness is relaxed rung by rung rather than failing the
    # whole slate. The leg's quote timestamp is always persisted and shown.
    max_quote_age: timedelta = timedelta(hours=3)

    def __post_init__(self) -> None:
        if not 2 <= self.min_legs <= self.max_legs:
            raise ValueError("require 2 <= min_legs <= max_legs")
        if not 1 < self.min_combined_odds < self.max_combined_odds:
            raise ValueError("require 1 < min_combined_odds < max_combined_odds")
        if not 1 < self.min_leg_odds < self.max_leg_odds:
            raise ValueError("require 1 < min_leg_odds < max_leg_odds")
        if not 0 <= self.min_leg_probability < 1:
            raise ValueError("min_leg_probability must be in [0, 1)")
        if self.max_legs_per_league < 1:
            raise ValueError("max_legs_per_league must be at least 1")
        if self.maximise not in {"probability", "expected_return"}:
            raise ValueError("maximise must be 'probability' or 'expected_return'")
        if self.max_quote_age <= timedelta(0):
            raise ValueError("max_quote_age must be positive")


_RELAXED_QUOTE_AGE = timedelta(hours=8)
LAST_RESORT_QUOTE_AGE = timedelta(hours=26)

# Up to five legs and a 1.25 floor so even a slate of only heavy favourites
# (1.05 ** 5 = 1.276) still yields a ticket.
_LAST_RESORT = DailyTicketLevel(
    version="daily-last-resort-v1",
    min_legs=2,
    max_legs=5,
    min_combined_odds=Decimal("1.25"),
    max_combined_odds=Decimal("30.00"),
    min_leg_odds=Decimal("1.03"),
    max_leg_odds=Decimal("6.00"),
    min_leg_probability=0.15,
    max_model_deficit=None,
    max_legs_per_league=3,
    maximise="probability",
    max_quote_age=LAST_RESORT_QUOTE_AGE,
)

DAILY_LADDERS: dict[DailyProduct, tuple[DailyTicketLevel, ...]] = {
    DailyProduct.SAFE: (
        DailyTicketLevel(
            version="daily-safe-v1",
            min_legs=2, max_legs=3,
            min_combined_odds=Decimal("1.80"), max_combined_odds=Decimal("3.50"),
            min_leg_odds=Decimal("1.15"), max_leg_odds=Decimal("1.80"),
            min_leg_probability=0.58, max_model_deficit=0.08,
            max_legs_per_league=2, maximise="probability",
        ),
        DailyTicketLevel(
            version="daily-safe-relaxed-v1",
            min_legs=2, max_legs=3,
            min_combined_odds=Decimal("1.60"), max_combined_odds=Decimal("4.50"),
            min_leg_odds=Decimal("1.10"), max_leg_odds=Decimal("2.10"),
            min_leg_probability=0.50, max_model_deficit=0.12,
            max_legs_per_league=2, maximise="probability",
            max_quote_age=_RELAXED_QUOTE_AGE,
        ),
        _LAST_RESORT,
    ),
    DailyProduct.BALANCED: (
        DailyTicketLevel(
            version="daily-balanced-v1",
            min_legs=3, max_legs=4,
            min_combined_odds=Decimal("3.00"), max_combined_odds=Decimal("6.00"),
            min_leg_odds=Decimal("1.25"), max_leg_odds=Decimal("2.30"),
            min_leg_probability=0.45, max_model_deficit=0.08,
            max_legs_per_league=2, maximise="expected_return",
        ),
        DailyTicketLevel(
            version="daily-balanced-relaxed-v1",
            min_legs=2, max_legs=4,
            min_combined_odds=Decimal("2.50"), max_combined_odds=Decimal("8.00"),
            min_leg_odds=Decimal("1.15"), max_leg_odds=Decimal("2.80"),
            min_leg_probability=0.38, max_model_deficit=0.12,
            max_legs_per_league=2, maximise="expected_return",
            max_quote_age=_RELAXED_QUOTE_AGE,
        ),
        _LAST_RESORT,
    ),
    DailyProduct.BOLD: (
        DailyTicketLevel(
            version="daily-bold-v1",
            min_legs=4, max_legs=5,
            min_combined_odds=Decimal("6.00"), max_combined_odds=Decimal("15.00"),
            min_leg_odds=Decimal("1.35"), max_leg_odds=Decimal("3.20"),
            min_leg_probability=0.33, max_model_deficit=0.08,
            max_legs_per_league=2, maximise="expected_return",
        ),
        DailyTicketLevel(
            version="daily-bold-relaxed-v1",
            min_legs=3, max_legs=5,
            min_combined_odds=Decimal("4.50"), max_combined_odds=Decimal("20.00"),
            min_leg_odds=Decimal("1.20"), max_leg_odds=Decimal("4.00"),
            min_leg_probability=0.28, max_model_deficit=0.12,
            max_legs_per_league=2, maximise="expected_return",
            max_quote_age=_RELAXED_QUOTE_AGE,
        ),
        _LAST_RESORT,
    ),
}


@dataclass(frozen=True)
class DailyTicket:
    product: DailyProduct
    legs: tuple[DailyCandidate, ...]
    combined_odds: Decimal
    joint_probability: float
    expected_return: float  # joint_probability * combined_odds (1.0 = break-even)
    level_version: str
    rung: int


@dataclass(frozen=True)
class DailyBuildResult:
    tickets: tuple[DailyTicket, ...]
    shortfall: tuple[DailyProduct, ...]
    candidates_considered: int


def build_daily_tickets(
    candidates: list[DailyCandidate],
    *,
    products: tuple[DailyProduct, ...] = DAILY_PRODUCTS,
    as_of: datetime,
) -> DailyBuildResult:
    """Build one ticket per requested product from disjoint fixtures.

    Deterministic: the same candidates and ``as_of`` always yield the same
    tickets. Earlier products never take legs that the later products need
    to exist at all (see ``_build_one``). A product that cannot be built even
    at its last-resort rung is reported in ``shortfall`` — the caller must
    surface that loudly.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    usable = [
        c for c in candidates
        if c.kickoff_utc > as_of
        and timedelta(0) <= as_of - c.captured_at <= LAST_RESORT_QUOTE_AGE
    ]
    # One leg per fixture across the whole day: keep the strongest candidate.
    by_fixture: dict[str, DailyCandidate] = {}
    for c in sorted(usable, key=_rank_key):
        by_fixture.setdefault(c.fixture_id, c)
    remaining = sorted(by_fixture.values(), key=_rank_key)

    tickets: list[DailyTicket] = []
    shortfall: list[DailyProduct] = []
    for index, product in enumerate(products):
        reserve = tuple(p for p in products[index + 1:])
        ticket = _build_one(product, remaining, reserve=reserve, as_of=as_of)
        if ticket is None:
            shortfall.append(product)
            continue
        tickets.append(ticket)
        used = {leg.fixture_id for leg in ticket.legs}
        remaining = [c for c in remaining if c.fixture_id not in used]

    return DailyBuildResult(
        tickets=tuple(tickets),
        shortfall=tuple(shortfall),
        candidates_considered=len(by_fixture),
    )


def _rank_key(c: DailyCandidate) -> tuple[float, str]:
    return (-c.estimated_probability, c.fixture_id)


def _eligible(c: DailyCandidate, level: DailyTicketLevel, as_of: datetime) -> bool:
    if as_of - c.captured_at > level.max_quote_age:
        return False
    if not level.min_leg_odds <= c.decimal_odds <= level.max_leg_odds:
        return False
    if c.estimated_probability < level.min_leg_probability:
        return False
    if level.max_model_deficit is not None and c.model_deficit > level.max_model_deficit:
        return False
    return True


# How many ranked combinations to test for reserve feasibility per rung, and
# how many legs the (cheap) feasibility probe may search over.
MAX_RESERVE_CHECKS = 300
_RESERVE_PROBE_POOL = 12


def _build_one(
    product: DailyProduct,
    pool: list[DailyCandidate],
    *,
    reserve: tuple[DailyProduct, ...],
    as_of: datetime,
) -> DailyTicket | None:
    """Best ticket for *product* that still leaves the *reserve* products buildable.

    Walks the ladder rung by rung; within a rung, combinations are tried best
    first and the first one whose leftover pool can still yield a last-resort
    ticket for every reserve product wins. Only when no rung can protect the
    reserve is the unconstrained best ticket taken (one ticket beats none).
    """
    fallback: DailyTicket | None = None
    for rung, level in enumerate(DAILY_LADDERS[product]):
        ranked = _ranked_combinations(
            level, [c for c in pool if _eligible(c, level, as_of)][:POOL_CAP]
        )
        if not ranked:
            continue
        if fallback is None:
            fallback = _ticket(product, ranked[0], level, rung)
        if not reserve:
            return _ticket(product, ranked[0], level, rung)
        for combo in ranked[:MAX_RESERVE_CHECKS]:
            used = {c.fixture_id for c in combo}
            leftover = [c for c in pool if c.fixture_id not in used]
            if _reserve_feasible(leftover, len(reserve), as_of):
                return _ticket(product, combo, level, rung)
    return fallback


def _reserve_feasible(pool: list[DailyCandidate], count: int, as_of: datetime) -> bool:
    """Can *count* disjoint last-resort tickets still be built from *pool*?"""
    remaining = [c for c in pool if _eligible(c, _LAST_RESORT, as_of)]
    for _ in range(count):
        ranked = _ranked_combinations(_LAST_RESORT, remaining[:_RESERVE_PROBE_POOL])
        if not ranked:
            return False
        used = {c.fixture_id for c in ranked[0]}
        remaining = [c for c in remaining if c.fixture_id not in used]
    return True


def _ticket(
    product: DailyProduct,
    legs: tuple[DailyCandidate, ...],
    level: DailyTicketLevel,
    rung: int,
) -> DailyTicket:
    odds = _combined_odds(legs)
    joint = math.prod(leg.estimated_probability for leg in legs)
    return DailyTicket(
        product=product,
        legs=legs,
        combined_odds=odds,
        joint_probability=joint,
        expected_return=joint * float(odds),
        level_version=level.version,
        rung=rung,
    )


def _ranked_combinations(
    level: DailyTicketLevel, pool: list[DailyCandidate]
) -> list[tuple[DailyCandidate, ...]]:
    """Every valid combination for *level*, best first (deterministic order).

    Ranking: primary objective desc, secondary objective desc, then the
    sorted fixture-id tuple asc as a stable tie-break.
    """
    scored: list[tuple[float, float, tuple[str, ...], tuple[DailyCandidate, ...]]] = []
    evaluated = 0
    for size in range(level.min_legs, min(level.max_legs, len(pool)) + 1):
        for combo in itertools.combinations(pool, size):
            evaluated += 1
            if evaluated > MAX_COMBINATIONS:
                break
            odds = _combined_odds(combo)
            if not level.min_combined_odds <= odds <= level.max_combined_odds:
                continue
            league_counts = Counter(c.league_id for c in combo)
            if max(league_counts.values()) > level.max_legs_per_league:
                continue
            joint = math.prod(c.estimated_probability for c in combo)
            expected_return = joint * float(odds)
            primary, secondary = (
                (joint, expected_return)
                if level.maximise == "probability"
                else (expected_return, joint)
            )
            fixtures = tuple(sorted(c.fixture_id for c in combo))
            scored.append((primary, secondary, fixtures, combo))
    scored.sort(key=lambda s: s[2])  # stable: tie-break first ...
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)  # ... then objective desc
    return [s[3] for s in scored]


def _combined_odds(legs: tuple[DailyCandidate, ...]) -> Decimal:
    result = Decimal("1")
    for leg in legs:
        result *= leg.decimal_odds
    return result
