"""Add optional account ownership to journal entries.

Revision ID: 0100_account_owned_bet_journal
Revises: ff58a0d2c3e1
"""

from alembic import op
import sqlalchemy as sa


revision = "0100_account_owned_bet_journal"
down_revision = "d2e4a6c8b0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bets",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bets_user_id_users",
        "bets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_bets_user_id", "bets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bets_user_id", table_name="bets")
    op.drop_constraint("fk_bets_user_id_users", "bets", type_="foreignkey")
    op.drop_column("bets", "user_id")
