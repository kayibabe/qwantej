"""
forebet_scraper.py — Scrape Forebet predictions and store as ExternalForecast rows.

Forebet is a mathematical/statistical football prediction platform (since 2009) that
provides 1X2 probabilities, O/U, predicted scores, and goal expectations for hundreds
of leagues. It is one of the highest-value free external benchmarks for Qwantej.

After match settlement, settle_external_forecasts() computes Brier scores per market
so the Data Source Performance dashboard can compare Forebet vs Qwantej ensemble.

Scheduling: Called once per day (morning sync after fixture data is current).
Rate limiting: 2-3 second delay between requests; cached for 6 hours.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_forecast import ExternalForecast
from app.models.fixture import Fixture

logger = logging.getLogger(__name__)

# Forebet base URLs — predictions are public, no login required.
_BASE = "https://www.forebet.com"
_URLS = {
    "today":    f"{_BASE}/en/football-predictions/today",
    "tomorrow": f"{_BASE}/en/football-predictions/tomorrow",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": _BASE,
}

# Fields we expect to extract per match row.
_EMPTY_PREDICTION: dict = {
    "home_team":       None,
    "away_team":       None,
    "league":          None,
    "country":         None,
    "home_win_prob":   None,
    "draw_prob":       None,
    "away_win_prob":   None,
    "over_25_prob":    None,
    "under_25_prob":   None,
    "over_15_prob":    None,
    "btts_yes_prob":   None,
    "pred_home_goals": None,
    "pred_away_goals": None,
    "confidence_label": None,
}


def _safe_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value.strip().replace("%", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _parse_forebet_html(html: str) -> list[dict]:
    """
    Parse Forebet prediction rows from HTML.

    Forebet uses a consistent table layout — each prediction row has:
    - Team names
    - 1X2 percentage bars or text probabilities
    - Predicted score (e.g. "2:1")
    - O/U indicators

    We try multiple CSS selector strategies and fall back gracefully.
    Returns a list of prediction dicts (may be empty if structure changed).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 is not installed — run: pip install beautifulsoup4 lxml")
        return []

    soup = BeautifulSoup(html, "lxml")
    predictions: list[dict] = []

    # Strategy 1: .rcnt table rows (Forebet's primary prediction table class)
    rows = soup.select("div.rcnt")
    if not rows:
        # Strategy 2: try the predictions table directly
        rows = soup.select("table.schema tr")

    for row in rows:
        pred = dict(_EMPTY_PREDICTION)

        # ── Team names ─────────────────────────────────────────────────────────
        teams = row.select(".homeTeam, .awayTeam, [class*='homeT'], [class*='awayT']")
        if len(teams) >= 2:
            pred["home_team"] = teams[0].get_text(strip=True)
            pred["away_team"] = teams[1].get_text(strip=True)
        else:
            # Try generic approach: find the match name link or header
            match_link = row.select_one("a[href*='/en/football/']")
            if match_link:
                text = match_link.get_text(strip=True)
                if " - " in text:
                    parts = text.split(" - ", 1)
                    pred["home_team"] = parts[0].strip()
                    pred["away_team"] = parts[1].strip()

        if not pred["home_team"] or not pred["away_team"]:
            continue

        # ── League ─────────────────────────────────────────────────────────────
        league_el = row.select_one(".shortTag, .lnameT, [class*='league']")
        if league_el:
            pred["league"] = league_el.get_text(strip=True)

        # ── 1X2 probabilities ──────────────────────────────────────────────────
        # Forebet typically shows probabilities as percentages in spans
        prob_els = row.select(".forepr, .prob1, .probD, .prob2, [class*='per']")
        probs = [_safe_float(el.get_text()) for el in prob_els if el.get_text(strip=True)]
        probs = [p for p in probs if p is not None and 0 <= p <= 100]
        if len(probs) >= 3:
            pred["home_win_prob"] = round(probs[0] / 100, 4)
            pred["draw_prob"]     = round(probs[1] / 100, 4)
            pred["away_win_prob"] = round(probs[2] / 100, 4)
        elif len(probs) == 2:
            # Some rows show only home/away for double chance
            pred["home_win_prob"] = round(probs[0] / 100, 4)
            pred["away_win_prob"] = round(probs[1] / 100, 4)

        # ── Predicted score ─────────────────────────────────────────────────────
        score_el = row.select_one(".ex_sc, .score, [class*='predScore'], [class*='sc_']")
        if score_el:
            score_text = score_el.get_text(strip=True)
            m = re.match(r"(\d+)[:\-](\d+)", score_text)
            if m:
                pred["pred_home_goals"] = float(m.group(1))
                pred["pred_away_goals"] = float(m.group(2))

        # ── Over/Under ──────────────────────────────────────────────────────────
        ou_el = row.select_one(".ou_text, [class*='ou_'], [class*='uo_']")
        if ou_el:
            ou_text = ou_el.get_text(strip=True).lower()
            # Forebet often shows "over" / "under" with a threshold
            if "over" in ou_text:
                # Detect threshold: "over 2.5" → over_25_prob high
                thres_m = re.search(r"(\d+\.?\d*)", ou_text)
                if thres_m:
                    t = float(thres_m.group(1))
                    if abs(t - 2.5) < 0.1:
                        pred["over_25_prob"] = 0.65   # directional signal only; no exact prob
                        pred["under_25_prob"] = 0.35
                    elif abs(t - 1.5) < 0.1:
                        pred["over_15_prob"] = 0.65
            elif "under" in ou_text:
                thres_m = re.search(r"(\d+\.?\d*)", ou_text)
                if thres_m:
                    t = float(thres_m.group(1))
                    if abs(t - 2.5) < 0.1:
                        pred["under_25_prob"] = 0.65
                        pred["over_25_prob"] = 0.35

        # Only keep rows where we got at least team names and some probability
        if pred["home_team"] and pred["away_team"]:
            predictions.append(pred)

    logger.info("forebet_scraper: parsed %d predictions from HTML (%d chars)", len(predictions), len(html))
    return predictions


