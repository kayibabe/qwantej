"""allow one leg per fixture in each personal accumulator

Revision ID: a197c4e8d2f1
Revises: ff58a0d2c3e1
"""

from alembic import op


revision = "a197c4e8d2f1"
down_revision = "ff58a0d2c3e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_custom_accumulator_one_leg_per_match",
        "custom_accumulator_legs",
        ["accumulator_id", "match_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_custom_accumulator_one_leg_per_match",
        "custom_accumulator_legs",
        type_="unique",
    )
