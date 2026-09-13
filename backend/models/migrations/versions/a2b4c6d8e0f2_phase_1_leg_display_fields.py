"""Phase 1: add quote_captured_at to accumulator_legs for price-freshness display.

Stores the exact moment the price quote was observed, so the UI can show
"price as of HH:MM" next to each leg. Nullable so existing rows remain valid.

Revision ID: a2b4c6d8e0f2
Revises: c6d8e0f2a4b1
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b4c6d8e0f2"
down_revision: str | Sequence[str] | None = "c6d8e0f2a4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accumulator_legs",
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accumulator_legs", "quote_captured_at")
