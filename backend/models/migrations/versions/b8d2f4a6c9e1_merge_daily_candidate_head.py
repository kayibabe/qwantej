"""Merge the ticket-queue and Daily Candidate migration branches."""

from collections.abc import Sequence

revision: str = "b8d2f4a6c9e1"
down_revision: str | Sequence[str] | None = ("a7c4e9d2b1f6", "f8b2d4a6c9e1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
