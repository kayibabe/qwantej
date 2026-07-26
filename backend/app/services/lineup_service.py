"""
lineup_service.py — Hybrid B Phase 6 Rule 3: Team News Alert.

Spec: Do Not Bet if the away team is confirmed resting/missing 5+ key players
(dramatically lowering their actual xG).

Data source: API-Football /injuries endpoint — returns injured and suspended
players per fixture. Populated once official squad news is confirmed (typically
1–24h before kickoff depending on competition).

Design rules (mirrors weather_service.py)
-----------------------------------------
- FAIL-OPEN: any error (no API key, network failure, fixture not in API)
  returns False — the bet proceeds on model merit.
- Cached per fixture_id within the process lifetime so a single sync run
  calls the API at most once per fixture.
- Checks the away team only; home absences don't affect X2 or Away O0.5.
- Threshold: HYBRID_B_LINEUP_ABSENT_THRESHOLD (default 5) injured+suspended
  away players → alert = True (match flagged, signal skipped).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import (
    HYBRID_B_LINEUP_CHECK_ENABLED,
    HYBRID_B_LINEUP_ABSENT_THRESHOLD,
)
from app.core.config import get_settings

log = logging.getLogger(__name__)

_BASE_URL = "https://v3.football.api-sports.io"
_TIMEOUT = 8.0

# Process-lifetime cache: fixture_id → absent away player count
_injury_cache: dict[int, int] = {}


def _api_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "x-rapidapi-key": settings.api_football_key,
        "x-rapidapi-host": "v3.football.api-sports.io",
    }


async def _fetch_away_absent_count(fixture_id: int, away_team: str) -> Optional[int]:
    """
    Query /injuries for the fixture and return the number of injured or
    suspended players on the away team. Returns None on any failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE_URL}/injuries",
                params={"fixture": fixture_id},
                headers=_api_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.debug("Lineup /injuries fetch failed for fixture %d: %s", fixture_id, exc)
        return None

    entries = data.get("response") or []
    if not entries:
        # No injury data yet for this fixture — lineup not confirmed
        return None

    away_team_lower = away_team.lower().strip()
    count = 0
    for entry in entries:
        team_name = (entry.get("team") or {}).get("name") or ""
        if team_name.lower().strip() != away_team_lower:
            continue
        reason = (entry.get("reason") or entry.get("type") or "").lower()
        if "injur" in reason or "suspend" in reason or "miss" in reason:
            count += 1

    return count


async def get_team_news_alert(fixture_id: int, away_team: str) -> bool:
    """
    Return True when the away team has >= HYBRID_B_LINEUP_ABSENT_THRESHOLD
    injured or suspended players confirmed for this fixture.

    Fail-open: returns False when the check is disabled, the API key is not
    set, or any lookup fails — the bet proceeds on model merit.
    """
    if not HYBRID_B_LINEUP_CHECK_ENABLED:
        return False

    settings = get_settings()
    if not settings.api_football_key:
        return False

    if fixture_id in _injury_cache:
        count = _injury_cache[fixture_id]
    else:
        count_or_none = await _fetch_away_absent_count(fixture_id, away_team)
        if count_or_none is None:
            # No data yet — not a blocking condition; fail-open
            return False
        count = count_or_none
        _injury_cache[fixture_id] = count

    if count >= HYBRID_B_LINEUP_ABSENT_THRESHOLD:
        log.info(
            "Team news alert for fixture %d (away: %s): %d absent players >= threshold %d",
            fixture_id, away_team, count, HYBRID_B_LINEUP_ABSENT_THRESHOLD,
        )
        return True

    return False
