"""Transactional API-Football ingestion into canonical point-in-time storage."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    AuditActor,
    AuditEvent,
    AuditEventType,
    Competition,
    EntityType,
    Fixture,
    FixtureStatus,
    OddsQuote,
    Provider,
    Season,
    SourceMapping,
    StatsSnapshot,
    StatsSubjectType,
    Team,
)
from backend.services.api_football_client import ApiFootballClient
from qwantej.fixtures import ApiFootballFixture, ApiFootballOddsQuote, parse_fixture, parse_odds

PROVIDER_NAME = "API-Football"
SOURCE_NAME = "api-football"
FIXTURE_SOURCE = "api-football:fixtures"
STATISTICS_SOURCE = "api-football:fixture-statistics"
PROVIDER_BASE_URL = "https://v3.football.api-sports.io"

_MARKET_MAP = {
    "Match Winner": "1X2",
    "Goals Over/Under": "TOTALS",
    "Both Teams Score": "BTTS",
    "Double Chance": "DOUBLE_CHANCE",
}


class ApiFootballIngestionError(ValueError):
    """An API-Football record cannot be safely reconciled to canonical data."""


@dataclass(frozen=True)
class IngestionSummary:
    fixtures_created: int = 0
    fixtures_updated: int = 0
    fixture_snapshots_created: int = 0
    statistics_snapshots_created: int = 0
    odds_quotes_created: int = 0
    odds_quotes_deduplicated: int = 0
    odds_quotes_unsupported: int = 0


def ingest_walk_forward_window(
    session: Session,
    client: ApiFootballClient,
    *,
    league_id: int,
    season: int,
    start_date: date,
    end_date: date,
    captured_at: datetime,
    include_fixture_statistics: bool = False,
    include_odds: bool = True,
) -> IngestionSummary:
    """Fetch and stage one bounded league-season window without committing it."""

    if start_date > end_date:
        raise ApiFootballIngestionError("start_date cannot follow end_date")
    _require_aware(captured_at, "captured_at")
    fixture_payloads = client.fixtures(
        league=league_id,
        season=season,
        **{"from": start_date.isoformat(), "to": end_date.isoformat(), "timezone": "UTC"},
    )
    window_fixture_ids = {
        parse_fixture(payload).external_fixture_id for payload in fixture_payloads
    }
    statistics_payloads: list[tuple[str, tuple[dict[str, Any], ...]]] = []
    if include_fixture_statistics:
        for payload in fixture_payloads:
            external_fixture_id = str(payload.get("fixture", {}).get("id", ""))
            if not external_fixture_id:
                raise ApiFootballIngestionError("fixture id missing before statistics fetch")
            statistics_payloads.append(
                (external_fixture_id, client.fixture_statistics(int(external_fixture_id)))
            )

    # The provider retains only a short pre-match odds history. This call captures
    # what is currently available; repeated scheduled runs build Qwantej's archive.
    # Skip the odds fetch entirely when the window contains no fixtures — this is
    # the main quota saver for offseason leagues in all-leagues mode.
    odds_payloads: tuple[dict[str, Any], ...] = ()
    if include_odds and window_fixture_ids:
        odds_payloads = tuple(
            payload
            for payload in client.odds(league=league_id, season=season)
            if _payload_fixture_id(payload) in window_fixture_ids
        )
    with session.begin_nested():
        fixture_summary = _ingest_fixtures(
            session, fixture_payloads, captured_at=captured_at
        )
        statistics_count = sum(
            _ingest_fixture_statistics(
                session,
                external_fixture_id=external_fixture_id,
                statistics=statistics,
                captured_at=captured_at,
            )
            for external_fixture_id, statistics in statistics_payloads
        )
        odds_summary = _ingest_odds(session, odds_payloads)
        return IngestionSummary(
            fixtures_created=fixture_summary.fixtures_created,
            fixtures_updated=fixture_summary.fixtures_updated,
            fixture_snapshots_created=fixture_summary.fixture_snapshots_created,
            statistics_snapshots_created=statistics_count,
            odds_quotes_created=odds_summary.odds_quotes_created,
            odds_quotes_deduplicated=odds_summary.odds_quotes_deduplicated,
            odds_quotes_unsupported=odds_summary.odds_quotes_unsupported,
        )


def ingest_fixtures(
    session: Session,
    payloads: Iterable[dict[str, Any]],
    *,
    captured_at: datetime,
) -> IngestionSummary:
    with session.begin_nested():
        return _ingest_fixtures(session, payloads, captured_at=captured_at)


def _ingest_fixtures(
    session: Session,
    payloads: Iterable[dict[str, Any]],
    *,
    captured_at: datetime,
) -> IngestionSummary:
    _require_aware(captured_at, "captured_at")
    provider = _provider(session)
    created = updated = snapshots = 0
    for payload in payloads:
        parsed = parse_fixture(payload)
        competition = _competition(session, provider, parsed)
        season = _season(session, provider, competition, parsed)
        home = _team(
            session,
            provider,
            parsed.external_home_team_id,
            parsed.home_team_name,
        )
        away = _team(
            session,
            provider,
            parsed.external_away_team_id,
            parsed.away_team_name,
        )
        fixture = _mapped_entity(
            session, provider.id, EntityType.FIXTURE, parsed.external_fixture_id, Fixture
        )
        if fixture is None:
            fixture = Fixture(
                competition=competition,
                season=season,
                home_team=home,
                away_team=away,
                kickoff_utc=parsed.kickoff_utc,
                status=FixtureStatus(parsed.status),
                venue=_bounded(parsed.venue, 150, "fixture venue"),
                home_goals=parsed.home_goals if parsed.status == "finished" else None,
                away_goals=parsed.away_goals if parsed.status == "finished" else None,
            )
            session.add(fixture)
            session.flush()
            _mapping(
                session,
                provider,
                EntityType.FIXTURE,
                parsed.external_fixture_id,
                fixture.id,
            )
            created += 1
        else:
            _assert_fixture_identity(fixture, competition, season, home, away, parsed)
            if _update_fixture(session, fixture, parsed, captured_at):
                updated += 1

        if _append_fixture_snapshot(session, fixture, parsed.raw, captured_at):
            snapshots += 1
    session.flush()
    return IngestionSummary(
        fixtures_created=created,
        fixtures_updated=updated,
        fixture_snapshots_created=snapshots,
    )


def ingest_fixture_statistics(
    session: Session,
    *,
    external_fixture_id: str,
    statistics: Sequence[dict[str, Any]],
    captured_at: datetime,
) -> bool:
    with session.begin_nested():
        return _ingest_fixture_statistics(
            session,
            external_fixture_id=external_fixture_id,
            statistics=statistics,
            captured_at=captured_at,
        )


def _ingest_fixture_statistics(
    session: Session,
    *,
    external_fixture_id: str,
    statistics: Sequence[dict[str, Any]],
    captured_at: datetime,
) -> bool:
    _require_aware(captured_at, "captured_at")
    provider = _provider(session)
    fixture = _mapped_entity(
        session, provider.id, EntityType.FIXTURE, external_fixture_id, Fixture
    )
    if fixture is None:
        raise ApiFootballIngestionError(
            f"fixture {external_fixture_id} must be ingested before its statistics"
        )
    payload = {"endpoint": "fixtures/statistics", "response": list(statistics)}
    return _append_stats_snapshot(
        session, fixture.id, payload, captured_at, source=STATISTICS_SOURCE
    )


def ingest_odds(
    session: Session, payloads: Iterable[dict[str, Any]]
) -> IngestionSummary:
    with session.begin_nested():
        return _ingest_odds(session, payloads)


def _ingest_odds(
    session: Session, payloads: Iterable[dict[str, Any]]
) -> IngestionSummary:
    provider = _provider(session)
    created = deduplicated = unsupported = 0
    unsupported_markets: set[str] = set()
    provider_timestamps: list[datetime] = []
    for payload in payloads:
        for parsed in parse_odds(payload):
            provider_timestamps.append(parsed.captured_at)
            canonical = _canonical_market_selection(parsed)
            if canonical is None:
                unsupported += 1
                unsupported_markets.add(parsed.market)
                continue
            market, selection = canonical
            fixture = _mapped_entity(
                session,
                provider.id,
                EntityType.FIXTURE,
                parsed.external_fixture_id,
                Fixture,
            )
            if fixture is None:
                raise ApiFootballIngestionError(
                    f"fixture {parsed.external_fixture_id} must be ingested before its odds"
                )
            if _find_odds_quote(
                session, fixture.id, parsed, market=market, selection=selection
            ) is not None:
                deduplicated += 1
                continue
            session.add(
                OddsQuote(
                    fixture_id=fixture.id,
                    bookmaker=_bounded(parsed.bookmaker, 80, "bookmaker"),
                    market=market,
                    selection=selection,
                    line=parsed.line,
                    decimal_odds=parsed.decimal_odds,
                    captured_at=parsed.captured_at,
                    source=SOURCE_NAME,
                )
            )
            created += 1
    if unsupported:
        session.add(
            AuditEvent(
                event_type=AuditEventType.GOVERNANCE,
                actor=AuditActor.SYSTEM,
                actor_ref="api-football-ingestion",
                action="skip_unsupported_odds_market",
                summary="Skipped API-Football odds without an approved canonical market",
                entity_type="odds_quotes",
                payload={
                    "unsupported_quote_count": unsupported,
                    "provider_markets": sorted(unsupported_markets),
                },
                occurred_at=max(provider_timestamps),
            )
        )
    session.flush()
    return IngestionSummary(
        odds_quotes_created=created,
        odds_quotes_deduplicated=deduplicated,
        odds_quotes_unsupported=unsupported,
    )


def _provider(session: Session) -> Provider:
    provider = session.scalar(select(Provider).where(Provider.name == PROVIDER_NAME))
    if provider is None:
        provider = Provider(
            name=PROVIDER_NAME,
            kind="football-data",
            base_url=PROVIDER_BASE_URL,
            is_active=True,
        )
        session.add(provider)
        session.flush()
    elif not provider.is_active:
        raise ApiFootballIngestionError("API-Football provider is disabled")
    return provider


def _competition(
    session: Session, provider: Provider, parsed: ApiFootballFixture
) -> Competition:
    existing = _mapped_entity(
        session,
        provider.id,
        EntityType.COMPETITION,
        parsed.external_league_id,
        Competition,
    )
    if existing is not None:
        return existing
    competition = Competition(
        name=_bounded(parsed.league_name, 150, "competition name"),
        country=_bounded(parsed.league_country, 80, "competition country"),
    )
    session.add(competition)
    session.flush()
    _mapping(
        session,
        provider,
        EntityType.COMPETITION,
        parsed.external_league_id,
        competition.id,
    )
    return competition


def _season(
    session: Session,
    provider: Provider,
    competition: Competition,
    parsed: ApiFootballFixture,
) -> Season:
    external_id = f"{parsed.external_league_id}:{parsed.season}"
    existing = _mapped_entity(session, provider.id, EntityType.SEASON, external_id, Season)
    if existing is not None:
        if existing.competition_id != competition.id:
            raise ApiFootballIngestionError("season mapping points to another competition")
        return existing
    season = Season(competition=competition, label=str(parsed.season))
    session.add(season)
    session.flush()
    _mapping(session, provider, EntityType.SEASON, external_id, season.id)
    return season


def _team(
    session: Session,
    provider: Provider,
    external_id: str,
    name: str,
) -> Team:
    existing = _mapped_entity(session, provider.id, EntityType.TEAM, external_id, Team)
    if existing is not None:
        return existing
    team = Team(name=_bounded(name, 150, "team name"))
    session.add(team)
    session.flush()
    _mapping(session, provider, EntityType.TEAM, external_id, team.id)
    return team


T = TypeVar("T")


def _mapped_entity(
    session: Session,
    provider_id: uuid.UUID,
    entity_type: EntityType,
    external_id: str,
    model: type[T],
) -> T | None:
    mapping = session.scalar(
        select(SourceMapping).where(
            SourceMapping.provider_id == provider_id,
            SourceMapping.entity_type == entity_type,
            SourceMapping.external_id == external_id,
        )
    )
    if mapping is None:
        return None
    entity = session.get(model, mapping.canonical_id)
    if entity is None:
        raise ApiFootballIngestionError(
            f"{entity_type.value} mapping {external_id} points to a missing row"
        )
    return entity


def _mapping(
    session: Session,
    provider: Provider,
    entity_type: EntityType,
    external_id: str,
    canonical_id: uuid.UUID,
) -> None:
    session.add(
        SourceMapping(
            provider=provider,
            entity_type=entity_type,
            external_id=external_id,
            canonical_id=canonical_id,
            confidence=1.0,
        )
    )
    session.flush()


def _assert_fixture_identity(
    fixture: Fixture,
    competition: Competition,
    season: Season,
    home: Team,
    away: Team,
    parsed: ApiFootballFixture,
) -> None:
    if (
        fixture.competition_id != competition.id
        or fixture.season_id != season.id
        or fixture.home_team_id != home.id
        or fixture.away_team_id != away.id
    ):
        raise ApiFootballIngestionError(
            f"fixture {parsed.external_fixture_id} identity conflicts with its canonical mapping"
        )


def _update_fixture(
    session: Session,
    fixture: Fixture,
    parsed: ApiFootballFixture,
    captured_at: datetime,
) -> bool:
    before = {
        "kickoff_utc": _as_utc(fixture.kickoff_utc).isoformat(),
        "status": fixture.status.value,
        "venue": fixture.venue,
        "home_goals": fixture.home_goals,
        "away_goals": fixture.away_goals,
    }
    if fixture.status is FixtureStatus.FINISHED and parsed.status != "finished":
        raise ApiFootballIngestionError("a finished fixture cannot regress to a non-final status")
    next_venue = _bounded(parsed.venue, 150, "fixture venue")
    next_home_goals = parsed.home_goals if parsed.status == "finished" else fixture.home_goals
    next_away_goals = parsed.away_goals if parsed.status == "finished" else fixture.away_goals
    after = {
        "kickoff_utc": parsed.kickoff_utc.isoformat(),
        "status": parsed.status,
        "venue": next_venue,
        "home_goals": next_home_goals,
        "away_goals": next_away_goals,
    }
    if before == after:
        return False
    fixture.kickoff_utc = parsed.kickoff_utc
    fixture.status = FixtureStatus(parsed.status)
    fixture.venue = next_venue
    fixture.home_goals = next_home_goals
    fixture.away_goals = next_away_goals
    session.add(
        AuditEvent(
            event_type=AuditEventType.DATA_REVISION,
            actor=AuditActor.SYSTEM,
            actor_ref="api-football-ingestion",
            action="reconcile_fixture",
            summary="Reconciled canonical fixture from a newer provider observation",
            entity_type="fixtures",
            entity_id=fixture.id,
            payload={"before": before, "after": after},
            occurred_at=captured_at.astimezone(UTC),
        )
    )
    return True


def _append_fixture_snapshot(
    session: Session,
    fixture: Fixture,
    raw: dict[str, Any],
    captured_at: datetime,
) -> bool:
    return _append_stats_snapshot(
        session,
        fixture.id,
        {"endpoint": "fixtures", "record": raw},
        captured_at,
        source=FIXTURE_SOURCE,
    )


def _append_stats_snapshot(
    session: Session,
    fixture_id: uuid.UUID,
    payload: dict[str, Any],
    captured_at: datetime,
    *,
    source: str,
) -> bool:
    as_of = captured_at.astimezone(UTC)
    existing = session.scalar(
        select(StatsSnapshot).where(
            StatsSnapshot.fixture_id == fixture_id,
            StatsSnapshot.as_of_timestamp == as_of,
            StatsSnapshot.source == source,
        )
    )
    if existing is not None:
        if existing.payload != payload:
            raise ApiFootballIngestionError(
                "the same fixture capture timestamp contains conflicting provider payloads"
            )
        return False
    session.add(
        StatsSnapshot(
            subject_type=StatsSubjectType.FIXTURE,
            fixture_id=fixture_id,
            as_of_timestamp=as_of,
            payload=payload,
            source=source,
        )
    )
    return True


def _find_odds_quote(
    session: Session,
    fixture_id: uuid.UUID,
    parsed: ApiFootballOddsQuote,
    *,
    market: str,
    selection: str,
) -> OddsQuote | None:
    conditions = [
        OddsQuote.fixture_id == fixture_id,
        OddsQuote.bookmaker == parsed.bookmaker,
        OddsQuote.market == market,
        OddsQuote.selection == selection,
        OddsQuote.decimal_odds == parsed.decimal_odds,
        OddsQuote.captured_at == parsed.captured_at,
        OddsQuote.source == SOURCE_NAME,
    ]
    conditions.append(
        OddsQuote.line.is_(None) if parsed.line is None else OddsQuote.line == parsed.line
    )
    return session.scalar(select(OddsQuote).where(*conditions))


def _canonical_market_selection(
    parsed: ApiFootballOddsQuote,
) -> tuple[str, str] | None:
    market = _MARKET_MAP.get(parsed.market)
    if market is None:
        return None
    selection_maps = {
        "1X2": {"Home": "home", "Draw": "draw", "Away": "away"},
        "TOTALS": {"Over": "over", "Under": "under"},
        "BTTS": {"Yes": "yes", "No": "no"},
        "DOUBLE_CHANCE": {
            "Home/Draw": "1X",
            "Home/Away": "12",
            "Draw/Away": "X2",
        },
    }
    selection = selection_maps[market].get(parsed.selection)
    if selection is None:
        return None
    return market, selection


def _bounded(value: str | None, maximum: int, field: str) -> str | None:
    if value is not None and len(value) > maximum:
        raise ApiFootballIngestionError(f"{field} exceeds {maximum} characters")
    return value


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiFootballIngestionError(f"{name} must be timezone-aware")


def _payload_fixture_id(payload: dict[str, Any]) -> str:
    fixture = payload.get("fixture")
    if not isinstance(fixture, dict):
        raise ApiFootballIngestionError("odds fixture must be an object")
    value = fixture.get("id")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ApiFootballIngestionError("odds fixture id must be an identifier")
    return str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
