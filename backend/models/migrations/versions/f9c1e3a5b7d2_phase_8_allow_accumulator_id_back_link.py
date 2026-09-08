"""phase 8 follow-up: allow one-time accumulator_id back-link on predictions

The predictions table is append-only (trigger da3a07d4e74e), but the
accumulator persistence service needs to set predictions.accumulator_id once
after inserting an Accumulator row.  This is a write-once link: NULL → UUID.

Update qwantej_forbid_mutation() to pass that single transition through while
continuing to block all other UPDATEs and every DELETE on predictions.

Revision ID: f9c1e3a5b7d2
Revises: e5f1c3a7b9d2
Create Date: 2026-09-08 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9c1e3a5b7d2"
down_revision: str | Sequence[str] | None = "e5f1c3a7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Updated trigger: allows setting accumulator_id from NULL to non-NULL on
# predictions (one-time write-once link), blocks everything else.
# NOTE: PL/pgSQL does NOT short-circuit boolean AND — OLD.accumulator_id
# must be accessed inside a nested IF that guards on TG_TABLE_NAME first,
# otherwise the expression errors for tables that have no accumulator_id column.
_FORBID_MUTATION_FN_V2 = """
CREATE OR REPLACE FUNCTION qwantej_forbid_mutation() RETURNS trigger AS $$
BEGIN
    -- Allow the write-once accumulator_id back-link on predictions.
    -- The accumulator persistence service sets this exactly once, from NULL
    -- to the UUID of the owning Accumulator row.  Any other UPDATE column,
    -- or a second change to accumulator_id, still raises.
    IF TG_TABLE_NAME = 'predictions' AND TG_OP = 'UPDATE' THEN
        IF OLD.accumulator_id IS NULL AND NEW.accumulator_id IS NOT NULL THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION
        'table % is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

# Downgrade restores the original strict function (no exceptions).
_FORBID_MUTATION_FN_V1 = """
CREATE OR REPLACE FUNCTION qwantej_forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'table % is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_FORBID_MUTATION_FN_V2)


def downgrade() -> None:
    op.execute(_FORBID_MUTATION_FN_V1)
