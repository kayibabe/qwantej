"""Guarantee a daily minimum of Daily Pick paper tickets (see qwantej.accumulator.daily).

``ensure_daily_tickets`` is idempotent per UTC day: it counts the Daily Pick
tickets already published today and builds only the missing products, so the
hourly scheduler can call it every run and a failed run is retried on the
next tick.

Candidate legs are *archived* forecasts (production or research) for
upcoming fixtures — never a probability computed here, so every leg keeps
full forecast lineage (DEVELOPMENT.md §4 "every prediction is archived").
Each leg is re-priced against the freshest coherent bookmaker snapshot
at build time, because the archived forecast's quote may be a day old.

Persistence is fail-closed, mirroring ``backend.services.accumulator``:
every leg's prediction row is locked (``SELECT … FOR UPDATE``) and checked
before anything is written, and a prediction can back at most one ticket.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Prediction,
    TicketStatus,
)
from backend.services.accumulator import AccumulatorPersistenceError
from qwantej.accumulator.daily import (
    DAILY_BUILDER_VERSION,
    DAILY_PRODUCTS,
    LAST_RESORT_QUOTE_AGE,
    DailyCandidate,
    DailyProduct,
    DailyTicket,
    build_daily_tickets,
)
from qwantej.markets.devig import devig

log = logging.getLogger(__name__)

_MARKET_SELECTIONS = {
    "1X2": ("home", "draw", "away"),
    "BTTS": ("yes", "no"),
}

# Same ticket-level stress haircut the value products use (AccumulatorPolicy).
STRESS_HAIRCUT = 0.05
# Framework §10: DQS < 60 is the REJECT band — never a customer-facing leg.
MIN_DQS = 60.0
# Customers need time to place a ticket before the first kickoff.
MIN_LEAD = timedelta(minutes=60)
PRIMARY_LOOKAHEAD = timedelta(hours=30)
FALLBACK_LOOKAHEAD = timedelta(hours=72)
# Oldest quote any ladder rung accepts; each rung applies its own, tighter cap.
MAX_QUOTE_AGE = LAST_RESORT_QUOTE_AGE
# All legs of one bookmaker snapshot must be captured within this spread.
MAX_LEG_SPREAD = timedelta(hours=1)
# Serialises concurrent builders (overlapping deploys, manual runs) on
# PostgreSQL so two processes cannot both see "not yet published today".
_ADVISORY_LOCK_KEY = 0x51_44_41_49_4C_59  # "QDAILY"


@dataclass
class DailyTicketRun:
    """Outcome of one ``ensure_daily_tickets`` call."""

    target: int
    existing_today: int
    created: list[Accumulator] = field(default_factory=list)
    tickets: list[DailyTicket] = field(default_factory=list)
    shortfall: list[DailyProduct] = field(default_factory=list)
    candidates_considered: int = 0

    @property
    def total_today(self) -> int:
        return self.existing_today + len(self.created)


def ensure_daily_tickets(
    session: Session,
    *,
    now: datetime,
    target: int = len(DAILY_PRODUCTS),
    build_hour_utc: int = 0,
) -> DailyTicketRun:
    """Top up today's Daily Pick tickets to *target* (max one per product).

    Nothing is built before *build_hour_utc* so the day's tickets cover the
    day's matches rather than the small hours. The caller owns the
    transaction. A non-empty ``shortfall`` means the slate genuinely could not
    support a ticket even at the last-resort rung and must be alerted on.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not 0 <= target <= len(DAILY_PRODUCTS):
        raise ValueError(f"target must be in [0, {len(DAILY_PRODUCTS)}]")
    if not 0 <= build_hour_utc <= 23:
        raise ValueError("build_hour_utc must be in [0, 23]")

    if target and session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(_ADVISORY_LOCK_KEY)))

    wanted = DAILY_PRODUCTS[:target]
    published = _products_published_today(session, now)
    missing = tuple(p for p in wanted if p.value not in published)
    run = DailyTicketRun(
        target=target,
        existing_today=sum(1 for p in wanted if p.value in published),
    )
    if not missing or now.astimezone(UTC).hour < build_hour_utc:
        return run

    used_fixtures: set[str] = set()
    for lookahead in (PRIMARY_LOOKAHEAD, FALLBACK_LOOKAHEAD):
        candidates = [
            c for c in load_daily_candidates(session, now=now, lookahead=lookahead)
            if c.fixture_id not in used_fixtures
        ]
        result = build_daily_tickets(candidates, products=missing, as_of=now)
        run.candidates_considered = max(run.candidates_considered, result.candidates_considered)
        run.tickets.extend(result.tickets)
        for ticket in result.tickets:
            used_fixtures.update(leg.fixture_id for leg in ticket.legs)
        missing = result.shortfall
        if not missing:
            break

    run.shortfall = list(missing)
    if run.tickets:
        run.created = _persist(session, run.tickets, now=now)
    if run.shortfall:
        log.error(
            "daily_tickets: SHORTFALL — could not build %s (candidates=%d); "
            "today has %d/%d Daily Pick tickets",
            [p.value for p in run.shortfall], run.candidates_considered,
            run.total_today, target,
        )
    else:
        log.info(
            "daily_tickets: %d created, %d/%d Daily Pick tickets today",
            len(run.created), run.total_today, target,
        )
    return run


