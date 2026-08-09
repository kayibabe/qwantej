"""
ETL loader for OpenFootball JSON data.

OpenFootball publishes result-only JSON at:
  https://raw.githubusercontent.com/openfootball/football.json/master/

This supplements Football-Data.co.uk coverage, particularly for German
(Bundesliga) and other leagues that the CSV source may not fully cover.

Covers: results only (goals, date, teams). No odds, no stats.

Usage:
    python -m scripts.etl.run_etl --source openfootball --seasons 2023 2024
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.historical_fixture import HistoricalFixture
from .base import ETLBase

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "openfootball"
_RAW_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"

# Season path → (country, league_name)
# Key format: "{start_year}-{2-digit-end}" e.g. "2024-25"
# Value: URL path fragment, country, league name
COMPETITIONS: list[dict[str, str]] = [
    {"path": "en.1",  "country": "England",     "league": "Premier League"},
    {"path": "en.2",  "country": "England",     "league": "Championship"},
    {"path": "de.1",  "country": "Germany",     "league": "Bundesliga"},
    {"path": "de.2",  "country": "Germany",     "league": "2. Bundesliga"},
    {"path": "es.1",  "country": "Spain",       "league": "La Liga"},
    {"path": "es.2",  "country": "Spain",       "league": "La Liga 2"},
    {"path": "it.1",  "country": "Italy",       "league": "Serie A"},
    {"path": "it.2",  "country": "Italy",       "league": "Serie B"},
    {"path": "fr.1",  "country": "France",      "league": "Ligue 1"},
    {"path": "fr.2",  "country": "France",      "league": "Ligue 2"},
    {"path": "nl.1",  "country": "Netherlands", "league": "Eredivisie"},
    {"path": "pt.1",  "country": "Portugal",    "league": "Primeira Liga"},
    {"path": "be.1",  "country": "Belgium",     "league": "First Division A"},
    {"path": "at.1",  "country": "Austria",     "league": "Bundesliga"},
    {"path": "ru.1",  "country": "Russia",      "league": "Premier Liga"},
]


def _season_path(start_year: int) -> str:
    """2024 → '2024-25'."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


class OpenFootballLoader(ETLBase):
    SOURCE_NAME = "openfootball"

    async def load(
        self,
        db: AsyncSession,
        seasons: list[int] | None = None,
        competitions: list[str] | None = None,
        use_cache: bool = True,
    ) -> int:
        """
        Args:
            seasons: list of season start years.
            competitions: list of path codes (e.g. ["en.1", "de.1"]).
                          Defaults to all in COMPETITIONS.
            use_cache: cache raw JSON files locally.
        """
        if seasons is None:
            current_year = datetime.today().year
            seasons = list(range(current_year - 5, current_year))

        allowed_paths = set(competitions) if competitions else None
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        ) as http:
            for season_start in seasons:
                season_path = _season_path(season_start)
                for comp in COMPETITIONS:
                    if allowed_paths and comp["path"] not in allowed_paths:
                        continue
                    count = await self._load_one(
                        db, http, season_start, season_path, comp, use_cache
                    )
                    logger.info(
                        "openfootball %s/%s (%s %s): %d rows upserted",
                        season_path, comp["path"],
                        comp["country"], comp["league"], count,
                    )
                    total += count

        return total

    async def _load_one(
        self,
        db: AsyncSession,
        http: aiohttp.ClientSession,
        season_start: int,
        season_path: str,
        comp: dict[str, str],
        use_cache: bool,
    ) -> int:
        url = f"{_RAW_BASE}/{season_path}/{comp['path']}.json"
        cache_path = _CACHE_DIR / f"{season_path.replace('-', '_')}_{comp['path'].replace('.', '_')}.json"

        data = await self._fetch_json(http, url, cache_path, use_cache)
        if data is None:
            return 0

        return await self._parse_and_upsert(db, data, season_start, comp)

    async def _parse_and_upsert(
        self,
        db: AsyncSession,
        data: dict,
        season_start: int,
        comp: dict[str, str],
    ) -> int:
        count = 0
        for rnd in data.get("rounds", []):
            for match in rnd.get("matches", []):
                row = self._parse_match(match, season_start, comp)
                if row is None:
                    continue
                row.compute_market_outcomes()
                row.compute_data_quality()
                await self.upsert_fixture(db, row)
                count += 1
        return count

    def _parse_match(
        self,
        match: dict[str, Any],
        season_start: int,
        comp: dict[str, str],
    ) -> HistoricalFixture | None:
        date_str = match.get("date", "")
        if not date_str:
            return None
        try:
            match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

        team1 = self.normalise_team_name(match.get("team1", ""))
        team2 = self.normalise_team_name(match.get("team2", ""))
        if not team1 or not team2:
            return None

        score = match.get("score", {})
        ft = score.get("ft") if score else None

        home_goals = self.safe_int(ft[0]) if ft and len(ft) >= 1 else None
        away_goals = self.safe_int(ft[1]) if ft and len(ft) >= 2 else None

        ht = score.get("ht") if score else None
        home_goals_ht = self.safe_int(ht[0]) if ht and len(ht) >= 1 else None
        away_goals_ht = self.safe_int(ht[1]) if ht and len(ht) >= 2 else None

        return HistoricalFixture(
            source=self.SOURCE_NAME,
            source_fixture_id=None,
            match_date=match_date,
            season=season_start,
            country=comp["country"],
            league=comp["league"],
            home_team=team1,
            away_team=team2,
            home_goals=home_goals,
            away_goals=away_goals,
            home_goals_ht=home_goals_ht,
            away_goals_ht=away_goals_ht,
        )

    async def _fetch_json(
        self,
        http: aiohttp.ClientSession,
        url: str,
        cache_path: Path,
        use_cache: bool,
    ) -> dict | None:
        if use_cache and cache_path.exists():
            try:
                return json.loads(cache_path.read_text("utf-8"))
            except Exception:
                pass

        try:
            async with http.get(url) as resp:
                if resp.status == 404:
                    logger.debug("Not found: %s", url)
                    return None
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                if use_cache:
                    cache_path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
                return data
        except aiohttp.ClientError as exc:
            logger.warning("OpenFootball fetch error %s: %s", url, exc)
            return None
