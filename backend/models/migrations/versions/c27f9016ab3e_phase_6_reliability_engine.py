"""phase 6 immutable league-market reliability snapshots

Revision ID: c27f9016ab3e
Revises: b61e3c4a92fd
Create Date: 2026-09-06 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c27f9016ab3e"
down_revision: str | Sequence[str] | None = "b61e3c4a92fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    state_enum = postgresql.ENUM(
        "qualified", "watch", "restricted", "blacklisted", name="reliability_state"
    )
    op.create_table(
        "reliability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "competition_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitions.id"), nullable=False,
        ),
        sa.Column("competition_class", sa.String(80), nullable=False),
        sa.Column("market_family", sa.String(80), nullable=False),
        sa.Column("evaluated_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("effective_sample_size", sa.Numeric(12, 6), nullable=False),
        sa.Column("shrinkage_weight", sa.Numeric(9, 8), nullable=False),
        sa.Column("league_reliability", sa.Numeric(7, 4), nullable=False),
        sa.Column("market_reliability", sa.Numeric(7, 4), nullable=False),
        sa.Column("segment_reliability", sa.Numeric(7, 4), nullable=False),
        sa.Column("posterior_standard_deviation", sa.Numeric(9, 8), nullable=False),
        sa.Column("conservative_lower_bound", sa.Numeric(9, 8), nullable=False),
        sa.Column("status", state_enum, nullable=False),
        sa.Column("grade", sa.String(12), nullable=False),
        sa.Column("components", postgresql.JSON(), nullable=False),
        sa.Column("diagnostics", postgresql.JSON(), nullable=False),
        sa.Column("future_rows_excluded", sa.Integer(), nullable=False),
        sa.Column("input_snapshot_ref", sa.String(255), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("code_commit", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("window_start <= window_end", name="ck_reliability_window_order"),
        sa.CheckConstraint(
            "window_end <= evaluated_as_of", name="ck_reliability_asof_cutoff"
        ),
        sa.CheckConstraint("observation_count > 0", name="ck_reliability_observations"),
        sa.CheckConstraint(
            "effective_sample_size > 0 AND effective_sample_size <= observation_count",
            name="ck_reliability_effective_sample",
        ),
        sa.CheckConstraint(
            "shrinkage_weight >= 0 AND shrinkage_weight <= 1",
            name="ck_reliability_shrinkage",
        ),
        sa.CheckConstraint(
            "posterior_standard_deviation >= 0", name="ck_reliability_uncertainty"
        ),
        sa.CheckConstraint(
            "league_reliability >= 0 AND league_reliability <= 100 "
            "AND market_reliability >= 0 AND market_reliability <= 100 "
            "AND segment_reliability >= 0 AND segment_reliability <= 100 "
            "AND conservative_lower_bound >= 0 AND conservative_lower_bound <= 1",
            name="ck_reliability_scores",
        ),
        sa.CheckConstraint("future_rows_excluded >= 0", name="ck_reliability_future_rows"),
        sa.UniqueConstraint(
            "competition_id", "market_family", "evaluated_as_of", "policy_version",
            name="uq_reliability_snapshot_segment_cutoff_policy",
        ),
    )
    op.create_index(
        "ix_reliability_snapshots_competition_id",
        "reliability_snapshots", ["competition_id"],
    )
    op.create_index(
        "ix_reliability_snapshots_market_family",
        "reliability_snapshots", ["market_family"],
    )
    op.create_index(
        "ix_reliability_snapshots_evaluated_as_of",
        "reliability_snapshots", ["evaluated_as_of"],
    )
    op.create_index(
        "ix_reliability_snapshots_status", "reliability_snapshots", ["status"]
    )
    op.add_column(
        "predictions",
        sa.Column("reliability_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_predictions_reliability_snapshot_id",
        "predictions", ["reliability_snapshot_id"],
    )
    op.create_foreign_key(
        "fk_predictions_reliability_snapshot",
        "predictions", "reliability_snapshots",
        ["reliability_snapshot_id"], ["id"],
    )
    for operation in ("update", "delete"):
        op.execute(
            f"CREATE TRIGGER trg_reliability_snapshots_no_{operation} "
            f"BEFORE {operation.upper()} ON reliability_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
        )
    op.execute(
        "CREATE TRIGGER trg_reliability_snapshots_no_truncate "
        "BEFORE TRUNCATE ON reliability_snapshots "
        "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_predictions_reliability_snapshot", "predictions", type_="foreignkey"
    )
    op.drop_index("ix_predictions_reliability_snapshot_id", table_name="predictions")
    op.drop_column("predictions", "reliability_snapshot_id")
    op.drop_table("reliability_snapshots")
    postgresql.ENUM(name="reliability_state").drop(op.get_bind(), checkfirst=True)
