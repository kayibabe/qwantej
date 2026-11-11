"""add no-vig probability and closing-quote provenance

Adds two nullable columns to `predictions`:

- `source_fair_probability`: proportional no-vig probability from the entry
  quote set, alongside the existing margin-inclusive
  `source_implied_probability`.
- `closing_bookmaker`: provenance for `closing_decimal_odds`, so a consumer can
  tell a genuine post-entry close from a stale or same-fetch value.

Both are additive and idempotent; existing rows stay NULL.
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c1e2f3a4d5"
down_revision = "c3a9f1d2e4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("predictions")}
    additions = (
        ("source_fair_probability", sa.Column("source_fair_probability", sa.Float(), nullable=True)),
        ("closing_bookmaker", sa.Column("closing_bookmaker", sa.String(length=100), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("predictions", column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("predictions")}
    for name in ("closing_bookmaker", "source_fair_probability"):
        if name in columns:
            op.drop_column("predictions", name)
