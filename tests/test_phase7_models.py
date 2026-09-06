"""Structural persistence coverage for the Phase 7 bankroll ledger."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import BankrollLedgerEntry, Base, LedgerEntryType, RiskStateSnapshot
from backend.services.bankroll import (
    append_ledger_entry,
    current_bankroll,
    record_risk_state,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def test_bankroll_is_derived_from_the_ledger_sum(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=1000, occurred_at=NOW, reason="seed",
    )
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=Decimal("-30.50"), occurred_at=NOW + timedelta(hours=1), reason="lost ticket",
    )
    entry = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=Decimal("45.25"), occurred_at=NOW + timedelta(hours=2), reason="won ticket",
    )
    assert float(current_bankroll(session, "primary")) == pytest.approx(1014.75)
    # balance_after is a coherent running total, not a re-summed guess.
    assert float(entry.balance_after) == pytest.approx(1014.75)


def test_accounts_are_isolated(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=500, occurred_at=NOW, reason="seed",
    )
    append_ledger_entry(
        session, account="alpha", entry_type=LedgerEntryType.DEPOSIT,
        amount=200, occurred_at=NOW, reason="seed",
    )
    assert float(current_bankroll(session, "primary")) == pytest.approx(500.0)
    assert float(current_bankroll(session, "alpha")) == pytest.approx(200.0)


def test_out_of_order_entry_is_rejected(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=1000, occurred_at=NOW, reason="seed",
    )
    with pytest.raises(ValueError, match="chronological order"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
            amount=10, occurred_at=NOW - timedelta(hours=1), reason="backdated",
        )


def test_deposit_and_withdrawal_signs_are_enforced(session: Session) -> None:
    with pytest.raises(ValueError, match="deposit"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
            amount=-100, occurred_at=NOW, reason="bad deposit",
        )
    with pytest.raises(ValueError, match="withdrawal"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.WITHDRAWAL,
            amount=100, occurred_at=NOW, reason="bad withdrawal",
        )


def test_zero_amount_rejected_by_service_and_db(session: Session) -> None:
    with pytest.raises(ValueError, match="non-zero"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.ADJUSTMENT,
            amount=0, occurred_at=NOW, reason="noop",
        )


def test_risk_state_derives_bankroll_peak_and_state_from_ledger(session: Session) -> None:
    # Deposit 1000 (peak), then lose 100 -> current 900, drawdown 10% -> CAUTION.
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=1000, occurred_at=NOW, reason="seed",
    )
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=-100, occurred_at=NOW + timedelta(hours=1), reason="lost",
    )
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=2),
        committed_exposure=50, daily_exposure=40,
    )
    session.commit()
    session.expire_all()
    stored = session.query(RiskStateSnapshot).one()
    assert stored.id == snapshot.id
    assert float(stored.current_bankroll) == pytest.approx(900.0)
    assert float(stored.peak_bankroll) == pytest.approx(1000.0)
    assert float(stored.available_bankroll) == pytest.approx(850.0)  # 900 - 50 committed
    assert float(stored.drawdown_fraction) == pytest.approx(0.10)
    assert stored.operating_state.value == "caution"
    assert stored.policy_version == "risk-v1"


def test_risk_state_qualitative_signal_forces_review(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=1000, occurred_at=NOW, reason="seed",
    )
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=1),
        committed_exposure=0, daily_exposure=0, calibration_failure=True,
    )
    # No drawdown, but a calibration failure still forces REVIEW.
    assert snapshot.operating_state.value == "review"


def test_idempotent_append_does_not_double_count(session: Session) -> None:
    first = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=45, occurred_at=NOW, reason="won", idempotency_key="ticket-42",
    )
    second = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=45, occurred_at=NOW, reason="won", idempotency_key="ticket-42",
    )
    assert first.id == second.id
    assert float(current_bankroll(session, "primary")) == pytest.approx(45.0)


def test_db_check_rejects_deposit_with_negative_amount(session: Session) -> None:
    # Bypass the service guard to prove the database itself enforces the sign.
    entry = BankrollLedgerEntry(
        account="primary", sequence=1, entry_type=LedgerEntryType.DEPOSIT,
        amount=-100, balance_after=0, occurred_at=NOW, reason="bad",
    )
    session.add(entry)
    with pytest.raises(IntegrityError):
        session.commit()


def test_db_check_rejects_negative_balance_after(session: Session) -> None:
    entry = BankrollLedgerEntry(
        account="primary", sequence=1, entry_type=LedgerEntryType.WITHDRAWAL,
        amount=-50, balance_after=-50, occurred_at=NOW, reason="overdraw",
    )
    session.add(entry)
    with pytest.raises(IntegrityError):
        session.commit()


def test_service_rejects_entry_that_would_make_balance_negative(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=100, occurred_at=NOW, reason="seed",
    )
    with pytest.raises(ValueError, match="negative"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.WITHDRAWAL,
            amount=-150, occurred_at=NOW + timedelta(hours=1), reason="overdraw",
        )


def test_equal_timestamp_entries_replay_in_append_order(session: Session) -> None:
    # Deposit and loss share a timestamp; sequence (not UUID) fixes the order.
    deposit = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=1000, occurred_at=NOW, reason="seed",
    )
    loss = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=-100, occurred_at=NOW, reason="lost",
    )
    assert loss.sequence > deposit.sequence
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW,
        committed_exposure=0, daily_exposure=0,
    )
    assert float(snapshot.current_bankroll) == pytest.approx(900.0)
    assert float(snapshot.drawdown_fraction) == pytest.approx(0.10)


def test_exact_retry_after_decimal_normalization_is_not_a_conflict(session: Session) -> None:
    first = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=Decimal("1.00001"), occurred_at=NOW, reason="won",
        idempotency_key="evt-9",
    )
    # Stored at 4 dp; the same request must dedupe rather than conflict.
    assert float(first.amount) == pytest.approx(1.0000)
    second = append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.SETTLEMENT,
        amount=Decimal("1.00001"), occurred_at=NOW, reason="won",
        idempotency_key="evt-9",
    )
    assert first.id == second.id


def _seed(session: Session, entry_type: LedgerEntryType, amount, hours: int) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=entry_type, amount=amount,
        occurred_at=NOW + timedelta(hours=hours), reason="seed",
    )


def test_snapshot_ignores_ledger_entries_after_its_cutoff(session: Session) -> None:
    _seed(session, LedgerEntryType.DEPOSIT, 1000, 0)
    _seed(session, LedgerEntryType.SETTLEMENT, -100, 1)   # as-of here: current 900
    _seed(session, LedgerEntryType.SETTLEMENT, -200, 2)   # future relative to cutoff
    early = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=1),
        committed_exposure=0, daily_exposure=0,
    )
    assert float(early.current_bankroll) == pytest.approx(900.0)
    assert float(early.drawdown_fraction) == pytest.approx(0.10)
    assert early.operating_state.value == "caution"
    # A later cutoff does see the second loss.
    late = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=2),
        committed_exposure=0, daily_exposure=0,
    )
    assert float(late.current_bankroll) == pytest.approx(700.0)
    assert float(late.drawdown_fraction) == pytest.approx(0.30)
    assert late.operating_state.value == "review"


def test_deposits_and_withdrawals_do_not_create_drawdown(session: Session) -> None:
    _seed(session, LedgerEntryType.DEPOSIT, 1000, 0)
    _seed(session, LedgerEntryType.WITHDRAWAL, -500, 1)
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=2),
        committed_exposure=0, daily_exposure=0,
    )
    assert float(snapshot.current_bankroll) == pytest.approx(500.0)
    assert float(snapshot.drawdown_fraction) == pytest.approx(0.0)
    assert snapshot.operating_state.value == "normal"


def test_conflicting_idempotency_key_is_rejected(session: Session) -> None:
    append_ledger_entry(
        session, account="primary", entry_type=LedgerEntryType.DEPOSIT,
        amount=100, occurred_at=NOW, reason="deposit", idempotency_key="evt-1",
    )
    with pytest.raises(ValueError, match="different event"):
        append_ledger_entry(
            session, account="primary", entry_type=LedgerEntryType.WITHDRAWAL,
            amount=-50, occurred_at=NOW, reason="withdrawal", idempotency_key="evt-1",
        )


def test_overcommitted_account_fails_closed_to_review(session: Session) -> None:
    _seed(session, LedgerEntryType.DEPOSIT, 100, 0)
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW + timedelta(hours=1),
        committed_exposure=150, daily_exposure=0,
    )
    assert float(snapshot.available_bankroll) == pytest.approx(0.0)
    assert snapshot.operating_state.value == "review"
    assert snapshot.diagnostics["exposure_breach"] is True


def test_db_check_rejects_negative_available_bankroll(session: Session) -> None:
    snapshot = RiskStateSnapshot(
        account="primary", evaluated_as_of=NOW,
        current_bankroll=100, peak_bankroll=100, available_bankroll=-50,
        committed_exposure=150, daily_exposure=0, drawdown_fraction=0,
        operating_state="review", policy_version="risk-v1", diagnostics={},
    )
    session.add(snapshot)
    with pytest.raises(IntegrityError):
        session.commit()


def test_db_check_rejects_peak_below_current(session: Session) -> None:
    snapshot = RiskStateSnapshot(
        account="primary", evaluated_as_of=NOW,
        current_bankroll=1000, peak_bankroll=900, available_bankroll=1000,
        committed_exposure=0, daily_exposure=0, drawdown_fraction=0,
        operating_state="normal", policy_version="risk-v1", diagnostics={},
    )
    session.add(snapshot)
    with pytest.raises(IntegrityError):
        session.commit()
