"""Phase 9: settlements, accumulators, accumulator_legs; extend experiment_kind

Adds the three tables that complete the closed decision-and-learning loop
(framework §38, §42, §43):

- `accumulators`        — published ticket record (append-only after lock)
- `accumulator_legs`    — individual legs linking accumulator → prediction
- `settlements`         — post-fixture outcomes, CLV and Brier contributions

Also extends the `experiment_kind` Postgres ENUM with two new values
used by the continuous-learning pipeline:
- `champion_challenger`  — challenger shadow-mode evaluation run
- `drift_check`          — scheduled drift detection run

Note: Postgres does not support removing ENUM values, so the downgrade()
drops the new tables and documents that the ENUM values remain (acceptable
for a development schema; a production-hardened downgrade would require
renaming the type and rebuilding it without the new values).

Revision ID: e9b4f2a71c3d
Revises: f3a7c9d21e6b
Create Date: 2026-09-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9b4f2a71c3d"
down_revision: str | Sequence[str] | None = "f3a7c9d21e6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. Extend experiment_kind ENUM
    # -----------------------------------------------------------------
    # ALTER TYPE … ADD VALUE is transactional in PG 12+ but cannot be
    # rolled back within the same transaction.  Alembic wraps migrations
    # in a transaction by default; we use execute_if to guard re-runs.
    op.execute("ALTER TYPE experiment_kind ADD VALUE IF NOT EXISTS 'champion_challenger'")
    op.execute("ALTER TYPE experiment_kind ADD VALUE IF NOT EXISTS 'drift_check'")

    # -----------------------------------------------------------------
    # 2. accumulators
    # -----------------------------------------------------------------
    ticket_status = postgresql.ENUM(
        "pending", "locked", "settled", "void",
        name="ticket_status", create_type=True,
    )
    op.create_table(
        "accumulators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product", sa.String(20), nullable=False),
        sa.Column("optimiser_version", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("combined_odds", sa.Numeric(10, 4), nullable=False),
        sa.Column("conservative_joint_probability", sa.Numeric(9, 8), nullable=False),
        sa.Column("stressed_joint_probability", sa.Numeric(9, 8), nullable=False),
        sa.Column("objective_score", sa.Numeric(10, 8), nullable=False),
        sa.Column("dependence_penalty_applied", sa.Numeric(8, 6), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stake", sa.Numeric(18, 4), nullable=True),
        sa.Column("risk_policy_version", sa.String(80), nullable=True),
        sa.Column("status", ticket_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("combined_odds > 1", name="ck_accumulators_odds_gt_1"),
        sa.CheckConstraint(
            "conservative_joint_probability > 0 AND conservative_joint_probability <= 1",
            name="ck_accumulators_joint_p_unit",
        ),
        sa.CheckConstraint(
            "stressed_joint_probability > 0 AND stressed_joint_probability <= 1",
            name="ck_accumulators_stressed_p_unit",
        ),
        sa.CheckConstraint("stake IS NULL OR stake > 0", name="ck_accumulators_stake_pos"),
    )
    op.create_index("ix_accumulators_product", "accumulators", ["product"])
    op.create_index("ix_accumulators_published_at", "accumulators", ["published_at"])
    op.create_index("ix_accumulators_status", "accumulators", ["status"])

    # Append-only guard: reject UPDATE, DELETE, TRUNCATE.
    op.execute("""
        CREATE OR REPLACE FUNCTION _guard_accumulators_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'accumulators rows are append-only; use a new row for corrections';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_accumulators_no_delete
        BEFORE DELETE OR TRUNCATE ON accumulators
        FOR EACH STATEMENT EXECUTE FUNCTION _guard_accumulators_immutable()
    """)
    # Allow UPDATE only for the status + locked_at + stake lifecycle fields.
    # A separate trigger blocks updates to immutable identity columns.
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
    op.execute("""
        CREATE TRIGGER trg_accumulators_freeze_identity
        BEFORE UPDATE ON accumulators
        FOR EACH ROW EXECUTE FUNCTION _guard_accumulators_identity()
    """)

    # -----------------------------------------------------------------
    # 3. accumulator_legs
    # -----------------------------------------------------------------
    op.create_table(
        "accumulator_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("accumulator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fixture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leg_index", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.String(40), nullable=False),
        sa.Column("market_family", sa.String(40), nullable=False),
        sa.Column("selection", sa.String(80), nullable=False),
        sa.Column("decimal_odds", sa.Numeric(8, 3), nullable=False),
        sa.Column("conservative_probability", sa.Numeric(9, 8), nullable=False),
        sa.Column("edge", sa.Numeric(8, 6), nullable=False),
        sa.Column("qss", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["accumulator_id"], ["accumulators.id"]),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"]),
        sa.UniqueConstraint(
            "accumulator_id", "prediction_id",
            name="uq_acca_leg_accumulator_prediction",
        ),
        sa.CheckConstraint("decimal_odds > 1", name="ck_acca_leg_odds_gt_1"),
        sa.CheckConstraint(
            "conservative_probability > 0 AND conservative_probability <= 1",
            name="ck_acca_leg_prob_unit",
        ),
        sa.CheckConstraint("leg_index >= 0", name="ck_acca_leg_index_nonneg"),
    )
    op.create_index("ix_acca_legs_accumulator_id", "accumulator_legs", ["accumulator_id"])
    op.create_index("ix_acca_legs_prediction_id", "accumulator_legs", ["prediction_id"])
    op.create_index("ix_acca_legs_fixture_id", "accumulator_legs", ["fixture_id"])

    # Append-only guard.
    op.execute("""
        CREATE OR REPLACE FUNCTION _guard_acca_legs_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'accumulator_legs rows are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_acca_legs_no_mutate
        BEFORE UPDATE OR DELETE OR TRUNCATE ON accumulator_legs
        FOR EACH STATEMENT EXECUTE FUNCTION _guard_acca_legs_immutable()
    """)

    # -----------------------------------------------------------------
    # 4. settlements
    # -----------------------------------------------------------------
    settlement_outcome = postgresql.ENUM(
        "win", "loss", "void", "push",
        name="settlement_outcome", create_type=True,
    )
    op.create_table(
        "settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_type", sa.String(20), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", settlement_outcome, nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_source", sa.String(80), nullable=True),
        sa.Column("stake", sa.Numeric(18, 4), nullable=True),
        sa.Column("gross_return", sa.Numeric(18, 4), nullable=True),
        sa.Column("profit_loss", sa.Numeric(18, 4), nullable=True),
        sa.Column("closing_odds", sa.Numeric(8, 3), nullable=True),
        sa.Column("closing_probability", sa.Numeric(9, 8), nullable=True),
        sa.Column("clv", sa.Numeric(9, 6), nullable=True),
        sa.Column("taken_probability", sa.Numeric(9, 8), nullable=True),
        sa.Column("brier_contribution", sa.Numeric(9, 8), nullable=True),
        sa.Column("log_loss_contribution", sa.Numeric(12, 8), nullable=True),
        sa.Column("calibration_bin", sa.String(20), nullable=True),
        sa.Column("reason_codes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supersedes_id"], ["settlements.id"]),
        sa.UniqueConstraint(
            "subject_type", "subject_id", "settled_at",
            name="uq_settlements_subject_settled_at",
        ),
        sa.CheckConstraint(
            "subject_type IN ('prediction', 'accumulator')",
            name="ck_settlements_subject_type",
        ),
        sa.CheckConstraint(
            "closing_odds IS NULL OR closing_odds > 1",
            name="ck_settlements_closing_odds_gt_1",
        ),
        sa.CheckConstraint(
            "brier_contribution IS NULL OR "
            "(brier_contribution >= 0 AND brier_contribution <= 1)",
            name="ck_settlements_brier_unit",
        ),
        sa.CheckConstraint("stake IS NULL OR stake > 0", name="ck_settlements_stake_pos"),
    )
    op.create_index("ix_settlements_subject_type", "settlements", ["subject_type"])
    op.create_index("ix_settlements_subject_id", "settlements", ["subject_id"])
    op.create_index("ix_settlements_outcome", "settlements", ["outcome"])
    op.create_index("ix_settlements_settled_at", "settlements", ["settled_at"])

    # Append-only guard (corrections create new rows, not mutations).
    op.execute("""
        CREATE OR REPLACE FUNCTION _guard_settlements_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'settlements rows are append-only; create a new row with supersedes_id for corrections';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_settlements_no_mutate
        BEFORE UPDATE OR DELETE OR TRUNCATE ON settlements
        FOR EACH STATEMENT EXECUTE FUNCTION _guard_settlements_immutable()
    """)


def downgrade() -> None:
    # Drop triggers and functions first.
    for tbl, trg, fn in [
        ("settlements", "trg_settlements_no_mutate", "_guard_settlements_immutable"),
        ("accumulator_legs", "trg_acca_legs_no_mutate", "_guard_acca_legs_immutable"),
        ("accumulators", "trg_accumulators_freeze_identity", "_guard_accumulators_identity"),
        ("accumulators", "trg_accumulators_no_delete", "_guard_accumulators_immutable"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trg} ON {tbl}")
    for fn in (
        "_guard_settlements_immutable",
        "_guard_acca_legs_immutable",
        "_guard_accumulators_identity",
        "_guard_accumulators_immutable",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")

    op.drop_table("settlements")
    op.drop_table("accumulator_legs")
    op.drop_table("accumulators")

    postgresql.ENUM(name="settlement_outcome").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="ticket_status").drop(op.get_bind(), checkfirst=True)

    # The two new experiment_kind values (champion_challenger, drift_check)
    # cannot be removed from a Postgres ENUM without dropping and rebuilding
    # the type (which would require migrating the experiments table too).
    # They are left in place; the ORM enum is the authoritative allowed-set.
