"""Phase 1B — Elo ratings table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-09

Adds:
  - elo_ratings  (persisted Elo rating per team/league/season)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "elo_ratings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("team_name", sa.String(120), nullable=False),
        sa.Column("league", sa.String(120), nullable=False),
        sa.Column("country", sa.String(120), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False, server_default="1500.0"),
        sa.Column("n_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_match_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    op.create_index("ix_elo_ratings_team_name", "elo_ratings", ["team_name"])
    op.create_index("ix_elo_ratings_league", "elo_ratings", ["league"])
    op.create_unique_constraint(
        "uq_elo_ratings_team_league_season",
        "elo_ratings",
        ["team_name", "league", "season"],
    )


def downgrade() -> None:
    op.drop_table("elo_ratings")
