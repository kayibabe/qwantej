"""
weather_service.py — Hybrid B Phase 6 Rule 5 weather override.

Spec: skip the match entirely when weather reports indicate heavy rain
(≥ 10 mm/hr) or high winds (≥ 50 km/h) at kickoff. Adverse weather reduces
goal-scoring probability and increases variance — bad for both X2 value
and Away O0.5.

Data source: Open-Meteo (https://open-meteo.com) — free, keyless, 16-day
hourly forecast. Two endpoints:
  1. Geocoding: city name → lat/lon (cached per city for the process lifetime)
  2. Forecast:  hourly precipitation + wind speed at the venue for match day
     (cached per location+date so same-city fixtures share one call)

Design rules
------------
- FAIL-OPEN: any error (no venue city, geocode miss, network failure,
  timeout) returns False — the bet proceeds on model merit. Weather is a
  defensive overlay, never a reason to crash or block signal computation.
- We check the kickoff hour AND the following two hours so conditions
  during the match (not just at whistle) are covered.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import (
    HYBRID_B_WEATHER_RAIN_MM_PER_HR,
    HYBRID_B_WEATHER_WIND_KMH,
    HYBRID_B_WEATHER_CHECK_ENABLED,
)

log = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 6.0

# Process-lifetime caches. Geocode results never change; forecasts are cached
# per (lat, lon, date) — one sync run computes many fixtures in the same city.
_geocode_cache: dict[str, Optional[tuple[float, float]]] = {}
_forecast_cache: dict[tuple[float, float, str], Optional[dict]] = {}


async def _geocode_city(city: str, country: Optional[str] = None) -> Optional[tuple[float, float]]:
    """Resolve a city name to (lat, lon). Cached; None on failure."""
    key = f"{city.lower().strip()}|{(country or '').lower().strip()}"
    if key in _geocode_cache:
        return _geocode_cache[key]

    result: Optional[tuple[float, float]] = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_GEOCODE_URL, params={"name": city, "count": 5})
            resp.raise_for_status()
            matches = resp.json().get("results") or []
            if matches:
                # Prefer a match in the fixture's country when we have one;
                # otherwise take the top-ranked result.
                chosen = matches[0]
                if country:
                    country_l = country.lower().strip()
                    for m in matches:
                        if (m.get("country") or "").lower().strip() == country_l:
                            chosen = m
                            break
                result = (float(chosen["latitude"]), float(chosen["longitude"]))
    except Exception as e:  # noqa: BLE001 — fail-open by design
        log.debug("Weather geocode failed for %r: %s", city, e)

    _geocode_cache[key] = result
    return result


async def _fetch_hourly(lat: float, lon: float, date_str: str) -> Optional[dict]:
    """Fetch hourly precipitation + wind for one date at a location. Cached."""
    key = (round(lat, 2), round(lon, 2), date_str)
    if key in _forecast_cache:
        return _forecast_cache[key]

    result: Optional[dict] = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_FORECAST_URL, params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation,wind_speed_10m",
                "start_date": date_str,
                "end_date": date_str,
                "timezone": "UTC",
                "wind_speed_unit": "kmh",
            })
            resp.raise_for_status()
            result = resp.json().get("hourly") or None
    except Exception as e:  # noqa: BLE001 — fail-open by design
        log.debug("Weather forecast failed for (%s, %s) %s: %s", lat, lon, date_str, e)

    _forecast_cache[key] = result
    return result


async def get_weather_alert(
    venue_city: Optional[str],
    country: Optional[str],
    kickoff_at: Optional[datetime],
) -> bool:
    """
    True when the forecast at the venue shows heavy rain (≥ 10 mm/hr) or high
    winds (≥ 50 km/h) in the kickoff hour or the two hours after it.

    Fail-open: returns False when the check is disabled, venue/kickoff data is
    missing, or any lookup fails.
    """
    if not HYBRID_B_WEATHER_CHECK_ENABLED:
        return False
    if not venue_city or not kickoff_at:
        return False

    coords = await _geocode_city(venue_city, country)
    if coords is None:
        return False

    # Normalise kickoff to UTC (DB datetimes are naive UTC).
    ko = kickoff_at if kickoff_at.tzinfo else kickoff_at.replace(tzinfo=timezone.utc)
    ko = ko.astimezone(timezone.utc)

    hourly = await _fetch_hourly(coords[0], coords[1], ko.strftime("%Y-%m-%d"))
    if not hourly:
        return False

    times = hourly.get("time") or []
    rain = hourly.get("precipitation") or []
    wind = hourly.get("wind_speed_10m") or []

    # Kickoff hour + 2 following hours (a match runs ~2h including half-time).
    target_hours = {(ko.hour + off) % 24 for off in (0, 1, 2)}
    for i, t in enumerate(times):
        try:
            hour = int(t[11:13])
        except (ValueError, IndexError):
            continue
        if hour not in target_hours:
            continue
        r = rain[i] if i < len(rain) and rain[i] is not None else 0.0
        w = wind[i] if i < len(wind) and wind[i] is not None else 0.0
        if r >= HYBRID_B_WEATHER_RAIN_MM_PER_HR or w >= HYBRID_B_WEATHER_WIND_KMH:
            log.info(
                "Weather alert for %s at %s UTC: rain=%.1fmm/h wind=%.1fkm/h",
                venue_city, t, r, w,
            )
            return True
    return False
