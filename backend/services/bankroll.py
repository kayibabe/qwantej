"""Append-only bankroll ledger operations and risk-state archival.

The current bankroll is *derived* from the immutable ledger, never stored as a
mutable figure, so it can always be reconstructed and audited. Entries are
recorded in chronological order per account; a per-account lock and an optional
idempotency key make concurrent or retried appends safe, so each row's
``balance_after`` stays a coherent running total.

Drawdown is measured on a cash-flow-adjusted equity curve (a unit/NAV model, as
an investment fund would): deposits and withdrawals buy and sell units at the
current NAV and so never register as performance — only settlements and
adjustments move the NAV. Every risk-state figure is computed from the ledger as
it stood at ``evaluated_as_of``, under the account lock, so a snapshot can never
see the future.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

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
    OperatingState,
    RiskPolicy,
    classify_state,
)

_EXTERNAL_FLOWS = (LedgerEntryType.DEPOSIT, LedgerEntryType.WITHDRAWAL)
_DRAWDOWN_QUANTUM = Decimal("0.00000001")
# Canonical monetary precision — matches the Numeric(18, 4) storage columns so a
# value never changes when it round-trips through the database.
_MONEY_QUANTUM = Decimal("0.0001")


def _money(value: Decimal | float | int) -> Decimal:
    """Canonicalise a monetary amount to the stored 4-dp precision."""

    return Decimal(str(value)).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def current_bankroll(
    session: Session, account: str = "primary", *, as_of: datetime | None = None
) -> Decimal:
    """Settled bankroll for an account: the sum of ledger amounts up to ``as_of``.

    ``as_of=None`` sums the whole ledger (used when appending a new entry, which
    is by construction the latest event).
    """

    conditions = [BankrollLedgerEntry.account == account]
    if as_of is not None:
        conditions.append(BankrollLedgerEntry.occurred_at <= as_of)
    total = session.execute(
        select(func.coalesce(func.sum(BankrollLedgerEntry.amount), 0)).where(*conditions)
    ).scalar_one()
    return Decimal(str(total))


def _lock_account(session: Session, account: str) -> None:
    """Serialise reads/appends for one account (PostgreSQL advisory lock).

    SQLite has a single writer, so no explicit lock is needed there.
    """

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:account)::bigint)"),
            {"account": account},
        )


def _evaluate_equity(
    session: Session, account: str, as_of: datetime
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (current_balance, peak_balance, performance_drawdown) at ``as_of``.

    Drawdown is the peak-to-current decline of the NAV (performance per unit of
    capital), so external cash flows do not create or mask drawdown.
    """

    rows = session.execute(
        select(BankrollLedgerEntry.entry_type, BankrollLedgerEntry.amount)
        .where(
            BankrollLedgerEntry.account == account,
            BankrollLedgerEntry.occurred_at <= as_of,
        )
        .order_by(BankrollLedgerEntry.occurred_at, BankrollLedgerEntry.sequence)
    ).all()

    units = Decimal(0)
    nav = Decimal(1)
    peak_nav = Decimal(1)
    balance = Decimal(0)
    peak_balance = Decimal(0)
    for entry_type, amount in rows:
        amount = Decimal(str(amount))
        balance += amount
        if entry_type in _EXTERNAL_FLOWS:
            # Buy/sell units at the current NAV — no change in performance.
            if nav > 0:
                units += amount / nav
            if units <= 0:
                # Account fully redeemed: re-base performance tracking.
                units = Decimal(0)
                nav = Decimal(1)
                peak_nav = Decimal(1)
        elif units > 0:
            # Settlement/adjustment: performance moves the NAV.
            nav = balance / units
        peak_nav = max(peak_nav, nav)
        peak_balance = max(peak_balance, balance)

    drawdown = (peak_nav - nav) / peak_nav if peak_nav > 0 else Decimal(0)
    drawdown = min(Decimal(1), max(Decimal(0), drawdown)).quantize(
        _DRAWDOWN_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    return balance, peak_balance, drawdown


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
    existing entry (a safe retry) only when the request matches it exactly; a
    key reused with different details is rejected rather than silently dropped.
    """

    if not account.strip():
        raise ValueError("account must not be blank")
    if not reason.strip():
        raise ValueError("reason must not be blank")
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("occurred_at must be timezone-aware")
    # Canonicalise to stored precision up front so idempotent retries compare
    # equal after a database round-trip.
    amount = _money(amount)
    if amount == 0:
        raise ValueError("ledger amount must be non-zero at 4-dp precision")
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
            _assert_idempotent_match(
                existing, entry_type, amount, occurred_at, reason, reference
            )
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
    if balance_after < 0:
        raise ValueError("ledger balance cannot go negative")

    # Monotonic per-account append counter, assigned under the account lock so
    # it reflects true insertion order regardless of equal timestamps.
    next_sequence = (
        session.execute(
            select(func.coalesce(func.max(BankrollLedgerEntry.sequence), 0)).where(
                BankrollLedgerEntry.account == account
            )
        ).scalar_one()
        + 1
    )
    entry = BankrollLedgerEntry(
        account=account,
        sequence=next_sequence,
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


def _assert_idempotent_match(
    existing: BankrollLedgerEntry,
    entry_type: LedgerEntryType,
    amount: Decimal,
    occurred_at: datetime,
    reason: str,
    reference: str | None,
) -> None:
    stored_occurred = existing.occurred_at
    if stored_occurred.tzinfo is None:
        stored_occurred = stored_occurred.replace(tzinfo=UTC)
    mismatched = (
        existing.entry_type is not entry_type
        or _money(existing.amount) != amount
        or stored_occurred != occurred_at
        or existing.reason != reason
        or existing.reference != reference
    )
    if mismatched:
        raise ValueError(
            "idempotency_key reused with a different event; refusing to discard it"
        )


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
    """Persist an immutable, point-in-time risk-state evaluation.

    Current/peak/available bankroll, drawdown and operating state are all derived
    from the ledger as it stood at ``evaluated_as_of`` (under the account lock)
    and from the policy — never trusted from the caller. An exposure breach
    (committed exposure exceeding bankroll) or a non-positive bankroll fails
    closed into REVIEW, and available bankroll is never stored negative.
    """

    if not account.strip():
        raise ValueError("account must not be blank")
    if evaluated_as_of.tzinfo is None or evaluated_as_of.utcoffset() is None:
        raise ValueError("evaluated_as_of must be timezone-aware")
    committed = Decimal(str(committed_exposure))
    daily = Decimal(str(daily_exposure))
    if committed < 0 or daily < 0:
        raise ValueError("exposure figures must be non-negative")

    _lock_account(session, account)
    current, peak, drawdown = _evaluate_equity(session, account, evaluated_as_of)
    if current < 0:
        # A negative ledger balance is an accounting error, not a risk state.
        raise ValueError("ledger balance is negative; cannot evaluate risk state")

    raw_available = current - committed
    available = max(Decimal(0), raw_available)
    exposure_breach = raw_available < 0
    no_capital = current <= 0

    operating_state = classify_state(
        float(drawdown),
        policy=policy,
        calibration_failure=calibration_failure,
        severe_drift=severe_drift,
        drift=drift,
        soft_deterioration=soft_deterioration,
    )
    if exposure_breach or no_capital:
        operating_state = OperatingState.REVIEW

    snapshot_diagnostics = dict(diagnostics or {})
    if exposure_breach:
        snapshot_diagnostics["exposure_breach"] = True
        snapshot_diagnostics["raw_available_bankroll"] = str(raw_available)
    if no_capital:
        snapshot_diagnostics["no_capital"] = True

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
        diagnostics=snapshot_diagnostics,
    )
    session.add(snapshot)
    session.flush()
    return snapshot
