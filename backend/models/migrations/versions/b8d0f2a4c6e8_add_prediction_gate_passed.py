"""Add predictions.gate_passed — distinguish archived-rejected from live signals

Revision ID: b8d0f2a4c6e8
Revises: 0cded7a40ae5
Create Date: 2026-09-20

DEVELOPMENT.md §4 requires that every computed forecast is archived, but a
forecast the value gate rejected must never be treated as a
published/stakeable signal. Before this migration the signal pipeline
enforced that second half of the rule by simply never archiving a
gate-rejected production forecast at all — satisfying "never stakeable" by
violating "always archived".

This column makes the boundary explicit and queryable instead of leaving
callers to infer gate outcome from ``reason_codes``. It defaults to ``True``
and every existing row genuinely passed the gate (rejected forecasts were
never persisted before this change), so no backfill is required. Downstream
consumers — the accumulator optimiser in particular — must filter on this
column before treating a row as eligible for staking.

The downgrade drops the column and is therefore only suitable for a
disposable schema where the gate-outcome classification is not required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d0f2a4c6e8"
down_revision: str | None = "0cded7a40ae5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("gate_passed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("predictions", "gate_passed", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "gate_passed")
