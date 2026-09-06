"""Append-only bankroll ledger operations and risk-state archival.

The current bankroll is *derived* from the immutable ledger, never stored as a
mutable figure, so it can always be reconstructed and audited. Entries are
recorded in chronological order per account so each row's ``balance_after`` is a
coherent running total.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    BankrollLedgerEntry,
    LedgerEntryType,
    RiskState,
    RiskStateSnapshot,
)
from qwantej.bankroll import OperatingState


def current_bankroll(session: Session, account: str = "primary") -> Decimal:
    """Settled bankroll for an account: the sum of every ledger amount."""

    total = session.execute(
        select(func.coalesce(func.sum(BankrollLedgerEntry.amount), 0)).where(
            BankrollLedgerEntry.account == account
        )
    ).scalar_one()
    return Decimal(str(total))


def append_ledger_entry(
    session: Session,
    *,
    account: str,
    entry_type: LedgerEntryType,
    amount: Decimal | float | int,
    occurred_at: datetime,
    reason: str,
    reference: str | None = None,
) -> BankrollLedgerEntry:
    """Append one settled cashflow, deriving ``balance_after`` from history."""

    if not account.strip():
        raise ValueError("account must not be blank")
    if not reason.strip():
        raise ValueError("reason must not be blank")
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("occurred_at must be timezone-aware")
    amount = Decimal(str(amount))
    if amount == 0:
        raise ValueError("ledger amount must be non-zero")
    if entry_type is LedgerEntryType.DEPOSIT and amount <= 0:
        raise ValueError("a deposit must be a positive amount")
    if entry_type is LedgerEntryType.WITHDRAWAL and amount >= 0:
        raise ValueError("a withdrawal must be a negative amount")

    last_occurred_at = session.execute(
        select(func.max(BankrollLedgerEntry.occurred_at)).where(
            BankrollLedgerEntry.account == account
        )
    ).scalar_one()
    if last_occurred_at is not None:
        # Some backends (e.g. SQLite) return naive datetimes; treat stored
        # timestamps as UTC per the base-model convention before comparing.
        if last_occurred_at.tzinfo is None:
            last_occurred_at = last_occurred_at.replace(tzinfo=UTC)
        if occurred_at < last_occurred_at:
            raise ValueError("ledger entries must be appended in chronological order")

    balance_after = current_bankroll(session, account) + amount
    entry = BankrollLedgerEntry(
        account=account,
        entry_type=entry_type,
        amount=amount,
        balance_after=balance_after,
        occurred_at=occurred_at,
        reason=reason,
        reference=reference,
    )
    session.add(entry)
    session.flush()
    return entry


def record_risk_state(
    session: Session,
    *,
    account: str,
    evaluated_as_of: datetime,
    current_bankroll_amount: Decimal | float,
    peak_bankroll: Decimal | float,
    available_bankroll: Decimal | float,
    committed_exposure: Decimal | float,
    daily_exposure: Decimal | float,
    operating_state: OperatingState,
    policy_version: str,
    rolling_volatility: Decimal | float | None = None,
    diagnostics: dict | None = None,
) -> RiskStateSnapshot:
    """Persist an immutable point-in-time risk-state evaluation."""

    if not account.strip() or not policy_version.strip():
        raise ValueError("account and policy_version must not be blank")
    if evaluated_as_of.tzinfo is None or evaluated_as_of.utcoffset() is None:
        raise ValueError("evaluated_as_of must be timezone-aware")
    current = Decimal(str(current_bankroll_amount))
    peak = Decimal(str(peak_bankroll))
    available = Decimal(str(available_bankroll))
    committed = Decimal(str(committed_exposure))
    daily = Decimal(str(daily_exposure))
    if peak < current:
        raise ValueError("peak_bankroll cannot be below current_bankroll")
    if available > current:
        raise ValueError("available_bankroll cannot exceed current_bankroll")
    if committed < 0 or daily < 0:
        raise ValueError("exposure figures must be non-negative")
    drawdown = (peak - current) / peak if peak > 0 else Decimal(0)

    snapshot = RiskStateSnapshot(
        account=account,
        evaluated_as_of=evaluated_as_of,
        current_bankroll=current,
        peak_bankroll=peak,
        available_bankroll=available,
        committed_exposure=committed,
        daily_exposure=daily,
        drawdown_fraction=drawdown,
        rolling_volatility=(
            None if rolling_volatility is None else Decimal(str(rolling_volatility))
        ),
        operating_state=RiskState(operating_state.value),
        policy_version=policy_version,
        diagnostics=diagnostics or {},
    )
    session.add(snapshot)
    session.flush()
    return snapshot
