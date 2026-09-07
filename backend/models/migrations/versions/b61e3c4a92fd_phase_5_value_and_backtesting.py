"""phase 5 value decisions and walk-forward experiment registry

Revision ID: b61e3c4a92fd
Revises: f7b3a910de42
Create Date: 2026-09-06 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b61e3c4a92fd"
down_revision: str | Sequence[str] | None = "f7b3a910de42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GUARD_EXPERIMENT_UPDATE = """
CREATE OR REPLACE FUNCTION qwantej_guard_experiment_update() RETURNS trigger AS $$
BEGIN
    IF OLD.name IS DISTINCT FROM NEW.name
       OR OLD.version IS DISTINCT FROM NEW.version
       OR OLD.kind IS DISTINCT FROM NEW.kind
       OR OLD.model_version IS DISTINCT FROM NEW.model_version
       OR OLD.calibration_version IS DISTINCT FROM NEW.calibration_version
       OR OLD.value_policy_version IS DISTINCT FROM NEW.value_policy_version
       OR OLD.conservative_policy_version IS DISTINCT FROM NEW.conservative_policy_version
       OR OLD.code_commit IS DISTINCT FROM NEW.code_commit
       OR OLD.data_snapshot_ref IS DISTINCT FROM NEW.data_snapshot_ref
       OR OLD.baseline IS DISTINCT FROM NEW.baseline
       OR OLD.random_seed IS DISTINCT FROM NEW.random_seed
       OR OLD.configuration::text IS DISTINCT FROM NEW.configuration::text
       OR OLD.started_at IS DISTINCT FROM NEW.started_at
       OR OLD.training_window_start IS DISTINCT FROM NEW.training_window_start
       OR OLD.training_window_end IS DISTINCT FROM NEW.training_window_end
       OR OLD.test_window_start IS DISTINCT FROM NEW.test_window_start
       OR OLD.test_window_end IS DISTINCT FROM NEW.test_window_end
       OR OLD.id IS DISTINCT FROM NEW.id
       OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'experiment % configuration is immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status::text <> 'running' THEN
        RAISE EXCEPTION 'completed experiment % is immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    kind_enum = postgresql.ENUM("walk_forward_backtest", name="experiment_kind")
    status_enum = postgresql.ENUM("running", "succeeded", "failed", name="experiment_status")
    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("calibration_version", sa.String(80), nullable=False),
        sa.Column("value_policy_version", sa.String(80), nullable=False),
        sa.Column("conservative_policy_version", sa.String(80), nullable=False),
        sa.Column("code_commit", sa.String(64), nullable=False),
        sa.Column("data_snapshot_ref", sa.String(255), nullable=False),
        sa.Column("baseline", sa.String(80), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("training_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer()),
        sa.Column("leakage_rows_rejected", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSON()),
        sa.Column("result_hash", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "training_window_start <= training_window_end",
            name="ck_experiments_training_window_order",
        ),
        sa.CheckConstraint(
            "test_window_start <= test_window_end",
            name="ck_experiments_test_window_order",
        ),
        sa.CheckConstraint(
            "training_window_end <= test_window_start",
            name="ck_experiments_walk_forward_order",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_experiments_finish_order",
        ),
        sa.CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="ck_experiments_sample"
        ),
        sa.CheckConstraint(
            "leakage_rows_rejected >= 0", name="ck_experiments_leakage_rows"
        ),
        sa.CheckConstraint(
            "status = 'running' OR finished_at IS NOT NULL",
            name="ck_experiments_completed_finished",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR "
            "(sample_size IS NOT NULL AND metrics IS NOT NULL AND result_hash IS NOT NULL)",
            name="ck_experiments_succeeded_result",
        ),
        sa.UniqueConstraint("name", "version", name="uq_experiments_name_version"),
    )
    op.create_index("ix_experiments_status", "experiments", ["status"])
    op.create_index("ix_experiments_model_version", "experiments", ["model_version"])

    op.create_table(
        "selection_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prediction_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id"), nullable=False,
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("edge", sa.Numeric(9, 8)),
        sa.Column("expected_value", sa.Numeric(12, 8)),
        sa.Column("reason_codes", postgresql.JSON(), nullable=False),
        sa.Column("gate_inputs", postgresql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "edge IS NULL OR (edge >= -1 AND edge <= 1)", name="ck_candidates_edge"
        ),
    )
    op.create_index(
        "ix_selection_candidates_prediction_id", "selection_candidates", ["prediction_id"]
    )
    op.create_index(
        "ix_selection_candidates_evaluated_at", "selection_candidates", ["evaluated_at"]
    )
    op.create_index("ix_selection_candidates_passed", "selection_candidates", ["passed"])

    op.execute(_GUARD_EXPERIMENT_UPDATE)
    op.execute(
        "CREATE TRIGGER trg_experiments_guard_update BEFORE UPDATE ON experiments "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_guard_experiment_update();"
    )
    for table in ("experiments", "selection_candidates"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
    op.execute(
        "CREATE TRIGGER trg_selection_candidates_no_update "
        "BEFORE UPDATE ON selection_candidates "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_selection_candidates_no_update ON selection_candidates;"
    )
    for table in ("selection_candidates", "experiments"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table};")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_delete ON {table};")
    op.execute("DROP TRIGGER IF EXISTS trg_experiments_guard_update ON experiments;")
    op.execute("DROP FUNCTION IF EXISTS qwantej_guard_experiment_update();")
    op.drop_table("selection_candidates")
    op.drop_table("experiments")
    postgresql.ENUM(name="experiment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="experiment_kind").drop(op.get_bind(), checkfirst=True)
