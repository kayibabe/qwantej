"""phase 2 hardening: append-only triggers + prediction run/input lineage

Addresses two review findings against the Phase 2 archive:

1. Immutability was only implied (no `updated_at`), not enforced — rows in
   `predictions` and `audit_events` could still be UPDATEd/DELETEd. This adds
   a Postgres trigger that raises on any UPDATE, DELETE or TRUNCATE of those
   append-only tables, so the archive is immutable at the database level.
   (The ORM's SQLite tests cannot exercise triggers; a Postgres regression
   test in tests/test_immutability_pg.py covers this against the dev
   container.)

2. `predictions` recorded model *versions* (attribution) but not which
   execution produced its parameters, nor the exact inputs — so a prediction
   could not actually be replayed. Adds `model_run_id` (FK -> model_runs) and
   `input_snapshot_hash`.

Revision ID: da3a07d4e74e
Revises: e461c24386f2
Create Date: 2026-09-06 11:52:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'da3a07d4e74e'
down_revision: str | Sequence[str] | None = 'e461c24386f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMUTABLE_TABLES = ("predictions", "audit_events")

_FORBID_MUTATION_FN = """
CREATE OR REPLACE FUNCTION qwantej_forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'table % is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # --- Finding 2: prediction execution/input lineage ---
    op.add_column(
        "predictions",
        sa.Column("model_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "predictions",
        sa.Column("input_snapshot_hash", sa.String(128), nullable=True),
    )
    op.create_foreign_key(
        "fk_predictions_model_run_id", "predictions", "model_runs",
        ["model_run_id"], ["id"],
    )
    op.create_index("ix_predictions_model_run_id", "predictions", ["model_run_id"])

    # --- Finding 1: enforce append-only immutability at the DB level ---
    op.execute(_FORBID_MUTATION_FN)
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_row_mutation "
            f"BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate "
            f"BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
        )


def downgrade() -> None:
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_row_mutation ON {table};")
    op.execute("DROP FUNCTION IF EXISTS qwantej_forbid_mutation();")

    op.drop_index("ix_predictions_model_run_id", table_name="predictions")
    op.drop_constraint("fk_predictions_model_run_id", "predictions", type_="foreignkey")
    op.drop_column("predictions", "input_snapshot_hash")
    op.drop_column("predictions", "model_run_id")
