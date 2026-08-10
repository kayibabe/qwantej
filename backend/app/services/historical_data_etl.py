"""
historical_data_etl.py — Download and ingest free historical football datasets.

Primary source: football-data.co.uk
  - CSV format, 1993–present, 20+ leagues
  - Includes match stats (shots, corners, cards) and pre-match odds
  - URL: https://www.football-data.co.uk/mmz4281/{season}/{league}.csv
    e.g. https://www.football-data.co.uk/mmz4281/2324/E0.csv

Running the ETL for the default 10 seasons × 18 leagues ≈ 180 files ≈ 200-300K rows.
All upserts are idempotent — re-running won't create duplicates.

Usage:
    asyncio.run(run_full_etl(db, seasons=10, leagues=DEFAULT_LEAGUES))
or via the admin endpoint:
    POST /api/admin/etl/historical?seasons=10
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import aiohttp
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.historical_fixture import HistoricalFixture

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# League catalogue — (code, country, league_name)
# ---------------------------------------------------------------------------
DEFAULT_LEAGUES: list[tuple[str, str, str]] = [
    ("E0",  "England",     "Premier League"),
    ("E1",  "England",     "Championship"),
    ("E2",  "England",     "League One"),
    ("E3",  "England",     "League Two"),
    ("SP1", "Spain",       "La Liga"),
    ("SP2", "Spain",       "La Liga 2"),
    ("D1",  "Germany",     "Bundesliga"),
    ("D2",  "Germany",     "2. Bundesliga"),
    ("I1",  "Italy",       "Serie A"),
    ("I2",  "Italy",       "Serie B"),
    ("F1",  "France",      "Ligue 1"),
    ("F2",  "France",      "Ligue 2"),
    ("N1",  "Netherlands", "Eredivisie"),
    ("B1",  "Belgium",     "First Division A"),
    ("P1",  "Portugal",    "Primeira Liga"),
    ("SC0", "Scotland",    "Premiership"),
    ("G1",  "Greece",      "Super League"),
    ("T1",  "Turkey",      "Süper Lig"),
]

_BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Column name aliases — football-data.co.uk has changed column names over the years.
# Each tuple is (canonical_name, [possible_column_names_in_CSV])
_COL_MAP: list[tuple[str, list[str]]] = [
    ("home_team",          ["HomeTeam", "Home"]),
    ("away_team",          ["AwayTeam", "Away"]),
    ("home_goals",         ["FTHG", "HG"]),
    ("away_goals",         ["FTAG", "AG"]),
    ("result",             ["FTR", "Res"]),
    ("home_goals_ht",      ["HTHG"]),
    ("away_goals_ht",      ["HTAG"]),
    ("home_shots",         ["HS"]),
    ("away_shots",         ["AS"]),
    ("home_shots_on_target", ["HST"]),
    ("away_shots_on_target", ["AST"]),
    ("home_corners",       ["HC"]),
    ("away_corners",       ["AC"]),
    ("home_yellow_cards",  ["HY"]),
    ("away_yellow_cards",  ["AY"]),
    ("home_red_cards",     ["HR"]),
    ("away_red_cards",     ["AR"]),
    ("home_fouls",         ["HF"]),
    ("away_fouls",         ["AF"]),
    ("home_possession",    ["HP"]),
    ("odds_home_win",      ["B365H", "BbMxH", "BWH", "MaxH"]),
    ("odds_draw",          ["B365D", "BbMxD", "BWD", "MaxD"]),
    ("odds_away_win",      ["B365A", "BbMxA", "BWA", "MaxA"]),
    ("odds_over_2_5",      ["B365>2.5", "BbMx>2.5", "Max>2.5"]),
    ("odds_under_2_5",     ["B365<2.5", "BbMx<2.5", "Max<2.5"]),
    ("odds_over_1_5",      ["B365>1.5", "BbMx>1.5", "Max>1.5"]),
    ("odds_under_1_5",     ["B365<1.5", "BbMx<1.5", "Max<1.5"]),
    ("odds_over_3_5",      ["B365>3.5", "Max>3.5"]),
    ("odds_under_3_5",     ["B365<3.5", "Max<3.5"]),
    ("odds_btts_yes",      ["B365BTSCY", "BbMxBTTSY", "MaxBTTSY"]),
    ("odds_btts_no",       ["B365BTSCN", "BbMxBTTSN", "MaxBTTSN"]),
]


def _season_code(year: int) -> str:
    """
    Convert a season start year to the football-data.co.uk URL code.
    year=2023 → season 2023/24 → '2324'
    """
    y1 = str(year)[-2:]
    y2 = str(year + 1)[-2:]
    return f"{y1}{y2}"


def _parse_date(raw: str) -> Optional[date]:
    """Parse DD/MM/YY or DD/MM/YYYY dates from football-data.co.uk."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _first_col(row: pd.Series, candidates: list[str]) -> Optional[object]:
    """Return the value of the first column in candidates that exists and is non-null."""
    for col in candidates:
        if col in row.index:
            val = row[col]
            if pd.notna(val):
                return val
    return None


