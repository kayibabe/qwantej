"""Add linear_ols to calibration_method enum

Revision ID: c3e5a7b9d1f2
Revises: f9c1e3a5b7d2
Create Date: 2026-09-10

Adds the ``linear_ols`` value to the ``calibration_method`` Postgres enum so
that OLS-fitted calibrators in the live signal pipeline can be stored with
correct provenance.  SQLite stores the column as VARCHAR and is unaffected.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e5a7b9d1f2"
down_revision = "f9c1e3a5b7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS makes this safe to re-run (Postgres >= 9.6).
        op.execute(sa.text("ALTER TYPE calibration_method ADD VALUE IF NOT EXISTS 'linear_ols'"))
    # SQLite: VARCHAR column; Base.metadata.create_all() already reflects the new value.


def downgrade() -> None:
    # PostgreSQL does not support removing values from a native enum type once
    # they have been committed (no DROP VALUE syntax).  Rolling back this
    # migration would require recreating the entire type, which risks data loss
    # on any row already using 'linear_ols'.  Consistent with the repository
    # policy for irreversible enum changes, this downgrade is intentionally a
    # no-op: to revert, redeploy the previous release and retire any rows that
    # reference the removed value before dropping and recreating the type.
    pass
