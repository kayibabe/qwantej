"""phase 7.5 immutability: append-only odds/stats snapshots, frozen registry/run lineage

Foundation-closure hardening (framework §12-13):

- `odds_quotes` and `stats_snapshots` are point-in-time observations that must
  never change after capture — a later price or stat correction is a new row,
  not an edit. Enforced with the same append-only triggers used for predictions.
- `model_registry` and `model_runs` are mutable lifecycle entities, but their
  identity/reproducibility fields (what the model *is* and what a run actually
  executed against) must be frozen once written, or `predictions` lineage can be
  rewritten after the fact. Guard triggers allow only the lifecycle fields to
  change, and lock a run once it has finished.

Revision ID: a1c2e3f40b5d
Revises: d4e8b1c05f9a
Create Date: 2026-09-06 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c2e3f40b5d"
down_revision: str | Sequence[str] | None = "d4e8b1c05f9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_TABLES = ("odds_quotes", "stats_snapshots")

_GUARD_MODEL_REGISTRY_UPDATE = """
CREATE OR REPLACE FUNCTION qwantej_guard_model_registry_update() RETURNS trigger AS $$
BEGIN
    IF OLD.id IS DISTINCT FROM NEW.id
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR OLD.family IS DISTINCT FROM NEW.family
       OR OLD.name IS DISTINCT FROM NEW.name
       OR OLD.version IS DISTINCT FROM NEW.version
       OR OLD.training_window_start IS DISTINCT FROM NEW.training_window_start
       OR OLD.training_window_end IS DISTINCT FROM NEW.training_window_end
       OR OLD.code_commit IS DISTINCT FROM NEW.code_commit
       OR OLD.artefact_hash IS DISTINCT FROM NEW.artefact_hash
       OR OLD.artefact_uri IS DISTINCT FROM NEW.artefact_uri
       OR OLD.hyperparameters::text IS DISTINCT FROM NEW.hyperparameters::text THEN
        RAISE EXCEPTION
            'model_registry % identity/lineage is immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_GUARD_MODEL_RUN_UPDATE = """
CREATE OR REPLACE FUNCTION qwantej_guard_model_run_update() RETURNS trigger AS $$
BEGIN
    IF OLD.id IS DISTINCT FROM NEW.id
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR OLD.model_id IS DISTINCT FROM NEW.model_id
       OR OLD.kind IS DISTINCT FROM NEW.kind
       OR OLD.started_at IS DISTINCT FROM NEW.started_at
       OR OLD.data_as_of IS DISTINCT FROM NEW.data_as_of
       OR OLD.data_snapshot_ref IS DISTINCT FROM NEW.data_snapshot_ref
       OR OLD.code_commit IS DISTINCT FROM NEW.code_commit
       OR OLD.parameters::text IS DISTINCT FROM NEW.parameters::text THEN
        RAISE EXCEPTION 'model_run % inputs are immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status::text IN ('succeeded', 'failed') THEN
        RAISE EXCEPTION 'finished model_run % is immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # Append-only point-in-time observation tables.
    for table in _APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_row_mutation "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate "
            f"BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
        )

    # Freeze registry/run identity while allowing lifecycle transitions.
    op.execute(_GUARD_MODEL_REGISTRY_UPDATE)
    op.execute(
        "CREATE TRIGGER trg_model_registry_guard_update BEFORE UPDATE ON model_registry "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_guard_model_registry_update();"
    )
    op.execute(_GUARD_MODEL_RUN_UPDATE)
    op.execute(
        "CREATE TRIGGER trg_model_runs_guard_update BEFORE UPDATE ON model_runs "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_guard_model_run_update();"
    )
    # The lineage anchors are never deleted or truncated.
    for table in ("model_registry", "model_runs"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
        )


def downgrade() -> None:
    for table in ("model_registry", "model_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete ON {table};")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_model_runs_guard_update ON model_runs;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_model_registry_guard_update ON model_registry;"
    )
    op.execute("DROP FUNCTION IF EXISTS qwantej_guard_model_run_update();")
    op.execute("DROP FUNCTION IF EXISTS qwantej_guard_model_registry_update();")
    for table in _APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_row_mutation ON {table};")
