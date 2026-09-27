"""Real-money bet tracking: immutable real bets and append-only settlements

Revision ID: e7a3c5d9f1b2
Revises: c9d1e4f7a2b5
Create Date: 2026-09-27

Adds ``real_bets`` (what the owner actually staked on a published ticket) and
``real_bet_settlements`` (what the bookmaker paid, with corrections as new
rows). Both are append-only: UPDATE, DELETE and TRUNCATE are rejected by the
existing ``qwantej_forbid_mutation()`` trigger function. Purely additive — no
existing table or row is touched, and paper tickets stay ``paper_only``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7a3c5d9f1b2"
down_revision: str | None = "c9d1e4f7a2b5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLES = ("real_bets", "real_bet_settlements")


def upgrade() -> None:
    outcome = postgresql.ENUM("won", "lost", "void", "cashed_out", name="real_bet_outcome")

    op.create_table(
        "real_bets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account", sa.String(80), nullable=False),
        sa.Column(
            "accumulator_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accumulators.id"), nullable=False,
        ),
        sa.Column("bookmaker", sa.String(80), nullable=False),
        sa.Column("bookmaker_reference", sa.String(120), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("stake", sa.Numeric(18, 4), nullable=False),
        sa.Column("taken_odds", sa.Numeric(10, 4), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stake > 0", name="ck_real_bets_stake_pos"),
        sa.CheckConstraint("taken_odds > 1", name="ck_real_bets_taken_odds_gt_1"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_real_bets_currency_iso",
        ),
        sa.UniqueConstraint(
            "account", "bookmaker", "bookmaker_reference",
            name="uq_real_bets_bookmaker_reference",
        ),
        sa.UniqueConstraint("account", "idempotency_key", name="uq_real_bets_idempotency"),
    )
    op.create_index("ix_real_bets_account", "real_bets", ["account"])
    op.create_index("ix_real_bets_accumulator_id", "real_bets", ["accumulator_id"])
    op.create_index("ix_real_bets_placed_at", "real_bets", ["placed_at"])

    op.create_table(
        "real_bet_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "real_bet_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("real_bets.id"), nullable=False,
        ),
        sa.Column("outcome", outcome, nullable=False),
        sa.Column("payout", sa.Numeric(18, 4), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("real_bet_settlements.id"), nullable=True,
        ),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "ledger_entry_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bankroll_ledger_entries.id"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("payout >= 0", name="ck_real_bet_settlements_payout_nonneg"),
        sa.UniqueConstraint("supersedes_id", name="uq_real_bet_settlements_supersedes"),
        sa.UniqueConstraint("ledger_entry_id", name="uq_real_bet_settlements_ledger_entry_id"),
    )
    op.create_index(
        "ix_real_bet_settlements_real_bet_id", "real_bet_settlements", ["real_bet_id"]
    )
    op.create_index(
        "uq_real_bet_settlements_one_original",
        "real_bet_settlements",
        ["real_bet_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NULL"),
    )

    for table in _TABLES:
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
    op.drop_table("real_bet_settlements")
    op.drop_table("real_bets")
    postgresql.ENUM(name="real_bet_outcome").drop(op.get_bind(), checkfirst=True)
