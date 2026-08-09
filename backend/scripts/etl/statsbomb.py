"""
ETL loader for StatsBomb Open Data.

Enriches historical_fixtures rows with xG values derived from StatsBomb
shot-event data. StatsBomb's open dataset covers selected competitions
(Champions League, La Liga historic, WSL, etc.) with full event feeds.

The loader:
  1. Downloads the competition/season/match index from GitHub.
  2. For each match in the open dataset, downloads shot events.
  3. Computes home_xg and away_xg by summing shot.statsbomb_xg per team.
  4. Upserts the xG onto the existing historical_fixtures row (if found) or
     inserts a new partial row (results may not be in the open data).

GitHub raw base:
  https://raw.githubusercontent.com/statsbomb/open-data/master/data/

Usage:
    python -m scripts.etl.run_etl --source statsbomb
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiohttp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.historical_fixture import HistoricalFixture
from .base import ETLBase

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "statsbomb"
_RAW_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


class StatsBombLoader(ETLBase):
    SOURCE_NAME = "statsbomb"

    async def load(
        self,
        db: AsyncSession,
        use_cache: bool = True,
        max_matches: int | None = None,
    ) -> int:
        """
        Load xG from all StatsBomb open-data competitions.

        Args:
            use_cache: cache raw JSON files locally.
            max_matches: if set, stop after this many matches (useful for dev).
        """
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        ) as http:
            competitions = await self._fetch_json(
                http, f"{_RAW_BASE}/competitions.json",
                _CACHE_DIR / "competitions.json", use_cache,
            )
            if not competitions:
                logger.error("Could not fetch StatsBomb competitions index")
                return 0

            total = 0
            processed = 0
            for comp in competitions:
                comp_id = comp["competition_id"]
                season_id = comp["season_id"]
                season_name = comp.get("season_name", "")

                matches = await self._fetch_json(
                    http,
                    f"{_RAW_BASE}/matches/{comp_id}/{season_id}.json",
                    _CACHE_DIR / f"matches_{comp_id}_{season_id}.json",
                    use_cache,
                )
                if not matches:
                    continue

                for match in matches:
                    if max_matches and processed >= max_matches:
                        return total
                    n = await self._process_match(db, http, match, use_cache)
                    total += n
                    processed += 1

            return total

    async def _process_match(
        self,
        db: AsyncSession,
        http: aiohttp.ClientSession,
        match: dict[str, Any],
        use_cache: bool,
    ) -> int:
        match_id = match.get("match_id")
        match_date_str = match.get("match_date", "")
        if not match_id or not match_date_str:
            return 0

        from datetime import datetime
        try:
            match_date = datetime.strptime(match_date_str, "%Y-%m-%d").date()
        except ValueError:
            return 0

        home_team = self.normalise_team_name(
            match.get("home_team", {}).get("home_team_name", "")
        )
        away_team = self.normalise_team_name(
            match.get("away_team", {}).get("away_team_name", "")
        )
        competition_name = match.get("competition", {}).get("competition_name", "")
        country_name = match.get("competition", {}).get("country_name", "")

        if not home_team or not away_team:
            return 0

        # Pull shot events to compute xG
        events = await self._fetch_json(
            http,
            f"{_RAW_BASE}/events/{match_id}.json",
            _CACHE_DIR / f"events_{match_id}.json",
            use_cache,
        )
        if not events:
            return 0

        home_xg = 0.0
        away_xg = 0.0
        for event in events:
            if event.get("type", {}).get("name") != "Shot":
                continue
            shot_xg = event.get("shot", {}).get("statsbomb_xg", 0.0)
            if not shot_xg:
                continue
            team = event.get("team", {}).get("name", "")
            home_name = match.get("home_team", {}).get("home_team_name", "")
            if team == home_name:
                home_xg += shot_xg
            else:
                away_xg += shot_xg

        home_xg = round(home_xg, 3)
        away_xg = round(away_xg, 3)

        season_year = self.infer_season(match_date)

        # Try to find the existing row and enrich it with xG
        stmt = select(HistoricalFixture).where(
            HistoricalFixture.match_date == match_date,
            HistoricalFixture.home_team == home_team,
            HistoricalFixture.away_team == away_team,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Only overwrite if better xG source (StatsBomb is the gold standard)
            if existing.xg_source != "statsbomb":
                await db.execute(
                    update(HistoricalFixture)
                    .where(HistoricalFixture.id == existing.id)
                    .values(
                        home_xg=home_xg,
                        away_xg=away_xg,
                        xg_source="statsbomb",
                    )
                )
                await db.commit()
            return 1
        else:
            # Insert a partial row — StatsBomb may not have the result
            home_goals = self.safe_int(match.get("home_score"))
            away_goals = self.safe_int(match.get("away_score"))
            row = HistoricalFixture(
                source=self.SOURCE_NAME,
                source_fixture_id=str(match_id),
                match_date=match_date,
                season=season_year,
                country=country_name,
                league=competition_name,
                home_team=home_team,
                away_team=away_team,
                home_goals=home_goals,
                away_goals=away_goals,
                home_xg=home_xg,
                away_xg=away_xg,
                xg_source="statsbomb",
            )
            row.compute_market_outcomes()
            row.compute_data_quality()
            await self.upsert_fixture(db, row)
            return 1

    async def _fetch_json(
        self,
        http: aiohttp.ClientSession,
        url: str,
        cache_path: Path,
        use_cache: bool,
    ) -> list[dict] | None:
        if use_cache and cache_path.exists():
            try:
                return json.loads(cache_path.read_text("utf-8"))
            except Exception:
                pass

        try:
            async with http.get(url) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                if use_cache:
                    cache_path.write_text(
                        json.dumps(data, ensure_ascii=False), "utf-8"
                    )
                return data
        except aiohttp.ClientError as exc:
            logger.warning("StatsBomb fetch error %s: %s", url, exc)
            return None