def _utc(ts: datetime) -> datetime:
    # SQLite drops tzinfo; PostgreSQL preserves it. Persisted times are UTC.
    return ts.astimezone(UTC) if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def _products_published_today(session: Session, now: datetime) -> set[str]:
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    rows = session.scalars(
        select(Accumulator.product)
        .where(
            Accumulator.product.in_([p.value for p in DAILY_PRODUCTS]),
            Accumulator.published_at >= day_start,
            Accumulator.published_at < day_start + timedelta(days=1),
        )
        .distinct()
    )
    return set(rows)


def load_daily_candidates(
    session: Session, *, now: datetime, lookahead: timedelta
) -> list[DailyCandidate]:
    """Archived supported-market forecasts for upcoming fixtures, re-priced now.

    Fixtures already on any ticket are excluded, as are forecasts
    below the DQS reject band or without a coherent fresh market snapshot.
    """
    fixtures_on_tickets = select(Prediction.fixture_id).where(
        Prediction.accumulator_id.is_not(None)
    )
    rows = session.execute(
        select(Prediction, Fixture)
        .join(Fixture, Prediction.fixture_id == Fixture.id)
        .where(
            Prediction.market.in_(tuple(_MARKET_SELECTIONS)),
            Prediction.accumulator_id.is_(None),
            Prediction.calibrated_probability.is_not(None),
            Prediction.dqs >= MIN_DQS,
            # A leg's forecast must predate the ticket's own decision cutoff.
            Prediction.prediction_timestamp <= now,
            Prediction.decision_as_of <= now,
            Fixture.status == FixtureStatus.SCHEDULED,
            Fixture.kickoff_utc > now + MIN_LEAD,
            Fixture.kickoff_utc <= now + lookahead,
            Fixture.id.not_in(fixtures_on_tickets),
        )
        .order_by(
            Prediction.research_mode,
            Prediction.prediction_timestamp.desc(),
            Prediction.id,
        )
    ).all()

    chosen: dict[tuple[uuid.UUID, str, str], tuple[Prediction, Fixture]] = {}
    for prediction, fixture in rows:
        if (
            prediction.selection in _MARKET_SELECTIONS[prediction.market]
            and prediction.line is None
        ):
            key = (fixture.id, prediction.market, prediction.selection)
            chosen.setdefault(key, (prediction, fixture))
    if not chosen:
        return []

    snapshots = _market_snapshots(session, list({key[0] for key in chosen}), now=now)
    candidates: list[DailyCandidate] = []
    for (fixture_id, market, selection), (prediction, fixture) in chosen.items():
        snap = snapshots.get((fixture_id, market, selection))
        if snap is None:
            continue
        odds, fair_probability, bookmaker, captured_at = snap
        model_p = float(prediction.calibrated_probability)  # type: ignore[arg-type]
        if not 0 < model_p < 1 or not 0 < fair_probability < 1:
            continue
        candidates.append(
            DailyCandidate(
                prediction_id=str(prediction.id),
                fixture_id=str(fixture.id),
                league_id=str(fixture.competition_id),
                market=market,
                selection=selection,
                kickoff_utc=_utc(fixture.kickoff_utc),
                model_probability=model_p,
                market_probability=fair_probability,
                decimal_odds=odds,
                captured_at=captured_at,
                dqs=float(prediction.dqs),  # type: ignore[arg-type]
                bookmaker=bookmaker,
            )
        )
    return candidates


