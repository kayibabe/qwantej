"""Repair the approved API-Football competition validation backfill.

Revision ID: c9d1e4f7a2b5
Revises: b8d0f2a4c6e8
Create Date: 2026-09-20

The original ``competitions.validated`` migration was necessarily a one-time
backfill.  On a database where the four approved API-Football competitions
were first ingested after that migration, they retained the schema default of
``FALSE``.  That makes the fail-closed publication gate hide otherwise valid
fixtures, prices, and paper-ticket candidates.

This idempotently restores the existing approved mapping scope (39, 61, 78,
140).  It neither validates any other competition nor touches predictions,
accumulators, settlements, or historical records.  New competition creation
is guarded in application code by the same allow-list.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d1e4f7a2b5"
down_revision: str | None = "b8d0f2a4c6e8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VALIDATED_EXTERNAL_IDS = ("39", "61", "78", "140")


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
        params = {f"id{i}": value for i, value in enumerate(_VALIDATED_EXTERNAL_IDS)}
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
    # The prior migration's false default is restored only for the exact scope
    # this corrective migration set.  No unrelated competition is changed.
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
        params = {f"id{i}": value for i, value in enumerate(_VALIDATED_EXTERNAL_IDS)}
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