def _safe_int(val) -> Optional[int]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        f = float(val)
        return round(f, 4) if f > 0 else None
    except (ValueError, TypeError):
        return None


def _infer_season(d: date) -> int:
    """July–June season boundary: July 2023 → season 2023."""
    return d.year if d.month >= 7 else d.year - 1


def _parse_csv_to_rows(
    csv_bytes: bytes,
    country: str,
    league: str,
    season_year: int,
) -> list[dict]:
    """
    Parse raw CSV bytes from football-data.co.uk into a list of row dicts
    ready to be upserted into HistoricalFixture.
    """
    try:
        df = pd.read_csv(
            io.BytesIO(csv_bytes),
            encoding="latin-1",
            on_bad_lines="skip",
            dtype=str,
        )
    except Exception as e:
        logger.warning("ETL: CSV parse failed for %s/%s — %s", country, league, e)
        return []

    # Drop rows where the date column is missing (empty footer rows are common).
    date_col = "Date"
    if date_col not in df.columns:
        return []
    df = df.dropna(subset=[date_col])
    df = df[df[date_col].str.strip().astype(bool)]

    rows: list[dict] = []
    for _, raw in df.iterrows():
        match_date = _parse_date(str(raw.get("Date", "")))
        if match_date is None:
            continue

        home_team = str(_first_col(raw, ["HomeTeam", "Home"]) or "").strip()
        away_team = str(_first_col(raw, ["AwayTeam", "Away"]) or "").strip()
        if not home_team or not away_team:
            continue

        row: dict = {
            "source": "football_data_co_uk",
            "match_date": match_date,
            "season": _infer_season(match_date),
            "country": country,
            "league": league,
            "home_team": home_team,
            "away_team": away_team,
        }

        # Map all remaining columns
        for canonical, candidates in _COL_MAP[2:]:  # skip home/away team already done
            val = _first_col(raw, candidates)
            if val is None:
                continue
            # Classify by expected type
            if canonical in ("home_goals", "away_goals", "home_goals_ht", "away_goals_ht",
                             "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target",
                             "home_corners", "away_corners", "home_yellow_cards", "away_yellow_cards",
                             "home_red_cards", "away_red_cards", "home_fouls", "away_fouls"):
                row[canonical] = _safe_int(val)
            elif canonical == "result":
                r = str(val).strip().upper()
                row[canonical] = r if r in ("H", "D", "A") else None
            elif canonical == "home_possession":
                row[canonical] = _safe_float(val)
            else:  # odds
                row[canonical] = _safe_float(val)

        rows.append(row)

    return rows


