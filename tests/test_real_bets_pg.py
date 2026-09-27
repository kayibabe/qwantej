"""Postgres-only guarantees for real-money tables (triggers, partial unique index).

Runs the real service flow against the dev Postgres container inside one
transaction that is rolled back, so nothing persists. Each expected failure is
wrapped in a SAVEPOINT so it does not abort the outer transaction. Skipped
when Postgres is unreachable or not migrated to include these tables.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import LedgerEntryType, RealBetOutcome, RealBetSettlement
from backend.services import real_bets as svc
from backend.services.bankroll import current_bankroll
from tests.test_real_bets import NOW, PUBLISHED, _ticket

DATABASE_URL = get_settings().database_url
# Isolated account so the test never mixes with any real rows in the dev DB.
ACCOUNT = f"pytest-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("real-money triggers are Postgres-only")
    eng = create_engine(DATABASE_URL)
    try:
        with eng.connect() as conn:
            present = conn.execute(text(
                "select count(*) from pg_trigger where tgname in "
                "('trg_real_bets_no_update', 'trg_real_bets_no_delete', "
                "'trg_real_bet_settlements_no_update', 'trg_real_bet_settlements_no_delete')"
            )).scalar_one()
    except OperationalError:
        pytest.skip("dev Postgres not reachable (docker compose up -d db)")
    if present != 4:
        pytest.skip("real-money triggers absent; run: alembic upgrade head")
    return eng


@pytest.fixture()
def session(engine):
    conn = engine.connect()
    outer = conn.begin()
    sess = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield sess
    finally:
        sess.close()
        outer.rollback()
        conn.close()


def _settled_bet(session: Session):
    ticket = _ticket(session)
    svc.record_cash_flow(session, kind=LedgerEntryType.DEPOSIT, amount="10000",
                         occurred_at=PUBLISHED - timedelta(hours=1), account=ACCOUNT, now=NOW)
    bet = svc.place_real_bet(
        session, accumulator_id=ticket.id, bookmaker="Premier Bet", stake="2500",
        taken_odds="3.10", placed_at=NOW - timedelta(minutes=30), currency="MWK",
        bookmaker_reference=f"PG-{uuid.uuid4().hex[:8]}", account=ACCOUNT, now=NOW,
    )
    settlement = svc.settle_real_bet(session, bet_id=bet.id, outcome=RealBetOutcome.WON,
                                     payout="7750", settled_at=NOW, now=NOW)
    return bet, settlement


def test_service_flow_on_postgres(session) -> None:
    bet, settlement = _settled_bet(session)
    assert current_bankroll(session, ACCOUNT) == Decimal("15250")
    assert svc.bankroll_summary(session, ACCOUNT).open_exposure == 0
    assert settlement.ledger_entry_id is not None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE real_bets SET stake = 1 WHERE id = :bet",
        "DELETE FROM real_bets WHERE id = :bet",
        "UPDATE real_bet_settlements SET payout = 0 WHERE id = :settlement",
        "DELETE FROM real_bet_settlements WHERE id = :settlement",
    ],
)
def test_rows_cannot_be_edited_or_deleted(session, statement) -> None:
    bet, settlement = _settled_bet(session)
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text(statement), {"bet": bet.id, "settlement": settlement.id})


def test_database_allows_only_one_original_settlement(session) -> None:
    bet, _ = _settled_bet(session)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(RealBetSettlement(
            real_bet_id=bet.id, outcome=RealBetOutcome.LOST, payout=0, settled_at=NOW,
        ))
        session.flush()