def _market_snapshots(
    session: Session, fixture_ids: list[uuid.UUID], *, now: datetime
) -> dict[tuple[uuid.UUID, str, str], tuple[Decimal, float, str, datetime]]:
    """Freshest coherent supported-market snapshots by fixture and selection.

    Coherent = one bookmaker quoting every outcome within MAX_LEG_SPREAD,
    so the de-vig runs on a real market rather than a synthetic mix (same rule
    as the signal pipeline). Ties on freshness break on bookmaker name.
    """
    quotes = session.scalars(
        select(OddsQuote).where(
            OddsQuote.fixture_id.in_(fixture_ids),
            OddsQuote.market.in_(tuple(_MARKET_SELECTIONS)),
            OddsQuote.captured_at < now,
            OddsQuote.captured_at >= now - MAX_QUOTE_AGE,
        )
        .order_by(OddsQuote.captured_at.desc(), OddsQuote.id)
    )
    latest: dict[tuple[uuid.UUID, str], dict[str, dict[str, OddsQuote]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for q in quotes:
        if q.line is None and q.selection in _MARKET_SELECTIONS[q.market]:
            latest[(q.fixture_id, q.market)][q.bookmaker].setdefault(q.selection, q)

    out: dict[tuple[uuid.UUID, str, str], tuple[Decimal, float, str, datetime]] = {}
    for (fixture_id, market), books in latest.items():
        selections = _MARKET_SELECTIONS[market]
        best: tuple[datetime, str] | None = None
        for bookmaker, sel_map in books.items():
            if not all(s in sel_map for s in selections):
                continue
            stamps = [_utc(sel_map[s].captured_at) for s in selections]
            if max(stamps) - min(stamps) > MAX_LEG_SPREAD:
                continue
            odds = [float(sel_map[s].decimal_odds) for s in selections]
            try:
                fair = devig(odds).fair
            except ValueError:
                continue
            rank = (max(stamps), bookmaker)
            if best is None or rank[0] > best[0] or (rank[0] == best[0] and rank[1] < best[1]):
                best = rank
                for index, selection in enumerate(selections):
                    out[(fixture_id, market, selection)] = (
                        Decimal(str(sel_map[selection].decimal_odds)),
                        fair[index], bookmaker, min(stamps),
                    )
    return out


def _manifest_hash(tickets: list[DailyTicket], now: datetime) -> str:
    payload = {
        "as_of": now.isoformat(),
        "builder": DAILY_BUILDER_VERSION,
        "tickets": [
            {
                "product": t.product.value,
                "level": t.level_version,
                "legs": [
                    {
                        "prediction_id": leg.prediction_id,
                        "decimal_odds": str(leg.decimal_odds),
                        "market_probability": leg.market_probability,
                        "model_probability": leg.model_probability,
                        "captured_at": leg.captured_at.isoformat(),
                    }
                    for leg in t.legs
                ],
            }
            for t in tickets
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _persist(session: Session, tickets: list[DailyTicket], *, now: datetime) -> list[Accumulator]:
    """Validate every leg under row locks, then write all tickets (all-or-nothing)."""
    problems: list[str] = []
    predictions: dict[str, Prediction] = {}
    for ticket in tickets:
        for leg in ticket.legs:
            if leg.prediction_id in predictions:
                problems.append(f"prediction {leg.prediction_id} used by two tickets")
                continue
            prediction = session.execute(
                select(Prediction)
                .where(Prediction.id == uuid.UUID(leg.prediction_id))
                .with_for_update()
            ).scalar_one_or_none()
            if prediction is None:
                problems.append(f"prediction {leg.prediction_id} does not exist")
                continue
            if str(prediction.fixture_id) != leg.fixture_id:
                problems.append(
                    f"prediction {leg.prediction_id} is not for fixture {leg.fixture_id}"
                )
            if prediction.accumulator_id is not None:
                problems.append(
                    f"prediction {leg.prediction_id} already belongs to accumulator "
                    f"{prediction.accumulator_id}"
                )
            predictions[leg.prediction_id] = prediction
    if problems:
        raise AccumulatorPersistenceError(problems)

    manifest = _manifest_hash(tickets, now)
    written: list[Accumulator] = []
    for ticket in tickets:
        accumulator = Accumulator(
            product=ticket.product.value,
            optimiser_version=DAILY_BUILDER_VERSION,
            policy_version=ticket.level_version,
            combined_odds=float(ticket.combined_odds),
            conservative_joint_probability=ticket.joint_probability,
            stressed_joint_probability=ticket.joint_probability * (1 - STRESS_HAIRCUT),
            objective_score=ticket.expected_return,
            dependence_penalty_applied=0.0,
            published_at=now,
            stake=None,  # Daily Picks are never staked.
            risk_policy_version=None,
            status=TicketStatus.PENDING,
            input_manifest_hash=manifest,
            risk_state=None,
            decision_cutoff=now,
            paper_only=True,
        )
        session.add(accumulator)
        session.flush()
        for index, leg in enumerate(ticket.legs):
            prediction = predictions[leg.prediction_id]
            session.add(
                AccumulatorLeg(
                    accumulator_id=accumulator.id,
                    prediction_id=prediction.id,
                    fixture_id=prediction.fixture_id,
                    leg_index=index,
                    league_id=leg.league_id,
                    market_family=leg.market,
                    selection=leg.selection,
                    decimal_odds=float(leg.decimal_odds),
                    conservative_probability=leg.estimated_probability,
                    edge=leg.edge,
                    qss=float(prediction.qss) if prediction.qss is not None else leg.dqs,
                    bookmaker=leg.bookmaker,
                    quote_captured_at=leg.captured_at,
                )
            )
            prediction.accumulator_id = accumulator.id
        session.flush()
        written.append(accumulator)
    return written
