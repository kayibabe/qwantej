"""Pure parsing and normalization for API-Football v3 payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ApiFootballPayloadError(ValueError):
    """A provider record is incomplete or incompatible with our contract."""


@dataclass(frozen=True)
class ApiFootballFixture:
    external_fixture_id: str
    external_league_id: str
    external_home_team_id: str
    external_away_team_id: str
    league_name: str
    league_country: str | None
    season: int
    home_team_name: str
    away_team_name: str
    kickoff_utc: datetime
    status: str
    venue: str | None
    home_goals: int | None
    away_goals: int | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ApiFootballOddsQuote:
    external_fixture_id: str
    bookmaker: str
    market: str
    selection: str
    line: Decimal | None
    decimal_odds: Decimal
    captured_at: datetime


_TOTAL_SELECTION = re.compile(r"^(Over|Under)\s+(-?\d+(?:\.\d+)?)$", re.IGNORECASE)


def parse_fixture(item: dict[str, Any]) -> ApiFootballFixture:
    fixture = _object(item, "fixture")
    league = _object(item, "league")
    teams = _object(item, "teams")
    home = _object(teams, "home")
    away = _object(teams, "away")
    goals = _object(item, "goals")
    status_obj = _object(fixture, "status")
    venue_obj = fixture.get("venue") or {}
    if not isinstance(venue_obj, dict):
        raise ApiFootballPayloadError("fixture.venue must be an object")

    timestamp = _integer(fixture, "timestamp")
    kickoff = datetime.fromtimestamp(timestamp, tz=UTC)
    home_id = _identifier(home, "id")
    away_id = _identifier(away, "id")
    if home_id == away_id:
        raise ApiFootballPayloadError("fixture home and away team ids must differ")

    return ApiFootballFixture(
        external_fixture_id=_identifier(fixture, "id"),
        external_league_id=_identifier(league, "id"),
        external_home_team_id=home_id,
        external_away_team_id=away_id,
        league_name=_text(league, "name"),
        league_country=_optional_text(league.get("country")),
        season=_integer(league, "season"),
        home_team_name=_text(home, "name"),
        away_team_name=_text(away, "name"),
        kickoff_utc=kickoff,
        status=normalize_fixture_status(_text(status_obj, "short")),
        venue=_optional_text(venue_obj.get("name")),
        home_goals=_optional_integer(goals.get("home"), "goals.home"),
        away_goals=_optional_integer(goals.get("away"), "goals.away"),
        raw=item,
    )


def parse_odds(item: dict[str, Any]) -> tuple[ApiFootballOddsQuote, ...]:
    fixture_obj = _object(item, "fixture")
    fixture_id = _identifier(fixture_obj, "id")
    captured_at = _parse_datetime(_text(item, "update"), "update")
    bookmakers = item.get("bookmakers")
    if not isinstance(bookmakers, list):
        raise ApiFootballPayloadError("bookmakers must be a list")

    quotes: list[ApiFootballOddsQuote] = []
    for bookmaker_obj in bookmakers:
        if not isinstance(bookmaker_obj, dict):
            raise ApiFootballPayloadError("bookmaker must be an object")
        bookmaker = _text(bookmaker_obj, "name")
        bets = bookmaker_obj.get("bets")
        if not isinstance(bets, list):
            raise ApiFootballPayloadError("bookmaker.bets must be a list")
        for bet_obj in bets:
            if not isinstance(bet_obj, dict):
                raise ApiFootballPayloadError("bet must be an object")
            market = _text(bet_obj, "name")
            values = bet_obj.get("values")
            if not isinstance(values, list):
                raise ApiFootballPayloadError("bet.values must be a list")
            for value_obj in values:
                if not isinstance(value_obj, dict):
                    raise ApiFootballPayloadError("bet value must be an object")
                raw_value = value_obj.get("value")
                if not isinstance(raw_value, str) or not raw_value.strip():
                    # Live API occasionally returns blank/null selections (e.g.
                    # suspended markets); skip rather than abort the whole payload.
                    continue
                raw_selection = raw_value.strip()
                selection, line = normalize_selection(raw_selection)
                odds = _decimal(value_obj.get("odd"), "odd")
                if odds <= 1:
                    # Odds ≤ 1.0 are invalid or suspended-market placeholders; skip.
                    continue
                quotes.append(
                    ApiFootballOddsQuote(
                        external_fixture_id=fixture_id,
                        bookmaker=bookmaker,
                        market=market,
                        selection=selection,
                        line=line,
                        decimal_odds=odds,
                        captured_at=captured_at,
                    )
                )
    return tuple(quotes)


def normalize_selection(value: str) -> tuple[str, Decimal | None]:
    match = _TOTAL_SELECTION.fullmatch(value.strip())
    if match is None:
        return value.strip(), None
    return match.group(1).title(), Decimal(match.group(2))


def normalize_fixture_status(value: str) -> str:
    code = value.upper()
    if code in {"NS", "TBD"}:
        return "scheduled"
    if code in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}:
        return "live"
    if code in {"FT", "AET", "PEN", "AWD", "WO"}:
        return "finished"
    if code == "PST":
        return "postponed"
    if code in {"CANC", "ABD"}:
        return "cancelled"
    raise ApiFootballPayloadError(f"unsupported fixture status {value!r}")


def _object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ApiFootballPayloadError(f"{key} must be an object")
    return value


def _identifier(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ApiFootballPayloadError(f"{key} must be an identifier")
    text = str(value).strip()
    if not text:
        raise ApiFootballPayloadError(f"{key} must not be blank")
    return text


def _text(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiFootballPayloadError(f"{key} must be non-blank text")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiFootballPayloadError("optional text field must be text or null")
    return value.strip() or None


def _integer(parent: dict[str, Any], key: str) -> int:
    value = parent.get(key)
    if value is None or isinstance(value, bool):
        raise ApiFootballPayloadError(f"{key} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiFootballPayloadError(f"{key} must be an integer") from exc


def _optional_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ApiFootballPayloadError(f"{field} must be an integer or null")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ApiFootballPayloadError(f"{field} must be an integer or null") from exc


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ApiFootballPayloadError(f"{field} must be decimal") from exc
    if not parsed.is_finite():
        raise ApiFootballPayloadError(f"{field} must be finite")
    return parsed


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiFootballPayloadError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApiFootballPayloadError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)
