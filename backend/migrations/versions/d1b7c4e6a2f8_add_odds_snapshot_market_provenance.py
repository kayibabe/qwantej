"""Add provider and market mapping provenance to immutable odds captures.

Revision ID: d1b7c4e6a2f8
Revises: b208d5e9f3a2, c3f8a1d9e2b7
"""

from alembic import op
import sqlalchemy as sa


revision = "d1b7c4e6a2f8"
down_revision = ("b208d5e9f3a2", "c3f8a1d9e2b7")
branch_labels = None
depends_on = None


def upgrade():
    # Leave existing normalized-only snapshots NULL; their provider payloads
    # cannot be reconstructed reliably from legacy market and selection keys.
    op.add_column("odds_snapshots", sa.Column("source_provider", sa.String(50), nullable=True))
    op.add_column("odds_snapshots", sa.Column("provider_market_id", sa.Integer(), nullable=True))
    op.add_column("odds_snapshots", sa.Column("provider_selection_raw", sa.String(200), nullable=True))
    op.add_column("odds_snapshots", sa.Column("provider_line_raw", sa.String(50), nullable=True))
    op.add_column("odds_snapshots", sa.Column("market_catalog_version", sa.String(40), nullable=True))
    op.add_column("odds_snapshots", sa.Column("market_contract_version", sa.String(40), nullable=True))
    op.add_column("odds_snapshots", sa.Column("market_mapping_version", sa.String(40), nullable=True))


def downgrade():
    op.drop_column("odds_snapshots", "market_mapping_version")
    op.drop_column("odds_snapshots", "market_contract_version")
    op.drop_column("odds_snapshots", "market_catalog_version")
    op.drop_column("odds_snapshots", "provider_line_raw")
    op.drop_column("odds_snapshots", "provider_selection_raw")
    op.drop_column("odds_snapshots", "provider_market_id")
    op.drop_column("odds_snapshots", "source_provider")