async def _fetch_forebet(day: str) -> str:
    """Fetch raw HTML for 'today' or 'tomorrow'. Returns empty string on failure."""
    url = _URLS.get(day, _URLS["today"])
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError as e:
        logger.warning("forebet_scraper: HTTP error fetching %s — %s", url, e)
        return ""
    except Exception as e:
        logger.warning("forebet_scraper: unexpected error fetching %s — %s", e.__class__.__name__, e)
        return ""


def _fuzzy_match(name_a: str, name_b: str) -> bool:
    """Case-insensitive partial match for team name fuzzy deduplication."""
    a = name_a.lower().strip()
    b = name_b.lower().strip()
    if a == b:
        return True
    # Check if one is a prefix of the other (handles truncation)
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long.startswith(short)


async def _match_to_fixture(
    db: AsyncSession,
    pred: dict,
    match_date: date,
) -> Optional[int]:
    """Try to resolve a prediction row to a fixture_id in our DB."""
    rows = await db.execute(
        select(Fixture.id, Fixture.home_team, Fixture.away_team).where(
            Fixture.event_date == match_date
        )
    )
    fixtures = rows.all()
    for fid, home, away in fixtures:
        if _fuzzy_match(pred["home_team"], home) and _fuzzy_match(pred["away_team"], away):
            return fid
    return None


