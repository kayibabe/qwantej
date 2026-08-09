"""initial postgres baseline

Revision ID: 0001
Revises:
Create Date: 2026-08-09

Tables are created by SQLAlchemy's Base.metadata.create_all() in init_db().
This revision exists solely to establish the Alembic versioning baseline so
that future schema migrations (Phase 1A onwards) can be tracked.

To mark an existing Postgres database as being at this revision without running
any DDL, run:  alembic stamp 0001

"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # Tables created by init_db() (Base.metadata.create_all) on first start


def downgrade() -> None:
    pass
