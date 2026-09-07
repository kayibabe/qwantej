"""Phase 10: add closing_quote_id to settlements; enforce active-settlement uniqueness

Two schema changes:

1. ``settlements.closing_quote_id`` (nullable UUID FK → odds_quotes.id)
   Stores the exact OddsQuote row used for CLV so the settlement is fully
   reproducible without re-running the closing-odds query (framework §13).

2. Partial unique index ``uq_settlements_active_subject``
   ``UNIQUE (subject_type, subject_id) WHERE supersedes_id IS NULL``
   Enforces at the database level that only one *active* (non-correction)
   settlement row exists per subject.  This makes the application-level
   idempotency guard race-safe: a concurrent worker that passes the
   ``is_already_settled()`` check will still be rejected by the DB, not
   silently create a duplicate.  Corrections (supersedes_id IS NOT NULL)
   are not covered by this index and remain unconstrained in count.

Reversibility: downgrade() drops both objects.  Existing settlement rows
with a non-NULL closing_quote_id would lose that FK link on downgrade, so
treat this as effectively irreversible once real data is written.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c1e3"
down_revision: str | None = "a1b3e7c5f2d9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settlements",
        sa.Column(
            "closing_quote_id",
            sa.UUID(),
            sa.ForeignKey("odds_quotes.id", name="fk_settlements_closing_quote"),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_settlements_active_subject",
        "settlements",
        ["subject_type", "subject_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_settlements_active_subject", table_name="settlements")
    op.drop_column("settlements", "closing_quote_id")
