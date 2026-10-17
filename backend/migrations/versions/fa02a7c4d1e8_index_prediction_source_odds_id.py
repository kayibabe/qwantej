"""index prediction source odds foreign key for efficient refresh cleanup"""

from alembic import op
import sqlalchemy as sa

revision = "fa02a7c4d1e8"
down_revision = "f9d1e4a8b6c2"
branch_labels = None
depends_on = None


def upgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("predictions")}
    if "ix_predictions_source_odds_id" not in indexes:
        op.create_index(
            "ix_predictions_source_odds_id",
            "predictions",
            ["source_odds_id"],
        )


def downgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("predictions")}
    if "ix_predictions_source_odds_id" in indexes:
        op.drop_index("ix_predictions_source_odds_id", table_name="predictions")
