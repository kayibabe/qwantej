"""Phase 1C — Calibration records table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

Adds:
  - calibration_records  (per-market isotonic regression calibrators)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calibration_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("market", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(30), nullable=False, server_default="1.0.0"),
        sa.Column("n_samples", sa.Integer(), nullable=False),
        sa.Column("raw_brier", sa.Float(), nullable=False),
        sa.Column("calibrated_brier", sa.Float(), nullable=False),
        sa.Column("brier_improvement", sa.Float(), nullable=False),
        sa.Column("calibration_knots_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_calibration_records_market", "calibration_records", ["market"])
    op.create_index("ix_calibration_records_is_active", "calibration_records", ["is_active"])


def downgrade() -> None:
    op.drop_table("calibration_records")
