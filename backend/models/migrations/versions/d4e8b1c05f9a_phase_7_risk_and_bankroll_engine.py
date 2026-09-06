"""phase 7 append-only bankroll ledger and immutable risk-state snapshots

Revision ID: d4e8b1c05f9a
Revises: c27f9016ab3e
Create Date: 2026-09-06 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e8b1c05f9a"
down_revision: str | Sequence[str] | None = "c27f9016ab3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    entry_type = postgresql.ENUM(
        "deposit", "withdrawal", "settlement", "adjustment", name="ledger_entry_type"
    )
    operating_state = postgresql.ENUM(
        "normal", "caution", "defensive", "review", name="risk_operating_state"
    )
    op.create_table(
        "bankroll_ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(80), nullable=False),
        sa.Column("entry_type", entry_type, nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 4), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0", name="ck_ledger_amount_nonzero"),
        sa.CheckConstraint(
            "(entry_type <> 'deposit' OR amount > 0) "
            "AND (entry_type <> 'withdrawal' OR amount < 0)",
            name="ck_ledger_sign_by_type",
        ),
        sa.UniqueConstraint("account", "occurred_at", "id", name="uq_ledger_account_occurred"),
        sa.UniqueConstraint("account", "idempotency_key", name="uq_ledger_idempotency"),
    )
    op.create_index(
        "ix_bankroll_ledger_entries_account", "bankroll_ledger_entries", ["account"]
    )
    op.create_index(
        "ix_bankroll_ledger_entries_entry_type",
        "bankroll_ledger_entries", ["entry_type"],
    )
    op.create_index(
        "ix_bankroll_ledger_entries_occurred_at",
        "bankroll_ledger_entries", ["occurred_at"],
    )
    op.create_table(
        "risk_state_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(80), nullable=False),
        sa.Column("evaluated_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_bankroll", sa.Numeric(18, 4), nullable=False),
        sa.Column("peak_bankroll", sa.Numeric(18, 4), nullable=False),
        sa.Column("available_bankroll", sa.Numeric(18, 4), nullable=False),
        sa.Column("committed_exposure", sa.Numeric(18, 4), nullable=False),
        sa.Column("daily_exposure", sa.Numeric(18, 4), nullable=False),
        sa.Column("drawdown_fraction", sa.Numeric(9, 8), nullable=False),
        sa.Column("rolling_volatility", sa.Numeric(18, 8), nullable=True),
        sa.Column("operating_state", operating_state, nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("diagnostics", postgresql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "available_bankroll <= current_bankroll", name="ck_risk_available_le_current"
        ),
        sa.CheckConstraint("available_bankroll >= 0", name="ck_risk_available_nonneg"),
        sa.CheckConstraint("current_bankroll >= 0", name="ck_risk_current_nonneg"),
        sa.CheckConstraint(
            "peak_bankroll >= current_bankroll", name="ck_risk_peak_ge_current"
        ),
        sa.CheckConstraint("committed_exposure >= 0", name="ck_risk_committed_nonneg"),
        sa.CheckConstraint("daily_exposure >= 0", name="ck_risk_daily_nonneg"),
        sa.CheckConstraint(
            "drawdown_fraction >= 0 AND drawdown_fraction <= 1",
            name="ck_risk_drawdown_unit",
        ),
        sa.UniqueConstraint(
            "account", "evaluated_as_of", "policy_version",
            name="uq_risk_state_account_asof_policy",
        ),
    )
    op.create_index(
        "ix_risk_state_snapshots_account", "risk_state_snapshots", ["account"]
    )
    op.create_index(
        "ix_risk_state_snapshots_evaluated_as_of",
        "risk_state_snapshots", ["evaluated_as_of"],
    )
    op.create_index(
        "ix_risk_state_snapshots_operating_state",
        "risk_state_snapshots", ["operating_state"],
    )
    for table in ("bankroll_ledger_entries", "risk_state_snapshots"):
        for operation in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_{operation} "
                f"BEFORE {operation.upper()} ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
            )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate "
            f"BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
        )


def downgrade() -> None:
    op.drop_table("risk_state_snapshots")
    op.drop_table("bankroll_ledger_entries")
    postgresql.ENUM(name="risk_operating_state").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="ledger_entry_type").drop(op.get_bind(), checkfirst=True)
