"""Persist exact bookmaker quote identity for Daily Pick legs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d3e5f7a9b2"
down_revision: str | Sequence[str] | None = "a6c8e0f2d4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("accumulator_legs", "daily_candidate_snapshots"):
        op.add_column(
            table,
            sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(f"ix_{table}_quote_id", table, ["quote_id"])
        op.create_foreign_key(
            f"fk_{table}_quote_id",
            table,
            "odds_quotes",
            ["quote_id"],
            ["id"],
        )


def downgrade() -> None:
    for table in ("daily_candidate_snapshots", "accumulator_legs"):
        op.drop_constraint(f"fk_{table}_quote_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_quote_id", table_name=table)
        op.drop_column(table, "quote_id")
