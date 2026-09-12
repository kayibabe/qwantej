"""Add an explicit retrospective/research prediction boundary.

Research predictions are derived from mutable historical fixture state and
must never be used as live reliability evidence. The default is ``False`` so
existing and prospective predictions retain the production path.

The downgrade drops the classification column and is therefore only suitable
for a disposable schema where that classification data is not required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d8e0f2a4b1"
down_revision: str | None = "a4b6c8d0e2f4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("research_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("predictions", "research_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("predictions", "research_mode")