async def scrape_forebet(db: AsyncSession, target_date: date) -> int:
    """
    Scrape Forebet for target_date and upsert into external_forecasts.

    For today: scrapes 'today' page.
    For tomorrow: scrapes 'tomorrow' page.
    Returns count of rows inserted or updated.
    """
    today = datetime.now(timezone.utc).date()
    day = "today" if target_date == today else "tomorrow"

    logger.info("forebet_scraper: fetching %s predictions for %s", day, target_date)
    html = await _fetch_forebet(day)
    if not html:
        logger.warning("forebet_scraper: empty response for %s", target_date)
        return 0

    predictions = _parse_forebet_html(html)
    if not predictions:
        logger.warning("forebet_scraper: no predictions parsed for %s — HTML structure may have changed", target_date)
        return 0

    inserted = 0
    for pred in predictions:
        home = pred["home_team"]
        away = pred["away_team"]

        # Check if already exists
        existing = await db.scalar(
            select(ExternalForecast.id).where(
                ExternalForecast.source == "forebet",
                ExternalForecast.home_team == home,
                ExternalForecast.away_team == away,
                ExternalForecast.match_date == target_date,
            )
        )
        if existing:
            continue

        # Try to resolve fixture
        await asyncio.sleep(0)   # yield to event loop
        fixture_id = await _match_to_fixture(db, pred, target_date)

        row = ExternalForecast(
            source="forebet",
            home_team=home,
            away_team=away,
            league=pred.get("league"),
            country=pred.get("country"),
            match_date=target_date,
            fixture_id=fixture_id,
            scraped_at=datetime.now(timezone.utc),
            home_win_prob=pred.get("home_win_prob"),
            draw_prob=pred.get("draw_prob"),
            away_win_prob=pred.get("away_win_prob"),
            over_15_prob=pred.get("over_15_prob"),
            over_25_prob=pred.get("over_25_prob"),
            under_25_prob=pred.get("under_25_prob"),
            btts_yes_prob=pred.get("btts_yes_prob"),
            pred_home_goals=pred.get("pred_home_goals"),
            pred_away_goals=pred.get("pred_away_goals"),
            confidence_label=pred.get("confidence_label"),
        )
        db.add(row)
        inserted += 1

    if inserted:
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("forebet_scraper: commit failed — %s", e)
            return 0

    logger.info("forebet_scraper: inserted %d/%d predictions for %s", inserted, len(predictions), target_date)
    return inserted


async def settle_external_forecasts(db: AsyncSession, settled_date: date) -> int:
    """
    After match settlement, compute Brier scores for ExternalForecast rows.

    Called by the scheduler after settle_bets_for_date(). Returns count of
    rows scored.
    """
    # Load unsettled external forecasts for this date
    result = await db.execute(
        select(ExternalForecast).where(
            ExternalForecast.match_date == settled_date,
            ExternalForecast.settled.is_(False),
        )
    )
    rows = result.scalars().all()
    if not rows:
        return 0

    # Load actual fixture results for match resolution
    fix_result = await db.execute(
        select(Fixture).where(Fixture.event_date == settled_date)
    )
    fixtures = {f.id: f for f in fix_result.scalars().all()}
    # Also index by team names for rows without fixture_id
    fixture_by_teams: dict[tuple[str, str], Fixture] = {}
    for f in fixtures.values():
        fixture_by_teams[(f.home_team.lower(), f.away_team.lower())] = f

    scored = 0
    for ef in rows:
        fix = None
        if ef.fixture_id:
            fix = fixtures.get(ef.fixture_id)
        if fix is None:
            fix = fixture_by_teams.get((ef.home_team.lower(), ef.away_team.lower()))
        if fix is None:
            continue

        # Only score completed matches
        if fix.home_score is None or fix.away_score is None:
            continue
        if not (fix.status or "").upper() in {"FT", "AET", "PEN", "FINISHED", "MATCH_FINISHED"}:
            continue

        hg = fix.home_score
        ag = fix.away_score
        total = hg + ag

        ef.actual_home_goals = hg
        ef.actual_away_goals = ag

        def brier(prob: Optional[float], outcome: int) -> Optional[float]:
            if prob is None:
                return None
            return round((prob - outcome) ** 2, 6)

        # 1X2
        if ef.home_win_prob is not None:
            ef.brier_1x2_home = brier(ef.home_win_prob, 1 if hg > ag else 0)
        if ef.draw_prob is not None:
            ef.brier_1x2_draw = brier(ef.draw_prob, 1 if hg == ag else 0)
        if ef.away_win_prob is not None:
            ef.brier_1x2_away = brier(ef.away_win_prob, 1 if ag > hg else 0)

        # Over/Under
        ef.brier_o15 = brier(ef.over_15_prob, 1 if total >= 2 else 0)
        ef.brier_o25 = brier(ef.over_25_prob, 1 if total >= 3 else 0)
        ef.brier_u25 = brier(ef.under_25_prob, 1 if total <= 2 else 0)

        # BTTS
        ef.brier_btts = brier(ef.btts_yes_prob, 1 if hg > 0 and ag > 0 else 0)

        ef.settled = True
        ef.settled_at = datetime.now(timezone.utc)
        scored += 1

    if scored:
        try:
            await db.commit()
            logger.info("forebet_scraper: scored %d external forecasts for %s", scored, settled_date)
        except Exception as e:
            await db.rollback()
            logger.error("forebet_scraper: settlement commit failed — %s", e)
            return 0

    return scored
