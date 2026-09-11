"""Add Competition.validated flag and seed the four validated leagues

Revision ID: a4b6c8d0e2f4
Revises: c3e5a7b9d1f2
Create Date: 2026-09-11

Adds ``competitions.validated`` (Boolean, NOT NULL, default FALSE) so that the
signal pipeline can enforce a hard publication barrier: only competitions with
``validated=True`` may generate live signals.

The four leagues whose calibration and reliability evidence is established are
seeded to ``validated=TRUE`` by looking them up via the existing
``source_mappings`` table (external_id IN ('39','78','61','140') for the
API-Football provider).  The seeding is a best-effort UPDATE — it is a no-op
on a fresh database with no ingested competitions, and safe to re-run.

Downgrade: drops the column (data loss of the flag only — competition rows
are untouched).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4b6c8d0e2f4"
down_revision = "c3e5a7b9d1f2"
branch_labels = None
depends_on = None

_VALIDATED_EXTERNAL_IDS = ("39", "78", "61", "140")


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column("validated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Seed validated=TRUE for the four API-Football leagues by resolving their
    # canonical competition UUIDs through the source_mappings/providers tables.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                UPDATE competitions
                SET validated = TRUE
                WHERE id IN (
                    SELECT sm.canonical_id
                    FROM source_mappings sm
                    JOIN providers p ON p.id = sm.provider_id
                    WHERE LOWER(p.name) LIKE 'api-football%'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id = ANY(:ids)
                )
                """
            ),
            {"ids": list(_VALIDATED_EXTERNAL_IDS)},
        )
    else:
        # SQLite: no ANY(); use IN with individual placeholders.
        placeholders = ", ".join(f":id{i}" for i in range(len(_VALIDATED_EXTERNAL_IDS)))
        params = {f"id{i}": v for i, v in enumerate(_VALIDATED_EXTERNAL_IDS)}
        bind.execute(
            sa.text(
                f"""
                UPDATE competitions
                SET validated = 1
                WHERE id IN (
                    SELECT sm.canonical_id
                    FROM source_mappings sm
                    JOIN providers p ON p.id = sm.provider_id
                    WHERE LOWER(p.name) LIKE 'api-football%'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id IN ({placeholders})
                )
                """
            ),
            params,
        )


def downgrade() -> None:
    op.drop_column("competitions", "validated")
