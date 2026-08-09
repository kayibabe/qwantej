"""Phase 1A — historical warehouse tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09

Adds:
  - historical_fixtures   (canonical match warehouse row)
  - forecast_snapshots    (per-fixture × market × horizon model snapshot)
  - data_source_experiments (A/B Brier comparisons per source)
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_fixtures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),

        # Source
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("source_fixture_id", sa.String(120), nullable=True),

        # Match identity
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("country", sa.String(120), nullable=False),
        sa.Column("league", sa.String(120), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("home_team", sa.String(120), nullable=False),
        sa.Column("away_team", sa.String(120), nullable=False),

        # Full-time result
        sa.Column("home_goals", sa.SmallInteger(), nullable=True),
        sa.Column("away_goals", sa.SmallInteger(), nullable=True),
        sa.Column("result", sa.String(1), nullable=True),

        # Half-time result
        sa.Column("home_goals_ht", sa.SmallInteger(), nullable=True),
        sa.Column("away_goals_ht", sa.SmallInteger(), nullable=True),

        # Pre-computed market outcomes
        sa.Column("btts", sa.Boolean(), nullable=True),
        sa.Column("over_1_5", sa.Boolean(), nullable=True),
        sa.Column("over_2_5", sa.Boolean(), nullable=True),
        sa.Column("over_3_5", sa.Boolean(), nullable=True),
        sa.Column("under_2_5", sa.Boolean(), nullable=True),
        sa.Column("under_3_5", sa.Boolean(), nullable=True),

        # Match stats
        sa.Column("home_shots", sa.SmallInteger(), nullable=True),
        sa.Column("away_shots", sa.SmallInteger(), nullable=True),
        sa.Column("home_shots_on_target", sa.SmallInteger(), nullable=True),
        sa.Column("away_shots_on_target", sa.SmallInteger(), nullable=True),
        sa.Column("home_corners", sa.SmallInteger(), nullable=True),
        sa.Column("away_corners", sa.SmallInteger(), nullable=True),
        sa.Column("home_yellow_cards", sa.SmallInteger(), nullable=True),
        sa.Column("away_yellow_cards", sa.SmallInteger(), nullable=True),
        sa.Column("home_red_cards", sa.SmallInteger(), nullable=True),
        sa.Column("away_red_cards", sa.SmallInteger(), nullable=True),
        sa.Column("home_fouls", sa.SmallInteger(), nullable=True),
        sa.Column("away_fouls", sa.SmallInteger(), nullable=True),
        sa.Column("home_possession", sa.Float(), nullable=True),

        # xG
        sa.Column("home_xg", sa.Float(), nullable=True),
        sa.Column("away_xg", sa.Float(), nullable=True),
        sa.Column("xg_source", sa.String(60), nullable=True),

        # Pre-match odds
        sa.Column("odds_home_win", sa.Float(), nullable=True),
        sa.Column("odds_draw", sa.Float(), nullable=True),
        sa.Column("odds_away_win", sa.Float(), nullable=True),
        sa.Column("odds_over_1_5", sa.Float(), nullable=True),
        sa.Column("odds_under_1_5", sa.Float(), nullable=True),
        sa.Column("odds_over_2_5", sa.Float(), nullable=True),
        sa.Column("odds_under_2_5", sa.Float(), nullable=True),
        sa.Column("odds_over_3_5", sa.Float(), nullable=True),
        sa.Column("odds_under_3_5", sa.Float(), nullable=True),
        sa.Column("odds_btts_yes", sa.Float(), nullable=True),
        sa.Column("odds_btts_no", sa.Float(), nullable=True),

        sa.Column("data_quality", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_historical_fixtures_match_date", "historical_fixtures", ["match_date"])
    op.create_index("ix_historical_fixtures_season", "historical_fixtures", ["season"])
    op.create_index("ix_historical_fixtures_league", "historical_fixtures", ["league"])
    op.create_index("ix_historical_fixtures_country", "historical_fixtures", ["country"])
    op.create_index("ix_historical_fixtures_source", "historical_fixtures", ["source"])
    op.create_index("ix_historical_fixtures_source_fixture_id", "historical_fixtures", ["source_fixture_id"])
    op.create_unique_constraint(
        "uq_historical_fixtures_match",
        "historical_fixtures",
        ["match_date", "league", "home_team", "away_team"],
    )

    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.Integer(),
                  sa.ForeignKey("fixtures.id", ondelete="SET NULL"), nullable=True),
        sa.Column("historical_fixture_id", sa.Integer(),
                  sa.ForeignKey("historical_fixtures.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(20), nullable=False),
        sa.Column("market", sa.String(80), nullable=False),

        # Model probabilities
        sa.Column("zinb_prob", sa.Float(), nullable=True),
        sa.Column("bayesian_prob", sa.Float(), nullable=True),
        sa.Column("elo_prob", sa.Float(), nullable=True),
        sa.Column("ensemble_prob", sa.Float(), nullable=False),
        sa.Column("calibrated_prob", sa.Float(), nullable=True),

        # Signal decision
        sa.Column("signal_type", sa.String(20), nullable=False, server_default="NO_SIGNAL"),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("data_quality_score", sa.Float(), nullable=True),

        # Odds
        sa.Column("fair_odds", sa.Float(), nullable=True),
        sa.Column("market_odds", sa.Float(), nullable=True),
        sa.Column("value_edge", sa.Float(), nullable=True),
        sa.Column("is_value_bet", sa.Boolean(), nullable=False, server_default="false"),

        # Raw inputs
        sa.Column("lambda_home", sa.Float(), nullable=True),
        sa.Column("lambda_away", sa.Float(), nullable=True),
        sa.Column("elo_home", sa.Float(), nullable=True),
        sa.Column("elo_away", sa.Float(), nullable=True),
        sa.Column("form_home", sa.Float(), nullable=True),
        sa.Column("form_away", sa.Float(), nullable=True),

        # Outcome
        sa.Column("outcome", sa.String(10), nullable=True),
        sa.Column("actual_home_goals", sa.Integer(), nullable=True),
        sa.Column("actual_away_goals", sa.Integer(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),

        sa.Column("model_version", sa.String(30), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_forecast_snapshots_fixture_market",
                    "forecast_snapshots", ["fixture_id", "market"])
    op.create_index("ix_forecast_snapshots_hist_market",
                    "forecast_snapshots", ["historical_fixture_id", "market"])
    op.create_index("ix_forecast_snapshots_snapshot_at",
                    "forecast_snapshots", ["snapshot_at"])
    op.create_index("ix_forecast_snapshots_signal_type",
                    "forecast_snapshots", ["signal_type"])

    op.create_table(
        "data_source_experiments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("market", sa.String(80), nullable=False),
        sa.Column("league", sa.String(120), nullable=True),
        sa.Column("experiment_start", sa.Date(), nullable=False),
        sa.Column("experiment_end", sa.Date(), nullable=False),
        sa.Column("baseline_brier", sa.Float(), nullable=False),
        sa.Column("baseline_n", sa.Integer(), nullable=False),
        sa.Column("source_brier", sa.Float(), nullable=False),
        sa.Column("source_n", sa.Integer(), nullable=False),
        sa.Column("brier_improvement", sa.Float(), nullable=False),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_data_source_experiments_source",
                    "data_source_experiments", ["source"])


def downgrade() -> None:
    op.drop_table("data_source_experiments")
    op.drop_table("forecast_snapshots")
    op.drop_table("historical_fixtures")
