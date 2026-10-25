"""Preserve provider fixture status and unresolved result states.

Revision ID: d2e4a6c8b0f1
Revises: d1b7c4e6a2f8
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e4a6c8b0f1"
down_revision = "d1b7c4e6a2f8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE matchstatus ADD VALUE IF NOT EXISTS 'ABANDONED'")
    op.execute("ALTER TYPE matchstatus ADD VALUE IF NOT EXISTS 'AWARDED'")
    op.add_column("matches", sa.Column("fixture_status_code", sa.String(10), nullable=True))


def downgrade():
    # PostgreSQL does not support dropping enum labels in place. Keep the
    # additive labels while removing the optional provider-code column.
    op.drop_column("matches", "fixture_status_code")
