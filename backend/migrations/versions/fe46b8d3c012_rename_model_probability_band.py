"""rename model probability band fields for Qwantej

Revision ID: fe46b8d3c012
Revises: fd35a7c2b901
"""

from alembic import op
import sqlalchemy as sa


revision = "fe46b8d3c012"
down_revision = "fd35a7c2b901"
branch_labels = None
depends_on = None


TABLES = (
    "band_mix_pair_states",
    "band_mix_lifecycle_events",
    "band_mix_daily_picks",
)


def _rename_column(old_name: str, new_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in TABLES:
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if old_name in columns and new_name not in columns:
            op.alter_column(table, old_name, new_column_name=new_name)


def upgrade() -> None:
    _rename_column("lohela_band", "qwantej_band")


def downgrade() -> None:
    _rename_column("qwantej_band", "lohela_band")
