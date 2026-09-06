"""Append-only bankroll ledger and immutable risk-state snapshots.

The ledger is Qwantej's financial institutional memory (framework §34, §38):
settled cashflows are recorded once and never mutated, so the current bankroll
is always the reproducible sum of an auditable history rather than a figure
someone can quietly edit. Risk-state snapshots capture the drawdown-aware
operating state at a point in time. Both tables are append-only; database
triggers forbid UPDATE, DELETE and TRUNCATE.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class LedgerEntryType(enum.StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    SETTLEMENT = "settlement"
    ADJUSTMENT = "adjustment"


class RiskState(enum.StrEnum):
    NORMAL = "normal"
    CAUTION = "caution"
    DEFENSIVE = "defensive"
    REVIEW = "review"


class BankrollLedgerEntry(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "bankroll_ledger_entries"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_ledger_amount_nonzero"),
        CheckConstraint(
            "(entry_type <> 'deposit' OR amount > 0) "
            "AND (entry_type <> 'withdrawal' OR amount < 0)",
            name="ck_ledger_sign_by_type",
        ),
        UniqueConstraint(
            "account", "occurred_at", "id", name="uq_ledger_account_occurred"
        ),
        UniqueConstraint("account", "idempotency_key", name="uq_ledger_idempotency"),
    )

    account: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True, default="primary"
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(
            LedgerEntryType,
            name="ledger_entry_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class RiskStateSnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "risk_state_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account", "evaluated_as_of", "policy_version",
            name="uq_risk_state_account_asof_policy",
        ),
        CheckConstraint(
            "available_bankroll <= current_bankroll", name="ck_risk_available_le_current"
        ),
        CheckConstraint("peak_bankroll >= current_bankroll", name="ck_risk_peak_ge_current"),
        CheckConstraint("committed_exposure >= 0", name="ck_risk_committed_nonneg"),
        CheckConstraint("daily_exposure >= 0", name="ck_risk_daily_nonneg"),
        CheckConstraint(
            "drawdown_fraction >= 0 AND drawdown_fraction <= 1",
            name="ck_risk_drawdown_unit",
        ),
    )

    account: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    evaluated_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    current_bankroll: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    peak_bankroll: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    available_bankroll: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    committed_exposure: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    daily_exposure: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    drawdown_fraction: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    rolling_volatility: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    operating_state: Mapped[RiskState] = mapped_column(
        Enum(
            RiskState,
            name="risk_operating_state",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    diagnostics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
