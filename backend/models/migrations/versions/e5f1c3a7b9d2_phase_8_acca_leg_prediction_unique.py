"""Phase 8: unique constraint on accumulator_legs.prediction_id

Enforces that each prediction row can only appear in a single accumulator
leg.  The existing (accumulator_id, prediction_id) constraint prevents
duplicate legs within one accumulator; this new constraint closes the
cross-accumulator race: two concurrent writers who both pass the
application-level SELECT FOR UPDATE guard cannot both insert an
accumulator_leg for the same prediction_id.

Without this constraint a crash between flush() and commit() in
persist_accumulator_decision could leave prediction_id claimed in
accumulator_legs but not yet back-linked in predictions.accumulator_id,
allowing a retry to write a second leg row for the same prediction.

Revision ID: e5f1c3a7b9d2
Revises: d1c3e5a7f9b2
Create Date: 2026-09-08 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f1c3a7b9d2"
down_revision: str | Sequence[str] | None = "d1c3e5a7f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_acca_leg_prediction",
        "accumulator_legs",
        ["prediction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_acca_leg_prediction", "accumulator_legs", type_="unique"
    )
