"""
Abstract base class for all historical-fixture ETL loaders.

Each loader subclass implements:
  - SOURCE_NAME  — identifier stored in historical_fixtures.source
  - load(db, **kwargs) → int  — upsert rows, return count upserted

Common helpers live here: upsert_fixture, normalise_team_name, etc.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.historical_fixture import HistoricalFixture

logger = logging.getLogger(__name__)


class ETLBase(ABC):
    SOURCE_NAME: str = ""

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def load(self, db: AsyncSession, **kwargs: Any) -> int:
        """Load data into historical_fixtures. Returns number of rows upserted."""
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def upsert_fixture(
        self,
        db: AsyncSession,
        row: HistoricalFixture,
    ) -> bool:
        """
        INSERT ... ON CONFLICT (match_date, league, home_team, away_team)
        DO UPDATE only the fields that are non-None in `row`.

        Returns True if a new row was inserted, False if an existing row
        was updated.
        """
        # Build the values dict
        values: dict[str, Any] = {
            "source": row.source,
            "source_fixture_id": row.source_fixture_id,
            "match_date": row.match_date,
            "season": row.season,
            "country": row.country,
            "league": row.league,
            "league_id": row.league_id,
            "home_team": row.home_team,
            "away_team": row.away_team,
            "home_goals": row.home_goals,
            "away_goals": row.away_goals,
            "result": row.result,
            "home_goals_ht": row.home_goals_ht,
            "away_goals_ht": row.away_goals_ht,
            "btts": row.btts,
            "over_1_5": row.over_1_5,
            "over_2_5": row.over_2_5,
            "over_3_5": row.over_3_5,
            "under_2_5": row.under_2_5,
            "under_3_5": row.under_3_5,
            "home_shots": row.home_shots,
            "away_shots": row.away_shots,
            "home_shots_on_target": row.home_shots_on_target,
            "away_shots_on_target": row.away_shots_on_target,
            "home_corners": row.home_corners,
            "away_corners": row.away_corners,
            "home_yellow_cards": row.home_yellow_cards,
            "away_yellow_cards": row.away_yellow_cards,
            "home_red_cards": row.home_red_cards,
            "away_red_cards": row.away_red_cards,
            "home_fouls": row.home_fouls,
            "away_fouls": row.away_fouls,
            "home_possession": row.home_possession,
            "home_xg": row.home_xg,
            "away_xg": row.away_xg,
            "xg_source": row.xg_source,
            "odds_home_win": row.odds_home_win,
            "odds_draw": row.odds_draw,
            "odds_away_win": row.odds_away_win,
            "odds_over_1_5": row.odds_over_1_5,
            "odds_under_1_5": row.odds_under_1_5,
            "odds_over_2_5": row.odds_over_2_5,
            "odds_under_2_5": row.odds_under_2_5,
            "odds_over_3_5": row.odds_over_3_5,
            "odds_under_3_5": row.odds_under_3_5,
            "odds_btts_yes": row.odds_btts_yes,
            "odds_btts_no": row.odds_btts_no,
            "data_quality": row.data_quality,
        }

        # On conflict: only overwrite fields that are explicitly set (non-None)
        # in this row, to allow incremental enrichment from secondary sources.
        update_set = {
            k: v for k, v in values.items()
            if v is not None and k not in ("match_date", "league", "home_team", "away_team")
        }
        # Always bump data_quality even if other fields are None
        if row.data_quality is not None:
            update_set["data_quality"] = row.data_quality

        stmt = (
            pg_insert(HistoricalFixture)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_historical_fixtures_match",
                set_=update_set,
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        # rowcount == 1 for insert, 2 for update (PostgreSQL ON CONFLICT returns 2)
        return result.rowcount == 1

    # ------------------------------------------------------------------
    # Normalisation utilities
    # ------------------------------------------------------------------

    @staticmethod
    def normalise_team_name(name: str) -> str:
        """Strip common suffixes and normalise whitespace for matching."""
        name = name.strip()
        # Remove trailing country codes in brackets, e.g. "Arsenal (ENG)"
        name = re.sub(r"\s*\([A-Z]{2,3}\)$", "", name)
        return name

    @staticmethod
    def safe_float(val: Any, minimum: float | None = None) -> float | None:
        """Parse a value to float; return None on failure."""
        if val is None or val == "" or val != val:  # NaN check
            return None
        try:
            f = float(val)
            if minimum is not None and f < minimum:
                return None
            return f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def safe_int(val: Any) -> int | None:
        """Parse a value to int; return None on failure."""
        if val is None or val == "":
            return None
        try:
            return int(float(str(val).strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def infer_season(match_date: date) -> int:
        """
        Return the start year of the season containing match_date.
        Seasons run roughly August–May so a June match belongs to the
        just-completed season, while an August match starts the new one.
        """
        return match_date.year if match_date.month >= 7 else match_date.year - 1
