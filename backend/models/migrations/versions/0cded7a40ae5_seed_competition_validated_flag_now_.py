"""Seed Competition.validated now that the four leagues have been ingested

Revision ID: 0cded7a40ae5
Revises: b4c6d8e0f2a4
Create Date: 2026-09-14

Migration a4b6c8d0e2f4 seeded ``validated=TRUE`` for the four supported
leagues by resolving them through ``source_mappings``, but documented itself
as a no-op on a fresh database with no ingested competitions yet. That was
exactly the Neon production database's state when it ran (empty, pre-first
ingestion) — so all four competitions came back from the first ingestion run
with ``validated=FALSE``, and the signal pipeline's publication gate
(``DEVELOPMENT.md`` §4) silently blocked every one of them.

This re-runs the identical, idempotent seed query now that
``source_mappings`` rows exist for the four leagues (created by the first
ingestion pass). Safe to re-run on any database: a no-op wherever the rows
are already validated or don't exist yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0cded7a40ae5"
down_revision = "b4c6d8e0f2a4"
branch_labels = None
depends_on = None

_VALIDATED_EXTERNAL_IDS = ("39", "78", "61", "140")


def upgrade() -> None:
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
                    WHERE LOWER(p.name) = 'api-football'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id = ANY(:ids)
                )
                """
            ),
            {"ids": list(_VALIDATED_EXTERNAL_IDS)},
        )
    else:
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
                    WHERE LOWER(p.name) = 'api-football'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id IN ({placeholders})
                )
                """
            ),
            params,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                UPDATE competitions
                SET validated = FALSE
                WHERE id IN (
                    SELECT sm.canonical_id
                    FROM source_mappings sm
                    JOIN providers p ON p.id = sm.provider_id
                    WHERE LOWER(p.name) = 'api-football'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id = ANY(:ids)
                )
                """
            ),
            {"ids": list(_VALIDATED_EXTERNAL_IDS)},
        )
    else:
        placeholders = ", ".join(f":id{i}" for i in range(len(_VALIDATED_EXTERNAL_IDS)))
        params = {f"id{i}": v for i, v in enumerate(_VALIDATED_EXTERNAL_IDS)}
        bind.execute(
            sa.text(
                f"""
                UPDATE competitions
                SET validated = 0
                WHERE id IN (
                    SELECT sm.canonical_id
                    FROM source_mappings sm
                    JOIN providers p ON p.id = sm.provider_id
                    WHERE LOWER(p.name) = 'api-football'
                      AND sm.entity_type = 'competition'
                      AND sm.external_id IN ({placeholders})
                )
                """
            ),
            params,
        )
