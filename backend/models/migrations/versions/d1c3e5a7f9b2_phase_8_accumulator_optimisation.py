"""Phase 8: accumulator_optimisation experiment kind; orchestration columns

Adds the schema elements required by the Phase 8 accumulator orchestration
engine (build_accumulator_decision):

1. ``experiment_kind.accumulator_optimisation`` — new ENUM value for
   experiments that log a full accumulator decision run.

2. Four new nullable columns on ``accumulators``:
   - ``input_manifest_hash varchar(128)`` — SHA-256 of the frozen candidate
     pool; binds the ticket irrevocably to its inputs for replay verification.
   - ``risk_state varchar(20)`` — operating state at decision time
     (normal/caution/defensive/review).
   - ``decision_cutoff timestamptz`` — the as_of timestamp passed to the
     engine; required for leakage audits.
   - ``paper_only boolean NOT NULL DEFAULT true`` — Phase 8 is paper-only;
     this flag gates any live publication/locking path.

Reversibility: ``paper_only`` default true is data-safe to drop.
``input_manifest_hash`` / ``risk_state`` / ``decision_cutoff`` are nullable,
so downgrade() can drop them cleanly.  The ENUM value cannot be removed
(Postgres limitation); it is documented in the downgrade docstring.

Revision ID: d1c3e5a7f9b2
Revises: b2d4f6a8c1e3
Create Date: 2026-09-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1c3e5a7f9b2"
down_revision: str | Sequence[str] | None = "b2d4f6a8c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend experiment_kind ENUM.
    # ALTER TYPE … ADD VALUE cannot be rolled back within a transaction, but
    # IF NOT EXISTS makes re-runs safe.
    op.execute(
        "ALTER TYPE experiment_kind ADD VALUE IF NOT EXISTS 'accumulator_optimisation'"
    )

    # 2. Add orchestration columns to accumulators.
    op.add_column(
        "accumulators",
        sa.Column("input_manifest_hash", sa.String(128), nullable=True),
    )
    op.add_column(
        "accumulators",
        sa.Column("risk_state", sa.String(20), nullable=True),
    )
    op.add_column(
        "accumulators",
        sa.Column("decision_cutoff", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "accumulators",
        sa.Column(
            "paper_only",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.create_check_constraint(
        "ck_accumulators_risk_state_valid",
        "accumulators",
        "risk_state IS NULL OR risk_state IN ('normal','caution','defensive','review')",
    )
    op.create_index(
        "ix_accumulators_paper_only", "accumulators", ["paper_only"]
    )
    op.create_index(
        "ix_accumulators_input_manifest_hash",
        "accumulators",
        ["input_manifest_hash"],
    )


def downgrade() -> None:
    # The ENUM value 'accumulator_optimisation' cannot be removed from
    # experiment_kind without dropping and rebuilding the type (which would
    # require migrating the experiments table too). It is left in place.
    op.drop_index("ix_accumulators_input_manifest_hash", table_name="accumulators")
    op.drop_index("ix_accumulators_paper_only", table_name="accumulators")
    op.drop_constraint(
        "ck_accumulators_risk_state_valid", "accumulators", type_="check"
    )
    op.drop_column("accumulators", "paper_only")
    op.drop_column("accumulators", "decision_cutoff")
    op.drop_column("accumulators", "risk_state")
    op.drop_column("accumulators", "input_manifest_hash")
