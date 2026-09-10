"""Add linear_ols to calibration_method enum

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c1e3
Create Date: 2026-09-10

Adds the ``linear_ols`` value to the ``calibration_method`` Postgres enum so
that OLS-fitted calibrators in the live signal pipeline can be stored with
correct provenance.  SQLite stores the column as VARCHAR and is unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e5a7b9d1f2"
down_revision = "b2d4f6a8c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS makes this safe to re-run (Postgres >= 9.6).
        op.execute(sa.text("ALTER TYPE calibration_method ADD VALUE IF NOT EXISTS 'linear_ols'"))
    # SQLite: VARCHAR column; Base.metadata.create_all() already reflects the new value.


def downgrade() -> None:
    # Postgres does not support removing enum values once committed; downgrade is a no-op.
    pass
