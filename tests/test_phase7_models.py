"""Structural persistence coverage for the Phase 7 bankroll ledger."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Base, LedgerEntryType, RiskStateSnapshot
from backend.services.bankroll import (
    append_ledger_entry,
    current_bankroll,
    record_risk_state,
)
from qwantej.bankroll import OperatingState

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


def test_risk_state_snapshot_derives_drawdown(session: Session) -> None:
    snapshot = record_risk_state(
        session, account="primary", evaluated_as_of=NOW,
        current_bankroll_amount=850, peak_bankroll=1000, available_bankroll=800,
        committed_exposure=50, daily_exposure=40,
        operating_state=OperatingState.CAUTION, policy_version="risk-v1",
    )
    session.commit()
    session.expire_all()
    stored = session.query(RiskStateSnapshot).one()
    assert stored.id == snapshot.id
    assert float(stored.drawdown_fraction) == pytest.approx(0.15)
    assert stored.operating_state.value == "caution"


def test_risk_state_rejects_available_above_current(session: Session) -> None:
    with pytest.raises(ValueError, match="available_bankroll"):
        record_risk_state(
            session, account="primary", evaluated_as_of=NOW,
            current_bankroll_amount=500, peak_bankroll=1000, available_bankroll=600,
            committed_exposure=0, daily_exposure=0,
            operating_state=OperatingState.NORMAL, policy_version="risk-v1",
        )


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