async def _fetch_csv(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Download a CSV file; returns bytes or None on error."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return await resp.read()
    except asyncio.TimeoutError:
        logger.warning("ETL: timeout fetching %s", url)
        return None
    except Exception as e:
        logger.warning("ETL: error fetching %s — %s", url, e)
        return None


async def _upsert_batch(db: AsyncSession, rows: list[dict]) -> int:
    """Upsert a batch of rows into historical_fixtures. Returns inserted count."""
    if not rows:
        return 0

    for row in rows:
        # Compute market outcomes from goals before inserting
        hg = row.get("home_goals")
        ag = row.get("away_goals")
        if hg is not None and ag is not None:
            total = hg + ag
            if not row.get("result"):
                row["result"] = "H" if hg > ag else ("D" if hg == ag else "A")
            row["btts"] = hg > 0 and ag > 0
            row["over_1_5"] = total >= 2
            row["over_2_5"] = total >= 3
            row["over_3_5"] = total >= 4
            row["under_2_5"] = total <= 2
            row["under_3_5"] = total <= 3

        # Compute data quality score inline
        score = 0.0
        if hg is not None and ag is not None:
            score += 0.25
        if row.get("home_goals_ht") is not None:
            score += 0.05
        if any(row.get(f) is not None for f in ("home_shots", "away_shots", "home_corners")):
            score += 0.15
        if row.get("odds_home_win") and row.get("odds_draw") and row.get("odds_away_win"):
            if row.get("odds_over_2_5") and row.get("odds_under_2_5"):
                score += 0.25
            else:
                score += 0.05
        row["data_quality"] = round(min(score, 1.0), 3)

    try:
        stmt = (
            pg_insert(HistoricalFixture)
            .values(rows)
            .on_conflict_do_nothing(
                constraint="uq_historical_fixtures_match"
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount or 0
    except Exception as e:
        await db.rollback()
        logger.error("ETL: upsert batch failed — %s", e)
        return 0


async def run_full_etl(
    db: AsyncSession,
    seasons: int = 10,
    leagues: list[tuple[str, str, str]] | None = None,
    concurrency: int = 4,
) -> dict[str, int]:
    """
    Download and ingest football-data.co.uk CSVs for the given number of seasons.

    Args:
        db: async DB session
        seasons: how many past seasons to fetch (default 10 ≈ ~200K rows)
        leagues: list of (code, country, name) tuples; defaults to DEFAULT_LEAGUES
        concurrency: max simultaneous HTTP requests

    Returns:
        {"files_fetched": N, "rows_inserted": N, "rows_skipped": N}
    """
    if leagues is None:
        leagues = DEFAULT_LEAGUES

    current_year = datetime.now(timezone.utc).year
    current_month = datetime.now(timezone.utc).month
    # Current season start year
    current_season_start = current_year if current_month >= 7 else current_year - 1
    season_years = list(range(current_season_start, current_season_start - seasons, -1))

    total_files = 0
    total_inserted = 0
    total_skipped = 0

    sem = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.football-data.co.uk/",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        for season_year in season_years:
            season_code = _season_code(season_year)

            async def fetch_and_ingest(code: str, country: str, league_name: str, sc: str = season_code, sy: int = season_year) -> tuple[int, int]:
                url = f"{_BASE_URL}/{sc}/{code}.csv"
                async with sem:
                    csv_bytes = await _fetch_csv(session, url)
                    if csv_bytes is None:
                        return 0, 0
                    await asyncio.sleep(0.3)   # polite rate limit

                rows = _parse_csv_to_rows(csv_bytes, country, league_name, sy)
                if not rows:
                    return 0, 0

                # Insert in batches of 500 to avoid huge single statements
                inserted = 0
                for i in range(0, len(rows), 500):
                    batch = rows[i:i + 500]
                    inserted += await _upsert_batch(db, batch)
                skipped = len(rows) - inserted
                logger.info("ETL: %s/%s/%s — %d rows (%d new, %d dup)", sc, code, country, len(rows), inserted, skipped)
                return inserted, skipped

            tasks = [
                fetch_and_ingest(code, country, league_name)
                for code, country, league_name in leagues
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    logger.error("ETL: league fetch failed — %s", r)
                    continue
                ins, skip = r
                total_inserted += ins
                total_skipped += skip
                total_files += 1

            logger.info(
                "ETL season %s/%s: done (%d files processed so far, %d rows inserted total)",
                season_year, season_year + 1, total_files, total_inserted,
            )

    logger.info(
        "ETL complete: %d files, %d inserted, %d skipped (existing)",
        total_files, total_inserted, total_skipped,
    )
    return {
        "files_fetched": total_files,
        "rows_inserted": total_inserted,
        "rows_skipped": total_skipped,
    }


async def run_current_season_etl(db: AsyncSession) -> dict[str, int]:
    """
    Fetch only the current season — called weekly by the scheduler to keep
    the warehouse current as the season progresses.
    """
    return await run_full_etl(db, seasons=1)
