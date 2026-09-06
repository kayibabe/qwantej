"""phase 7.5 immutable point-in-time feature snapshots

Adds the framework's missing feature-store contract: every model-ready vector
is versioned, tied to an as-of cutoff, content-addressed, and linked to the
append-only source observations used to build it. Rows are immutable because a
correction or recomputation must create a new historical revision.

Revision ID: f3a7c9d21e6b
Revises: a1c2e3f40b5d
Create Date: 2026-09-06 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a7c9d21e6b"
down_revision: str | Sequence[str] | None = "a1c2e3f40b5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id"),
            nullable=False,
        ),
        sa.Column("feature_version", sa.String(80), nullable=False),
        sa.Column("as_of_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSON, nullable=False),
        sa.Column("stats_snapshot_ids", postgresql.JSON, nullable=False),
        sa.Column("odds_quote_ids", postgresql.JSON, nullable=False),
        sa.Column("imputation_policy_version", sa.String(80), nullable=False),
        sa.Column("source_data_hash", sa.String(128), nullable=False),
        sa.Column("feature_hash", sa.String(128), nullable=False),
        sa.Column("snapshot_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("code_commit", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "feature_version <> ''", name="ck_feature_snapshot_version_nonblank"
        ),
        sa.CheckConstraint(
            "imputation_policy_version <> ''",
            name="ck_feature_snapshot_imputation_policy_nonblank",
        ),
        sa.CheckConstraint(
            "code_commit <> ''", name="ck_feature_snapshot_commit_nonblank"
        ),
        sa.CheckConstraint(
            "length(source_data_hash) = 71 AND source_data_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_source_hash",
        ),
        sa.CheckConstraint(
            "length(feature_hash) = 71 AND feature_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_feature_hash",
        ),
        sa.CheckConstraint(
            "length(snapshot_hash) = 71 AND snapshot_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_hash",
        ),
        sa.UniqueConstraint(
            "fixture_id",
            "feature_version",
            "as_of_timestamp",
            "snapshot_hash",
            name="uq_feature_snapshot_identity",
        ),
    )
    op.create_index("ix_feature_snapshots_fixture_id", "feature_snapshots", ["fixture_id"])
    op.create_index(
        "ix_feature_snapshots_feature_version", "feature_snapshots", ["feature_version"]
    )
    op.create_index(
        "ix_feature_snapshots_as_of_timestamp", "feature_snapshots", ["as_of_timestamp"]
    )
    op.execute(
        "CREATE TRIGGER trg_feature_snapshots_no_row_mutation "
        "BEFORE UPDATE OR DELETE ON feature_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
    )
    op.execute(
        "CREATE TRIGGER trg_feature_snapshots_no_truncate "
        "BEFORE TRUNCATE ON feature_snapshots "
        "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_feature_snapshots_no_truncate ON feature_snapshots;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_feature_snapshots_no_row_mutation "
        "ON feature_snapshots;"
    )
    op.drop_index("ix_feature_snapshots_as_of_timestamp", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_feature_version", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_fixture_id", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
