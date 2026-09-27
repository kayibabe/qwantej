"""Real-money endpoints: bankroll cash flows, real bets and their settlements.

These are the API's first write endpoints. They are gated by the same API key
as every other route, validate strictly (unknown fields rejected), and commit
only after the service layer's rules pass. Rule violations are 422 with a
plain-language message; a missing bet or ticket is 404.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models import LedgerEntryType, RealBet
from backend.schemas.real_bets import (
    BankrollSummaryOut,
    CashFlowIn,
    LedgerEntryOut,
    RealBetIn,
    RealBetOut,
    RealBetPage,
    RealBetSettlementIn,
    RealBetSettlementOut,
)
from backend.services import real_bets as svc

router = APIRouter(tags=["real-money"], dependencies=[RequireApiKey])

_MAX_LIMIT = 100


def _serialize(bet: RealBet) -> RealBetOut:
    current = svc.effective_settlement(bet)
    profit = None if current is None else Decimal(str(current.payout)) - Decimal(str(bet.stake))
    return RealBetOut(
        id=bet.id,
        accumulator_id=bet.accumulator_id,
        bookmaker=bet.bookmaker,
        bookmaker_reference=bet.bookmaker_reference,
        currency=bet.currency,
        stake=Decimal(str(bet.stake)),
        taken_odds=Decimal(str(bet.taken_odds)),
        placed_at=bet.placed_at,
        notes=bet.notes,
        created_at=bet.created_at,
        status="open" if current is None else "settled",
        settlement=None if current is None else RealBetSettlementOut.model_validate(current),
        profit_loss=profit,
        history=[RealBetSettlementOut.model_validate(s) for s in bet.settlements],
    )


def _commit(db: DbDep) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # A concurrent duplicate slipped past the service's pre-checks.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this record conflicts with one already saved (duplicate slip or key)",
        ) from exc


def _rule_error(exc: svc.RealBetError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if isinstance(exc, svc.RealBetNotFound)
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(status_code=code, detail=str(exc))


def _load(db: DbDep, bet_id: uuid.UUID) -> RealBet:
    bet = db.execute(
        select(RealBet).where(RealBet.id == bet_id).options(selectinload(RealBet.settlements))
    ).scalar_one_or_none()
    if bet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="real bet not found")
    return bet


# --- Bankroll ---------------------------------------------------------------

@router.get("/bankroll", response_model=BankrollSummaryOut)
def get_bankroll(db: DbDep) -> BankrollSummaryOut:
    """Settled balance, stakes riding on open bets, and what is free to stake."""
    s = svc.bankroll_summary(db)
    return BankrollSummaryOut(**s.__dict__)


def _cash_flow(db: DbDep, body: CashFlowIn, kind: LedgerEntryType) -> LedgerEntryOut:
    try:
        entry = svc.record_cash_flow(
            db, kind=kind, amount=body.amount, occurred_at=body.occurred_at,
            reference=body.reference, idempotency_key=body.idempotency_key,
        )
    except svc.RealBetError as exc:
        db.rollback()
        raise _rule_error(exc) from exc
    _commit(db)
    return LedgerEntryOut.model_validate(entry)


@router.post("/bankroll/deposits", response_model=LedgerEntryOut, status_code=201)
def post_deposit(body: CashFlowIn, db: DbDep) -> LedgerEntryOut:
    return _cash_flow(db, body, LedgerEntryType.DEPOSIT)


@router.post("/bankroll/withdrawals", response_model=LedgerEntryOut, status_code=201)
def post_withdrawal(body: CashFlowIn, db: DbDep) -> LedgerEntryOut:
    return _cash_flow(db, body, LedgerEntryType.WITHDRAWAL)


# --- Real bets --------------------------------------------------------------

@router.post("/real-bets", response_model=RealBetOut, status_code=201)
def post_real_bet(body: RealBetIn, db: DbDep) -> RealBetOut:
    try:
        bet = svc.place_real_bet(db, **body.model_dump())
    except svc.RealBetError as exc:
        db.rollback()
        raise _rule_error(exc) from exc
    bet_id = bet.id
    _commit(db)
    return _serialize(_load(db, bet_id))


@router.get("/real-bets", response_model=RealBetPage)
def get_real_bets(
    db: DbDep,
    status_filter: Annotated[str | None, Query(alias="status", pattern="^(open|settled)$")] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RealBetPage:
    rows, total = svc.list_real_bets(db, status=status_filter, limit=limit, offset=offset)
    return RealBetPage(items=[_serialize(b) for b in rows], total=total, limit=limit, offset=offset)


@router.get("/real-bets/{bet_id}", response_model=RealBetOut)
def get_real_bet(bet_id: uuid.UUID, db: DbDep) -> RealBetOut:
    return _serialize(_load(db, bet_id))


@router.post(
    "/real-bets/{bet_id}/settlements", response_model=RealBetSettlementOut, status_code=201
)
def post_settlement(
    bet_id: uuid.UUID, body: RealBetSettlementIn, db: DbDep
) -> RealBetSettlementOut:
    try:
        settlement = svc.settle_real_bet(db, bet_id=bet_id, **body.model_dump())
    except svc.RealBetError as exc:
        db.rollback()
        raise _rule_error(exc) from exc
    out = RealBetSettlementOut.model_validate(settlement)
    _commit(db)
    return out
