"""
ETL loader for Football-Data.co.uk CSV files.

Downloads per-league per-season CSVs and upserts into historical_fixtures.
Covers results + pre-match B365 odds + full match stats back to ~1993.

Usage:
    python -m scripts.etl.run_etl --source fdcuk --seasons 2023 2024 --leagues all
    python -m scripts.etl.run_etl --source fdcuk --seasons 2024 --leagues E0 SP1
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiohttp
import csv

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.historical_fixture import HistoricalFixture
from .base import ETLBase

logger = logging.getLogger(__name__)

# Cache directory for downloaded CSVs
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "football_data_co_uk"

# Football-Data.co.uk division codes → (country, league_name)
DIVISIONS: dict[str, tuple[str, str]] = {
    "E0":  ("England", "Premier League"),
    "E1":  ("England", "Championship"),
    "E2":  ("England", "League One"),
    "E3":  ("England", "League Two"),
    "SP1": ("Spain", "La Liga"),
    "SP2": ("Spain", "La Liga 2"),
    "D1":  ("Germany", "Bundesliga"),
    "D2":  ("Germany", "2. Bundesliga"),
    "I1":  ("Italy", "Serie A"),
    "I2":  ("Italy", "Serie B"),
    "F1":  ("France", "Ligue 1"),
    "F2":  ("France", "Ligue 2"),
    "B1":  ("Belgium", "First Division A"),
    "N1":  ("Netherlands", "Eredivisie"),
    "P1":  ("Portugal", "Primeira Liga"),
    "SC0": ("Scotland", "Scottish Premiership"),
    "T1":  ("Turkey", "Super Lig"),
    "G1":  ("Greece", "Super League"),
}

_BASE_URL = "https://www.football-data.co.uk/mmz4281"


def _season_code(start_year: int) -> str:
    """2024 → '2425', 2023 → '2324'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _parse_date(raw: str) -> date | None:
    """Handle DD/MM/YY and DD/MM/YYYY formats."""
    raw = raw.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class FootballDataCoUkLoader(ETLBase):
    SOURCE_NAME = "football_data_co_uk"

    async def load(
        self,
        db: AsyncSession,
        seasons: list[int] | None = None,
        divisions: list[str] | None = None,
        use_cache: bool = True,
    ) -> int:
        """
        Download and upsert Football-Data.co.uk CSV data.

        Args:
            seasons: list of season start years, e.g. [2022, 2023, 2024].
                     Defaults to the last 5 complete seasons.
            divisions: list of division codes (e.g. ["E0", "SP1"]).
                       Defaults to all divisions in DIVISIONS.
            use_cache: if True, serve from .cache/ if file already downloaded.
        """
        if seasons is None:
            current_year = date.today().year
            seasons = list(range(current_year - 5, current_year))
        if divisions is None:
            divisions = list(DIVISIONS.keys())

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        total = 0

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        ) as http:
            for season in seasons:
                season_code = _season_code(season)
                for div_code in divisions:
                    if div_code not in DIVISIONS:
                        logger.warning("Unknown division code %s — skipping", div_code)
                        continue
                    country, league = DIVISIONS[div_code]
                    count = await self._load_one(
                        db, http, season, season_code, div_code,
                        country, league, use_cache,
                    )
                    logger.info(
                        "%s/%s (%s %s): %d rows upserted",
                        season_code, div_code, country, league, count,
                    )
                    total += count

        return total

    async def _load_one(
        self,
        db: AsyncSession,
        http: aiohttp.ClientSession,
        season: int,
        season_code: str,
        div_code: str,
        country: str,
        league: str,
        use_cache: bool,
    ) -> int:
        csv_bytes = await self._fetch_csv(http, season_code, div_code, use_cache)
        if csv_bytes is None:
            return 0
        return await self._parse_and_upsert(db, csv_bytes, season, country, league)

    async def _fetch_csv(
        self,
        http: aiohttp.ClientSession,
        season_code: str,
        div_code: str,
        use_cache: bool,
    ) -> bytes | None:
        cache_path = _CACHE_DIR / f"{season_code}_{div_code}.csv"
        if use_cache and cache_path.exists():
            return cache_path.read_bytes()

        url = f"{_BASE_URL}/{season_code}/{div_code}.csv"
        try:
            async with http.get(url) as resp:
                if resp.status == 404:
                    logger.debug("Not found: %s", url)
                    return None
                resp.raise_for_status()
                data = await resp.read()
                if use_cache:
                    cache_path.write_bytes(data)
                return data
        except aiohttp.ClientError as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            return None

    async def _parse_and_upsert(
        self,
        db: AsyncSession,
        csv_bytes: bytes,
        season: int,
        country: str,
        league: str,
    ) -> int:
        # Decode — Football-Data.co.uk files are latin-1
        text = csv_bytes.decode("latin-1", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        count = 0
        for raw in reader:
            row = self._parse_row(raw, season, country, league)
            if row is None:
                continue
            row.compute_market_outcomes()
            row.compute_data_quality()
            await self.upsert_fixture(db, row)
            count += 1

        return count

    def _parse_row(
        self,
        raw: dict[str, str],
        season: int,
        country: str,
        league: str,
    ) -> HistoricalFixture | None:
        date_str = raw.get("Date", "").strip()
        if not date_str:
            return None
        match_date = _parse_date(date_str)
        if match_date is None:
            return None

        home = self.normalise_team_name(raw.get("HomeTeam", "") or raw.get("Home", ""))
        away = self.normalise_team_name(raw.get("AwayTeam", "") or raw.get("Away", ""))
        if not home or not away:
            return None

        row = HistoricalFixture(
            source=self.SOURCE_NAME,
            source_fixture_id=None,
            match_date=match_date,
            season=season,
            country=country,
            league=league,
            home_team=home,
            away_team=away,
            home_goals=self.safe_int(raw.get("FTHG") or raw.get("HG")),
            away_goals=self.safe_int(raw.get("FTAG") or raw.get("AG")),
            home_goals_ht=self.safe_int(raw.get("HTHG")),
            away_goals_ht=self.safe_int(raw.get("HTAG")),
            # Stats
            home_shots=self.safe_int(raw.get("HS")),
            away_shots=self.safe_int(raw.get("AS")),
            home_shots_on_target=self.safe_int(raw.get("HST")),
            away_shots_on_target=self.safe_int(raw.get("AST")),
            home_corners=self.safe_int(raw.get("HC")),
            away_corners=self.safe_int(raw.get("AC")),
            home_yellow_cards=self.safe_int(raw.get("HY")),
            away_yellow_cards=self.safe_int(raw.get("AY")),
            home_red_cards=self.safe_int(raw.get("HR")),
            away_red_cards=self.safe_int(raw.get("AR")),
            home_fouls=self.safe_int(raw.get("HF")),
            away_fouls=self.safe_int(raw.get("AF")),
            # Best available odds: prefer Bet365 (B365), fall back to BW, then IW
            odds_home_win=self._best_odd(raw, ("B365H", "BWH", "IWH", "PSH", "WHH")),
            odds_draw=self._best_odd(raw, ("B365D", "BWD", "IWD", "PSD", "WHD")),
            odds_away_win=self._best_odd(raw, ("B365A", "BWA", "IWA", "PSA", "WHA")),
            odds_over_2_5=self._best_odd(raw, ("B365>2.5", "GB>2.5", "B>2.5")),
            odds_under_2_5=self._best_odd(raw, ("B365<2.5", "GB<2.5", "B<2.5")),
        )
        return row

    def _best_odd(self, raw: dict[str, str], keys: tuple[str, ...]) -> float | None:
        """Return the first valid decimal odd from the ordered key list."""
        for k in keys:
            val = self.safe_float(raw.get(k), minimum=1.01)
            if val is not None:
                return val
        return None
