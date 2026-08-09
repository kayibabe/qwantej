"""Migrate all DateTime columns to TIMESTAMP WITH TIME ZONE

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-09

SQLite used TIMESTAMP WITHOUT TIME ZONE (naive). PostgreSQL is strict about
timezone-awareness, so all datetime columns are migrated to TIMESTAMPTZ.
The USING clause reinterprets any existing naive values as UTC.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table_name, [column_names])
_TABLES: list[tuple[str, list[str]]] = [
    ("ingestion_runs",      ["started_at", "ended_at"]),
    ("tracked_bets",        ["created_at", "updated_at", "settled_at"]),
    ("backtest_results",    ["created_at"]),
    ("fixtures",            ["kickoff_at", "created_at", "updated_at"]),
    ("loss_analysis",       ["created_at"]),
    ("market_snapshots",    ["pulled_at"]),
    ("signals",             ["computed_at"]),
    ("users",               ["subscription_expires_at", "created_at", "updated_at", "last_active_at"]),
    ("learning_proposals",  ["updated_at"]),
]


def upgrade() -> None:
    for table, cols in _TABLES:
        for col in cols:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE "
                f"USING {col} AT TIME ZONE 'UTC'"
            )


def downgrade() -> None:
    for table, cols in _TABLES:
        for col in cols:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE "
                f"USING {col} AT TIME ZONE 'UTC'"
            )
