"""Append-only bankroll ledger operations and risk-state archival.

The current bankroll is *derived* from the immutable ledger, never stored as a
mutable figure, so it can always be reconstructed and audited. Entries are
recorded in chronological order per account; a per-account lock and an optional
idempotency key make concurrent or retried appends safe, so each row's
``balance_after`` stays a coherent running total.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.models import (
    BankrollLedgerEntry,
    LedgerEntryType,
    RiskState,
    RiskStateSnapshot,
)
from qwantej.bankroll import (
    DEFAULT_RISK_POLICY,
    RiskPolicy,
    classify_state,
)


def current_bankroll(session: Session, account: str = "primary") -> Decimal:
    """Settled bankroll for an account: the sum of every ledger amount."""

    total = session.execute(
        select(func.coalesce(func.sum(BankrollLedgerEntry.amount), 0)).where(
            BankrollLedgerEntry.account == account
        )
    ).scalar_one()
    return Decimal(str(total))


def _peak_bankroll(session: Session, account: str) -> Decimal:
    """High-water mark of the running balance for drawdown measurement."""

    peak = session.execute(
        select(func.max(BankrollLedgerEntry.balance_after)).where(
            BankrollLedgerEntry.account == account
        )
    ).scalar_one()
    return Decimal(str(peak)) if peak is not None else Decimal(0)


def _lock_account(session: Session, account: str) -> None:
    """Serialise appends for one account (PostgreSQL advisory lock).

    SQLite has a single writer, so no explicit lock is needed there.
    """

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:account)::bigint)"),
            {"account": account},
        )


def append_ledger_entry(
    session: Session,
    *,
    account: str,
    entry_type: LedgerEntryType,
    amount: Decimal | float | int,
    occurred_at: datetime,
    reason: str,
    reference: str | None = None,
    idempotency_key: str | None = None,
) -> BankrollLedgerEntry:
    """Append one settled cashflow, deriving ``balance_after`` from history.

    Passing the same ``idempotency_key`` twice for an account returns the
    existing entry instead of double-counting a retried event.
    """

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

    # Serialise before reading the running total so a concurrent append cannot
    # compute balance_after from a stale sum.
    _lock_account(session, account)

    if idempotency_key is not None:
        existing = session.execute(
            select(BankrollLedgerEntry).where(
                BankrollLedgerEntry.account == account,
                BankrollLedgerEntry.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

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
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    session.flush()
    return entry


def record_risk_state(
    session: Session,
    *,
    account: str,
    evaluated_as_of: datetime,
    committed_exposure: Decimal | float,
    daily_exposure: Decimal | float,
    policy: RiskPolicy = DEFAULT_RISK_POLICY,
    rolling_volatility: Decimal | float | None = None,
    calibration_failure: bool = False,
    severe_drift: bool = False,
    drift: bool = False,
    soft_deterioration: bool = False,
    diagnostics: dict | None = None,
) -> RiskStateSnapshot:
    """Persist an immutable risk-state evaluation derived from the ledger.

    Current bankroll, peak, available bankroll, drawdown and operating state are
    all *derived* here — from the ledger and the policy — rather than trusted
    from the caller. Only genuinely external figures (committed/daily exposure,
    and the qualitative drift/calibration signals) are supplied.
    """

    if not account.strip():
        raise ValueError("account must not be blank")
    if evaluated_as_of.tzinfo is None or evaluated_as_of.utcoffset() is None:
        raise ValueError("evaluated_as_of must be timezone-aware")
    committed = Decimal(str(committed_exposure))
    daily = Decimal(str(daily_exposure))
    if committed < 0 or daily < 0:
        raise ValueError("exposure figures must be non-negative")

    current = current_bankroll(session, account)
    peak = _peak_bankroll(session, account)
    if peak < current:  # defensive: cannot happen for a coherent ledger
        peak = current
    available = current - committed
    drawdown = (peak - current) / peak if peak > 0 else Decimal(0)
    operating_state = classify_state(
        float(drawdown),
        policy=policy,
        calibration_failure=calibration_failure,
        severe_drift=severe_drift,
        drift=drift,
        soft_deterioration=soft_deterioration,
    )

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
        policy_version=policy.version,
        diagnostics=diagnostics or {},
    )
    session.add(snapshot)
    session.flush()
    return snapshot
