"""Add append-only Daily Pick candidate-pool snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c4e9d2b1f6"
down_revision: str | Sequence[str] | None = "f9c1e3a5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_candidate_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_day", sa.Date(), nullable=False),
        sa.Column("captured_at_run", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id"),
            nullable=False,
        ),
        sa.Column(
            "fixture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixtures.id"),
            nullable=False,
        ),
        sa.Column("league_id", sa.String(40), nullable=False),
        sa.Column("market", sa.String(40), nullable=False),
        sa.Column("selection", sa.String(80), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_probability", sa.Numeric(7, 6), nullable=False),
        sa.Column("market_probability", sa.Numeric(7, 6), nullable=False),
        sa.Column("decimal_odds", sa.Numeric(8, 3), nullable=False),
        sa.Column("quote_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dqs", sa.Numeric(5, 2), nullable=False),
        sa.Column("bookmaker", sa.String(80)),
        sa.Column("candidate_status", sa.String(32), nullable=False),
        sa.Column("exclusion_reason", sa.String(120)),
        sa.Column("selected_product", sa.String(20)),
        sa.Column(
            "accumulator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accumulators.id"),
        ),
        sa.UniqueConstraint("run_id", "prediction_id", name="uq_daily_candidate_run_prediction"),
    )
    for column in ("run_id", "product_day", "prediction_id", "fixture_id", "kickoff_utc"):
        op.create_index(
            f"ix_daily_candidate_snapshots_{column}",
            "daily_candidate_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("daily_candidate_snapshots")
