"""Real-money bets placed by the owner, and their bookmaker settlements.

Qwantej publishes paper tickets (`Accumulator`, always ``paper_only``); these
tables record what the owner then *actually* staked at a bookmaker on one of
those tickets. They are kept strictly apart from the paper archive so paper
performance and real-money performance are never blended.

- `RealBet` — the placement facts: which published ticket (exact legs, no
  partial tickets), bookmaker, slip reference, stake and the price actually
  taken. Immutable once written.
- `RealBetSettlement` — what the bookmaker paid out. The bookmaker's payout is
  authoritative (its void-leg and cash-out rules differ from the model's).
  Append-only: a correction is a new row that ``supersedes`` the prior one.

Money moves into the bankroll ledger only at settlement (profit/loss as a
``settlement`` entry). Open exposure is the sum of stakes on unsettled bets,
which is what `record_risk_state` expects as ``committed_exposure``.
Database triggers forbid UPDATE, DELETE and TRUNCATE on both tables.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class RealBetOutcome(enum.StrEnum):
    WON = "won"  # includes wins paid at reduced odds after a void leg
    LOST = "lost"
    VOID = "void"  # whole bet voided; stake returned
    CASHED_OUT = "cashed_out"


class RealBet(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "real_bets"
    __table_args__ = (
        CheckConstraint("stake > 0", name="ck_real_bets_stake_pos"),
        CheckConstraint("taken_odds > 1", name="ck_real_bets_taken_odds_gt_1"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_real_bets_currency_iso",
        ),
        UniqueConstraint(
            "account", "bookmaker", "bookmaker_reference",
            name="uq_real_bets_bookmaker_reference",
        ),
        UniqueConstraint("account", "idempotency_key", name="uq_real_bets_idempotency"),
    )

    account: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Exact-legs rule: a real bet is always one whole published ticket.
    accumulator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accumulators.id"), nullable=False, index=True
    )
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False)
    # The bookmaker's bet-slip / receipt id. NULL allowed (not every slip has
    # one), so the uniqueness guard only applies when it is given.
    bookmaker_reference: Mapped[str | None] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    stake: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    # Combined price actually taken; compare with accumulators.combined_odds
    # (the published price) to measure slippage.
    taken_odds: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    settlements: Mapped[list["RealBetSettlement"]] = relationship(
        back_populates="real_bet", order_by="RealBetSettlement.created_at"
    )


class RealBetSettlement(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "real_bet_settlements"
    __table_args__ = (
        CheckConstraint("payout >= 0", name="ck_real_bet_settlements_payout_nonneg"),
        # A correction supersedes exactly one row, and a row can be superseded
        # at most once, so each bet has a single linear settlement history.
        UniqueConstraint("supersedes_id", name="uq_real_bet_settlements_supersedes"),
        UniqueConstraint("ledger_entry_id", name="uq_real_bet_settlements_ledger_entry_id"),
        # Only one original (non-correction) settlement per bet.
        Index(
            "uq_real_bet_settlements_one_original",
            "real_bet_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NULL"),
            sqlite_where=text("supersedes_id IS NULL"),
        ),
    )

    real_bet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("real_bets.id"), nullable=False, index=True
    )
    outcome: Mapped[RealBetOutcome] = mapped_column(
        Enum(
            RealBetOutcome,
            name="real_bet_outcome",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    # Total returned by the bookmaker, stake included (0 for a loss).
    payout: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    # When the bookmaker settled the bet (may be earlier than when recorded).
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("real_bet_settlements.id")
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    # The ledger entry this settlement (or correction delta) posted. NULL only
    # for a correction that does not change profit/loss.
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bankroll_ledger_entries.id")
    )

    real_bet: Mapped["RealBet"] = relationship(back_populates="settlements")
