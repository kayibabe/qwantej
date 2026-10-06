"""Allow derived daily tickets to reference persisted source legs.

The downgrade restores the historical one-ticket-per-prediction constraint.
It is reversible as long as derived tickets have been removed or archived
outside the database first; retaining derived rows would correctly make the
constraint restoration fail rather than delete historical ticket evidence.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a6c8e0f2d4b1"
down_revision = "b8d2f4a6c9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_acca_leg_prediction", "accumulator_legs", type_="unique")
    op.add_column(
        "accumulator_legs",
        sa.Column("source_accumulator_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_accumulator_legs_source_accumulator_id",
        "accumulator_legs",
        ["source_accumulator_id"],
    )
    op.create_foreign_key(
        "fk_accumulator_legs_source_accumulator_id",
        "accumulator_legs",
        "accumulators",
        ["source_accumulator_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_accumulator_legs_source_accumulator_id",
        "accumulator_legs",
        type_="foreignkey",
    )
    op.drop_index("ix_accumulator_legs_source_accumulator_id", table_name="accumulator_legs")
    op.drop_column("accumulator_legs", "source_accumulator_id")
    op.create_unique_constraint(
        "uq_acca_leg_prediction", "accumulator_legs", ["prediction_id"]
    )
