"""Phase 9 fix: add taken_odds to settlements; extend accumulator identity guard

Adds the taken_odds column that was missing from the initial Phase 9 schema
and extends the _guard_accumulators_identity trigger to protect all evidence
columns (not just id/product/combined_odds/published_at).

Revision ID: a1b3e7c5f2d9
Revises: e9b4f2a71c3d
Create Date: 2026-09-07 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b3e7c5f2d9"
down_revision: str | Sequence[str] | None = "e9b4f2a71c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add taken_odds to settlements so CLV can compare taken vs closing price.
    op.add_column("settlements", sa.Column("taken_odds", sa.Numeric(8, 3), nullable=True))
    op.create_check_constraint(
        "ck_settlements_taken_odds_gt_1",
        "settlements",
        "taken_odds IS NULL OR taken_odds > 1",
    )

    # 2. Extend _guard_accumulators_identity to protect all evidence columns.
    #    The original trigger (from e9b4f2a71c3d) only checked 4 columns; the
    #    remaining columns (including created_at) are also part of the published,
    #    immutable ticket record.
    op.execute("""
        CREATE OR REPLACE FUNCTION _guard_accumulators_identity()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (
                NEW.id,
                NEW.product,
                NEW.optimiser_version,
                NEW.policy_version,
                NEW.combined_odds,
                NEW.conservative_joint_probability,
                NEW.stressed_joint_probability,
                NEW.objective_score,
                NEW.dependence_penalty_applied,
                NEW.published_at,
                NEW.created_at
            ) IS DISTINCT FROM (
                OLD.id,
                OLD.product,
                OLD.optimiser_version,
                OLD.policy_version,
                OLD.combined_odds,
                OLD.conservative_joint_probability,
                OLD.stressed_joint_probability,
                OLD.objective_score,
                OLD.dependence_penalty_applied,
                OLD.published_at,
                OLD.created_at
            ) THEN
                RAISE EXCEPTION 'accumulators evidence columns are immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)


def downgrade() -> None:
    # WARNING: dropping taken_odds permanently destroys any recorded execution prices.
    # Only downgrade on a dev/test schema where that data loss is acceptable.
    op.drop_constraint("ck_settlements_taken_odds_gt_1", "settlements", type_="check")
    op.drop_column("settlements", "taken_odds")

    # Revert _guard_accumulators_identity to the original 4-column version.
    op.execute("""
        CREATE OR REPLACE FUNCTION _guard_accumulators_identity()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.id, NEW.product, NEW.combined_odds, NEW.published_at) IS DISTINCT FROM
               (OLD.id, OLD.product, OLD.combined_odds, OLD.published_at) THEN
                RAISE EXCEPTION 'accumulators identity columns are immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
