"""phase 4 calibration registry, monitoring, and lineage hardening

Revision ID: c84f2d19a6b1
Revises: da3a07d4e74e
Create Date: 2026-09-06 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c84f2d19a6b1"
down_revision: str | Sequence[str] | None = "da3a07d4e74e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A prediction's run must belong to the model version it names. The prior
    # single-column FK only proved that each row existed independently.
    op.create_unique_constraint(
        "uq_model_runs_id_model_id", "model_runs", ["id", "model_id"]
    )
    op.drop_constraint("fk_predictions_model_run_id", "predictions", type_="foreignkey")
    op.create_foreign_key(
        "fk_predictions_model_run_model",
        "predictions",
        "model_runs",
        ["model_run_id", "model_version_id"],
        ["id", "model_id"],
    )
    op.add_column("predictions", sa.Column("input_snapshot_ref", sa.String(255)))

    method_enum = postgresql.ENUM("platt", "isotonic", name="calibration_method")
    status_enum = postgresql.ENUM(
        "development", "challenger", "champion", "retired", name="calibration_status"
    )
    op.create_table(
        "calibration_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("method", method_enum, nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("market", sa.String(40)),
        sa.Column("competition", sa.String(120)),
        sa.Column("model_family", sa.String(40)),
        sa.Column("trained_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column("parameters", postgresql.JSON(), nullable=False),
        sa.Column("diagnostics", postgresql.JSON()),
        sa.Column("artefact_hash", sa.String(128), nullable=False),
        sa.Column("code_commit", sa.String(64), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sample_size > 0", name="ck_calibration_models_sample_size_positive"),
        sa.CheckConstraint(
            "minimum_sample_size >= 2", name="ck_calibration_models_minimum_sample_size"
        ),
        sa.CheckConstraint(
            "sample_size >= minimum_sample_size",
            name="ck_calibration_models_sample_meets_minimum",
        ),
        sa.CheckConstraint(
            "training_window_start <= training_window_end",
            name="ck_calibration_models_training_window_order",
        ),
        sa.CheckConstraint(
            "training_window_end <= trained_as_of",
            name="ck_calibration_models_point_in_time",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["calibration_models.id"]),
        sa.UniqueConstraint("version", name="uq_calibration_models_version"),
    )
    for column in ("status", "market", "competition", "model_family"):
        op.create_index(f"ix_calibration_models_{column}", "calibration_models", [column])

    op.add_column(
        "predictions",
        sa.Column("calibration_model_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "fk_predictions_calibration_model_id",
        "predictions",
        "calibration_models",
        ["calibration_model_id"],
        ["id"],
    )
    op.create_index(
        "ix_predictions_calibration_model_id", "predictions", ["calibration_model_id"]
    )

    op.create_table(
        "calibration_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "calibration_model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calibration_models.id"),
            nullable=False,
        ),
        sa.Column("evaluated_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("brier_score", sa.Numeric(9, 8), nullable=False),
        sa.Column("log_loss", sa.Numeric(12, 8), nullable=False),
        sa.Column("expected_calibration_error", sa.Numeric(9, 8), nullable=False),
        sa.Column("calibration_intercept", sa.Numeric(12, 8)),
        sa.Column("calibration_slope", sa.Numeric(12, 8)),
        sa.Column("brier_skill_score", sa.Numeric(12, 8)),
        sa.Column("reliability_curve", postgresql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sample_size > 0", name="ck_cal_snap_sample_positive"
        ),
        sa.CheckConstraint(
            "window_start <= window_end", name="ck_cal_snap_window_order"
        ),
        sa.CheckConstraint(
            "window_end <= evaluated_as_of", name="ck_cal_snap_point_in_time"
        ),
        sa.CheckConstraint(
            "brier_score >= 0 AND brier_score <= 1",
            name="ck_cal_snap_brier_unit",
        ),
        sa.CheckConstraint(
            "expected_calibration_error >= 0 AND expected_calibration_error <= 1",
            name="ck_cal_snap_ece_unit",
        ),
    )
    op.create_index(
        "ix_calibration_snapshots_calibration_model_id",
        "calibration_snapshots",
        ["calibration_model_id"],
    )
    op.create_index(
        "ix_calibration_snapshots_evaluated_as_of",
        "calibration_snapshots",
        ["evaluated_as_of"],
    )
    op.execute(
        "CREATE TRIGGER trg_calibration_snapshots_no_row_mutation "
        "BEFORE UPDATE OR DELETE ON calibration_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
    )
    op.execute(
        "CREATE TRIGGER trg_calibration_snapshots_no_truncate "
        "BEFORE TRUNCATE ON calibration_snapshots "
        "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_calibration_snapshots_no_truncate "
        "ON calibration_snapshots;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_calibration_snapshots_no_row_mutation "
        "ON calibration_snapshots;"
    )
    op.drop_table("calibration_snapshots")

    op.drop_index("ix_predictions_calibration_model_id", table_name="predictions")
    op.drop_constraint(
        "fk_predictions_calibration_model_id", "predictions", type_="foreignkey"
    )
    op.drop_column("predictions", "calibration_model_id")

    for column in ("model_family", "competition", "market", "status"):
        op.drop_index(f"ix_calibration_models_{column}", table_name="calibration_models")
    op.drop_table("calibration_models")
    postgresql.ENUM(name="calibration_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="calibration_method").drop(op.get_bind(), checkfirst=True)

    op.drop_column("predictions", "input_snapshot_ref")
    op.drop_constraint("fk_predictions_model_run_model", "predictions", type_="foreignkey")
    op.create_foreign_key(
        "fk_predictions_model_run_id",
        "predictions",
        "model_runs",
        ["model_run_id"],
        ["id"],
    )
    op.drop_constraint("uq_model_runs_id_model_id", "model_runs", type_="unique")
