"""Record real-money bets on published tickets and settle them into the ledger.

Rules enforced here (the API is a thin layer over this module):

- A real bet is one whole published ticket (exact legs), in the account's
  single currency, placed after the ticket was published and before its first
  kickoff, and never in the future.
- A stake must fit the *available* bankroll: settled ledger balance minus the
  stakes already riding on open bets. Record a deposit first.
- The bookmaker's payout is authoritative and must be consistent with the
  outcome (lost → 0, void → stake returned, won → more than the stake).
- Settling posts profit/loss to the bankroll ledger as one ``settlement``
  entry. A correction supersedes the current settlement and posts only the
  change in profit/loss, so the ledger always sums to the true result.

The ledger requires chronological appends, so ledger entries are dated when
they are *recorded*; the bookmaker's own settlement time is kept on the
settlement row. Every money action is written to the audit trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.models import (
    Accumulator,
    AccumulatorLeg,
    AuditActor,
    AuditEvent,
    AuditEventType,
    BankrollLedgerEntry,
    LedgerEntryType,
    RealBet,
    RealBetOutcome,
    RealBetSettlement,
    TicketStatus,
)
from backend.services.bankroll import _lock_account, _money, append_ledger_entry, current_bankroll

DEFAULT_ACCOUNT = "primary"
# Clock-skew allowance for "not in the future" checks.
_FUTURE_TOLERANCE = timedelta(minutes=5)
_ODDS_QUANTUM = Decimal("0.0001")


class RealBetError(ValueError):
    """A request that breaks a real-money rule; the message is user-facing."""


class RealBetNotFound(RealBetError):
    pass


@dataclass(frozen=True)
class BankrollSummary:
    account: str
    currency: str
    balance: Decimal
    open_exposure: Decimal
    available: Decimal
    open_bets: int


def _decimal(value: Decimal | float | str, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise RealBetError(f"{field} must be a number") from exc
    if not result.is_finite():
        raise RealBetError(f"{field} must be a finite number")
    return result


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RealBetError(f"{field} must include a time zone")
    return value


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; stored timestamps are UTC by convention.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _audit(session: Session, *, action: str, entity_type: str, entity_id: uuid.UUID,
           summary: str, payload: dict, occurred_at: datetime) -> None:
    session.add(
        AuditEvent(
            event_type=AuditEventType.OTHER,
            actor=AuditActor.HUMAN,
            actor_ref="api",
            action=action,
            summary=summary[:500],
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            occurred_at=occurred_at,
        )
    )


# --------------------------------------------------------------------------
# Bankroll position
# --------------------------------------------------------------------------

def open_exposure(session: Session, account: str = DEFAULT_ACCOUNT) -> tuple[Decimal, int]:
    """Total stake on bets with no settlement yet, and how many there are."""

    settled = select(RealBetSettlement.real_bet_id)
    total, count = session.execute(
        select(func.coalesce(func.sum(RealBet.stake), 0), func.count(RealBet.id)).where(
            RealBet.account == account, RealBet.id.not_in(settled)
        )
    ).one()
    return _money(total), int(count)


def bankroll_summary(session: Session, account: str = DEFAULT_ACCOUNT) -> BankrollSummary:
    balance = _money(current_bankroll(session, account))
    exposure, count = open_exposure(session, account)
    return BankrollSummary(
        account=account,
        currency=get_settings().real_money_currency,
        balance=balance,
        open_exposure=exposure,
        available=balance - exposure,
        open_bets=count,
    )


def record_cash_flow(
    session: Session,
    *,
    kind: LedgerEntryType,
    amount: Decimal | float | str,
    occurred_at: datetime,
    reference: str | None = None,
    idempotency_key: str | None = None,
    account: str = DEFAULT_ACCOUNT,
    now: datetime | None = None,
) -> BankrollLedgerEntry:
    """Record a deposit or withdrawal. ``amount`` is always given as positive."""

    if kind not in (LedgerEntryType.DEPOSIT, LedgerEntryType.WITHDRAWAL):
        raise RealBetError("only deposits and withdrawals can be recorded directly")
    now = now or datetime.now(UTC)
    _aware(occurred_at, "occurred_at")
    if occurred_at > now + _FUTURE_TOLERANCE:
        raise RealBetError("occurred_at cannot be in the future")
    value = _money(_decimal(amount, "amount"))
    if value <= 0:
        raise RealBetError("amount must be greater than zero")

    _lock_account(session, account)
    # A retry of an already-recorded key returns the original entry (checked
    # for an exact match by the ledger) and is neither re-validated nor
    # audited a second time.
    replay = idempotency_key is not None and session.execute(
        select(BankrollLedgerEntry.id).where(
            BankrollLedgerEntry.account == account,
            BankrollLedgerEntry.idempotency_key == idempotency_key,
        )
    ).first() is not None
    if kind is LedgerEntryType.WITHDRAWAL and not replay:
        summary = bankroll_summary(session, account)
        if value > summary.available:
            raise RealBetError(
                f"withdrawal of {value} exceeds the available bankroll of "
                f"{summary.available} (stakes on open bets are reserved)"
            )
    signed = value if kind is LedgerEntryType.DEPOSIT else -value
    try:
        entry = append_ledger_entry(
            session,
            account=account,
            entry_type=kind,
            amount=signed,
            occurred_at=occurred_at,
            reason=kind.value,
            reference=reference,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise RealBetError(str(exc)) from exc
    if replay:
        return entry
    _audit(
        session,
        action=f"bankroll_{kind.value}",
        entity_type="bankroll_ledger_entries",
        entity_id=entry.id,
        summary=f"{kind.value} of {value} {get_settings().real_money_currency}",
        payload={"amount": str(value), "reference": reference},
        occurred_at=now,
    )
    return entry


# --------------------------------------------------------------------------
# Placing a bet
# --------------------------------------------------------------------------

def place_real_bet(
    session: Session,
    *,
    accumulator_id: uuid.UUID,
    bookmaker: str,
    stake: Decimal | float | str,
    taken_odds: Decimal | float | str,
    placed_at: datetime,
    currency: str,
    bookmaker_reference: str | None = None,
    notes: str | None = None,
    idempotency_key: str | None = None,
    account: str = DEFAULT_ACCOUNT,
    now: datetime | None = None,
) -> RealBet:
    now = now or datetime.now(UTC)
    _aware(placed_at, "placed_at")
    bookmaker = bookmaker.strip()
    bookmaker_reference = (bookmaker_reference or "").strip() or None
    if not bookmaker:
        raise RealBetError("bookmaker is required")
    account_currency = get_settings().real_money_currency
    if currency != account_currency:
        raise RealBetError(f"this bankroll is kept in {account_currency}, not {currency}")
    stake_value = _money(_decimal(stake, "stake"))
    if stake_value <= 0:
        raise RealBetError("stake must be greater than zero")
    odds_value = _decimal(taken_odds, "taken_odds").quantize(_ODDS_QUANTUM)
    if odds_value <= 1:
        raise RealBetError("taken odds must be greater than 1")
    if placed_at > now + _FUTURE_TOLERANCE:
        raise RealBetError("placed_at cannot be in the future")

    _lock_account(session, account)

    if idempotency_key is not None:
        existing = session.execute(
            select(RealBet).where(
                RealBet.account == account, RealBet.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if existing is not None:
            same = (
                existing.accumulator_id == accumulator_id
                and existing.bookmaker == bookmaker
                and existing.bookmaker_reference == bookmaker_reference
                and _money(existing.stake) == stake_value
                and Decimal(str(existing.taken_odds)).quantize(_ODDS_QUANTUM) == odds_value
                and _as_utc(existing.placed_at) == placed_at
            )
            if not same:
                raise RealBetError(
                    "idempotency_key was already used for a different bet; refusing to overwrite it"
                )
            return existing

    ticket = session.execute(
        select(Accumulator)
        .where(Accumulator.id == accumulator_id)
        .options(selectinload(Accumulator.legs).selectinload(AccumulatorLeg.fixture))
    ).scalar_one_or_none()
    if ticket is None:
        raise RealBetNotFound("published ticket not found")
    if ticket.status is TicketStatus.VOID:
        raise RealBetError("this ticket was voided and cannot be staked")
    if not ticket.legs:
        raise RealBetError("this ticket has no legs")
    if placed_at < _as_utc(ticket.published_at):
        raise RealBetError("placed_at is before the ticket was published")
    first_kickoff = min(_as_utc(leg.fixture.kickoff_utc) for leg in ticket.legs)
    if placed_at >= first_kickoff:
        raise RealBetError(
            "placed_at is at or after the first kickoff; in-play bets are not the model's pick"
        )

    if bookmaker_reference is not None and session.execute(
        select(RealBet.id).where(
            RealBet.account == account,
            RealBet.bookmaker == bookmaker,
            RealBet.bookmaker_reference == bookmaker_reference,
        )
    ).first():
        raise RealBetError(
            f"a bet with {bookmaker} slip reference {bookmaker_reference} is already recorded"
        )

    position = bankroll_summary(session, account)
    if stake_value > position.available:
        raise RealBetError(
            f"stake of {stake_value} exceeds the available bankroll of {position.available} "
            f"{account_currency}; record a deposit first"
        )

    bet = RealBet(
        account=account,
        accumulator_id=ticket.id,
        bookmaker=bookmaker,
        bookmaker_reference=bookmaker_reference,
        currency=currency,
        stake=stake_value,
        taken_odds=odds_value,
        placed_at=placed_at,
        notes=(notes or "").strip() or None,
        idempotency_key=idempotency_key,
    )
    session.add(bet)
    session.flush()
    _audit(
        session,
        action="real_bet_placed",
        entity_type="real_bets",
        entity_id=bet.id,
        summary=f"{stake_value} {currency} at {odds_value} with {bookmaker} on ticket {ticket.id}",
        payload={
            "accumulator_id": str(ticket.id),
            "stake": str(stake_value),
            "taken_odds": str(odds_value),
            "published_odds": str(ticket.combined_odds),
            "bookmaker": bookmaker,
            "bookmaker_reference": bookmaker_reference,
        },
        occurred_at=now,
    )
    return bet


# --------------------------------------------------------------------------
# Settling a bet
# --------------------------------------------------------------------------

def effective_settlement(bet: RealBet) -> RealBetSettlement | None:
    """The settlement no other row supersedes (the current truth), if any."""

    superseded = {s.supersedes_id for s in bet.settlements if s.supersedes_id}
    current = [s for s in bet.settlements if s.id not in superseded]
    return current[0] if current else None


def _check_payout(outcome: RealBetOutcome, payout: Decimal, stake: Decimal) -> None:
    if outcome is RealBetOutcome.LOST and payout != 0:
        raise RealBetError("a lost bet pays out 0")
    if outcome is RealBetOutcome.VOID and payout != stake:
        raise RealBetError(f"a void bet returns exactly the stake ({stake})")
    if outcome is RealBetOutcome.WON and payout <= stake:
        raise RealBetError(
            f"a won bet pays out more than the stake ({stake}); "
            "use 'void' if only the stake came back"
        )


def settle_real_bet(
    session: Session,
    *,
    bet_id: uuid.UUID,
    outcome: RealBetOutcome,
    payout: Decimal | float | str,
    settled_at: datetime,
    supersedes_id: uuid.UUID | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> RealBetSettlement:
    now = now or datetime.now(UTC)
    _aware(settled_at, "settled_at")
    payout_value = _money(_decimal(payout, "payout"))
    if payout_value < 0:
        raise RealBetError("payout cannot be negative")
    reason = (reason or "").strip() or None

    bet = session.execute(
        select(RealBet).where(RealBet.id == bet_id).options(selectinload(RealBet.settlements))
    ).scalar_one_or_none()
    if bet is None:
        raise RealBetNotFound("real bet not found")
    _lock_account(session, bet.account)
    session.refresh(bet, attribute_names=["settlements"])

    stake = _money(bet.stake)
    _check_payout(outcome, payout_value, stake)
    if settled_at < _as_utc(bet.placed_at):
        raise RealBetError("settled_at is before the bet was placed")
    if settled_at > now + _FUTURE_TOLERANCE:
        raise RealBetError("settled_at cannot be in the future")

    current = effective_settlement(bet)
    if supersedes_id is None:
        if current is not None:
            raise RealBetError(
                "this bet is already settled; send a correction with supersedes_id "
                f"{current.id} and a reason"
            )
        previous_profit = Decimal(0)
    else:
        if current is None or current.id != supersedes_id:
            raise RealBetError("supersedes_id must be the bet's current settlement")
        if reason is None:
            raise RealBetError("a correction needs a reason")
        previous_profit = _money(current.payout) - stake

    settlement_id = uuid.uuid4()
    delta = (payout_value - stake) - previous_profit
    ledger_entry = None
    if delta != 0:
        try:
            ledger_entry = append_ledger_entry(
                session,
                account=bet.account,
                entry_type=LedgerEntryType.SETTLEMENT,
                amount=delta,
                occurred_at=now,
                reason="real bet correction" if supersedes_id else "real bet settled",
                reference=f"real_bet:{bet.id}",
                idempotency_key=f"real_bet_settlement:{settlement_id}",
            )
        except ValueError as exc:
            raise RealBetError(str(exc)) from exc

    settlement = RealBetSettlement(
        id=settlement_id,
        real_bet_id=bet.id,
        outcome=outcome,
        payout=payout_value,
        settled_at=settled_at,
        supersedes_id=supersedes_id,
        reason=reason,
        ledger_entry_id=ledger_entry.id if ledger_entry else None,
    )
    session.add(settlement)
    session.flush()
    _audit(
        session,
        action="real_bet_correction" if supersedes_id else "real_bet_settled",
        entity_type="real_bet_settlements",
        entity_id=settlement.id,
        summary=f"bet {bet.id} {outcome.value}, payout {payout_value}, ledger {delta:+}",
        payload={
            "real_bet_id": str(bet.id),
            "outcome": outcome.value,
            "payout": str(payout_value),
            "ledger_delta": str(delta),
            "supersedes_id": str(supersedes_id) if supersedes_id else None,
            "reason": reason,
        },
        occurred_at=now,
    )
    session.refresh(bet, attribute_names=["settlements"])
    return settlement


@dataclass(frozen=True)
class RealBetResults:
    """Realised results over every settled real bet (effective settlements)."""

    currency: str
    n_bets: int
    n_open: int
    n_won: int
    n_lost: int
    n_void: int
    n_cashed_out: int
    settled_stake: Decimal
    settled_profit: Decimal

    @property
    def roi(self) -> Decimal | None:
        """Profit over stake of settled bets; void bets return their stake."""
        return self.settled_profit / self.settled_stake if self.settled_stake else None


def real_bet_results(session: Session, account: str = DEFAULT_ACCOUNT) -> RealBetResults:
    bets = session.scalars(
        select(RealBet)
        .where(RealBet.account == account)
        .options(selectinload(RealBet.settlements))
    ).all()
    counts = dict.fromkeys(RealBetOutcome, 0)
    stake_total = Decimal(0)
    profit_total = Decimal(0)
    n_open = 0
    for bet in bets:
        current = effective_settlement(bet)
        if current is None:
            n_open += 1
            continue
        counts[current.outcome] += 1
        if current.outcome is not RealBetOutcome.VOID:
            stake_total += _money(bet.stake)
        profit_total += _money(current.payout) - _money(bet.stake)
    return RealBetResults(
        currency=get_settings().real_money_currency,
        n_bets=len(bets),
        n_open=n_open,
        n_won=counts[RealBetOutcome.WON],
        n_lost=counts[RealBetOutcome.LOST],
        n_void=counts[RealBetOutcome.VOID],
        n_cashed_out=counts[RealBetOutcome.CASHED_OUT],
        settled_stake=_money(stake_total),
        settled_profit=_money(profit_total),
    )


def list_real_bets(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    account: str = DEFAULT_ACCOUNT,
) -> tuple[list[RealBet], int]:
    """Newest-first page of bets; ``status`` is ``open`` or ``settled``."""

    stmt = select(RealBet).where(RealBet.account == account)
    settled = select(RealBetSettlement.real_bet_id)
    if status == "open":
        stmt = stmt.where(RealBet.id.not_in(settled))
    elif status == "settled":
        stmt = stmt.where(RealBet.id.in_(settled))
    elif status is not None:
        raise RealBetError("status must be 'open' or 'settled'")
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.options(selectinload(RealBet.settlements))
        .order_by(RealBet.placed_at.desc(), RealBet.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), int(total)


__all__ = [
    "BankrollSummary",
    "DEFAULT_ACCOUNT",
    "RealBetError",
    "RealBetNotFound",
    "bankroll_summary",
    "effective_settlement",
    "list_real_bets",
    "open_exposure",
    "place_real_bet",
    "real_bet_results",
    "record_cash_flow",
    "settle_real_bet",
]
