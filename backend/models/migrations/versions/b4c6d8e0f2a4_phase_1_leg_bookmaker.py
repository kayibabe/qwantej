"""Phase 1: preserve bookmaker attribution on accumulator legs.

The accumulator leg is an immutable paper-ticket snapshot.  Storing the
bookmaker beside the captured price lets the UI identify the executable quote
without reaching back into mutable or later odds data.  Existing rows remain
nullable because older tickets predate this evidence field.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c6d8e0f2a4"
down_revision: str | Sequence[str] | None = "a2b4c6d8e0f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accumulator_legs",
        sa.Column("bookmaker", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accumulator_legs", "bookmaker")
