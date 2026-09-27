"""Request/response schemas for the real-money endpoints.

Money is `Decimal` (serialised as an exact string in JSON), never float, so
amounts are not rounded on the way in or out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.models import RealBetOutcome

_KEY = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class CashFlowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    occurred_at: AwareDatetime
    reference: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = _KEY


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    entry_type: str
    amount: Decimal
    balance_after: Decimal
    occurred_at: datetime
    reference: str | None
    reason: str


class BankrollSummaryOut(BaseModel):
    account: str
    currency: str
    balance: Decimal
    open_exposure: Decimal
    available: Decimal
    open_bets: int


class RealBetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accumulator_id: uuid.UUID
    bookmaker: str = Field(min_length=1, max_length=80)
    bookmaker_reference: str | None = Field(default=None, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    stake: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    taken_odds: Decimal = Field(gt=1, max_digits=10, decimal_places=4)
    placed_at: AwareDatetime
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = _KEY


class RealBetSettlementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: RealBetOutcome
    payout: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    settled_at: AwareDatetime
    supersedes_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=255)


class RealBetSettlementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outcome: RealBetOutcome
    payout: Decimal
    settled_at: datetime
    supersedes_id: uuid.UUID | None
    reason: str | None
    ledger_entry_id: uuid.UUID | None
    created_at: datetime


class RealBetOut(BaseModel):
    id: uuid.UUID
    accumulator_id: uuid.UUID
    bookmaker: str
    bookmaker_reference: str | None
    currency: str
    stake: Decimal
    taken_odds: Decimal
    placed_at: datetime
    notes: str | None
    created_at: datetime
    status: str  # "open" or "settled"
    # The current (non-superseded) settlement, and its profit/loss.
    settlement: RealBetSettlementOut | None
    profit_loss: Decimal | None
    history: list[RealBetSettlementOut]


class RealBetResultsOut(BaseModel):
    """Realised results of real-money bets, in the bankroll currency."""

    currency: str
    n_bets: int
    n_open: int
    n_won: int
    n_lost: int
    n_void: int
    n_cashed_out: int
    settled_stake: Decimal  # stakes on settled bets except voids (refunded)
    settled_profit: Decimal
    roi: Decimal | None


class RealBetPage(BaseModel):
    items: list[RealBetOut]
    total: int
    limit: int
    offset: int
