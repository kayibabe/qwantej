"""API-Football client, normalization, and canonical ingestion tests."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditEvent,
    Base,
    FeatureSnapshot,
    Fixture,
    FixtureStatus,
    OddsQuote,
    SourceMapping,
    StatsSnapshot,
)
from backend.services.api_football_client import ApiFootballClient, ApiFootballError
from backend.services.api_football_ingestion import (
    ApiFootballIngestionError,
    ingest_fixture_statistics,
    ingest_fixtures,
    ingest_odds,
    ingest_walk_forward_window,
)
from backend.services.features import create_feature_snapshot
from qwantej.fixtures import ApiFootballPayloadError, parse_fixture, parse_odds

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


def _fixture_payload(
    *,
    status: str = "NS",
    home_id: int = 10,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> dict:
    return {
        "fixture": {
            "id": 1001,
            "timestamp": int(KICKOFF.timestamp()),
            "date": KICKOFF.isoformat(),
            "status": {"short": status},
            "venue": {"name": "National Stadium"},
        },
        "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026},
        "teams": {
            "home": {"id": home_id, "name": "Home FC"},
            "away": {"id": 20, "name": "Away FC"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def _odds_payload() -> dict:
    return {
        "fixture": {"id": 1001},
        "update": "2026-09-06T12:30:00+00:00",
        "bookmakers": [
            {
                "id": 1,
                "name": "Bet Example",
                "bets": [
                    {
                        "id": 5,
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 2.5", "odd": "2.10"},
                            {"value": "Under 2.5", "odd": "1.75"},
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


class FakeTransport:
    def __init__(self, pages: dict[int, dict], *, status: int = 200, remaining: int = 99) -> None:
        self.pages = pages
        self.status = status
        self.remaining = remaining
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def get_json(self, url, *, headers, timeout_seconds):
        self.calls.append((url, dict(headers), timeout_seconds))
        page = int(parse_qs(urlparse(url).query).get("page", [1])[0])
        headers = {"x-ratelimit-requests-remaining": str(self.remaining)}
        return self.status, headers, self.pages[page]


def _wrapper(response: list[dict], *, page: int = 1, total: int = 1) -> dict:
    return {
        "errors": [],
        "results": len(response),
        "paging": {"current": page, "total": total},
        "response": response,
    }


def test_client_pages_and_keeps_key_out_of_url() -> None:
    transport = FakeTransport(
        {
            1: _wrapper([{"id": 1}], page=1, total=2),
            2: _wrapper([{"id": 2}], page=2, total=2),
        }
    )
    client = ApiFootballClient(api_key="test-secret", transport=transport)
    assert client.fixtures(league=39, season=2026) == ({"id": 1}, {"id": 2})
    assert len(transport.calls) == 2
    assert all("test-secret" not in url for url, _, _ in transport.calls)
    assert all(headers["x-apisports-key"] == "test-secret" for _, headers, _ in transport.calls)


def test_client_warns_when_quota_is_low(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport({1: _wrapper([{"id": 1}])}, remaining=10)
    client = ApiFootballClient(api_key="key", transport=transport)
    with caplog.at_level(logging.WARNING, logger="backend.services.api_football_client"):
        client.fixtures(league=39, season=2026)
    assert any(
        "quota low" in record.message and "10" in record.message for record in caplog.records
    )


def test_client_no_warning_when_quota_is_healthy(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport({1: _wrapper([{"id": 1}])}, remaining=500)
    client = ApiFootballClient(api_key="key", transport=transport)
    with caplog.at_level(logging.WARNING, logger="backend.services.api_football_client"):
        client.fixtures(league=39, season=2026)
    assert not any("quota low" in record.message for record in caplog.records)


def test_client_sanitizes_provider_errors() -> None:
    transport = FakeTransport(
        {1: {"errors": {"token": "test-secret"}, "response": [], "paging": {}}}
    )
    client = ApiFootballClient(api_key="test-secret", transport=transport)
    with pytest.raises(ApiFootballError) as exc_info:
        client.fixtures(league=39)
    assert "test-secret" not in str(exc_info.value)
    assert "token" in str(exc_info.value)


def test_parser_normalizes_fixture_and_total_line() -> None:
    fixture = parse_fixture(_fixture_payload())
    assert fixture.kickoff_utc == KICKOFF
    assert fixture.status == "scheduled"
    quotes = parse_odds(_odds_payload())
    assert [(quote.selection, str(quote.line)) for quote in quotes] == [
        ("Over", "2.5"),
        ("Under", "2.5"),
    ]


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ApiFootballPayloadError, match="unsupported fixture status"):
        parse_fixture(_fixture_payload(status="NEW"))


def test_fixture_ingestion_creates_canonical_mappings_and_snapshot(
    session: Session,
) -> None:
    summary = ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    assert summary.fixtures_created == 1
    assert summary.fixture_snapshots_created == 1
    assert session.query(Fixture).count() == 1
    assert session.query(SourceMapping).count() == 5
    snapshot = session.scalar(select(StatsSnapshot))
    assert snapshot is not None
    assert snapshot.as_of_timestamp.replace(tzinfo=UTC) == NOW
    assert snapshot.payload["endpoint"] == "fixtures"


def test_fixture_exact_retry_is_idempotent(session: Session) -> None:
    first = ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    second = ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    assert first.fixture_snapshots_created == 1
    assert second == type(second)()
    assert session.query(Fixture).count() == 1
    assert session.query(StatsSnapshot).count() == 1


def test_fixture_finalization_is_audited(session: Session) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    summary = ingest_fixtures(
        session,
        [_fixture_payload(status="FT", home_goals=2, away_goals=1)],
        captured_at=NOW + timedelta(hours=3),
    )
    fixture = session.scalar(select(Fixture))
    assert fixture is not None
    assert summary.fixtures_updated == 1
    assert fixture.status is FixtureStatus.FINISHED
    assert (fixture.home_goals, fixture.away_goals) == (2, 1)
    assert session.query(AuditEvent).count() == 1


def test_fixture_identity_conflict_rolls_back_batch(session: Session) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    mappings_before = session.query(SourceMapping).count()
    with pytest.raises(ApiFootballIngestionError, match="identity conflicts"):
        ingest_fixtures(
            session,
            [_fixture_payload(home_id=999)],
            captured_at=NOW + timedelta(minutes=1),
        )
    assert session.query(SourceMapping).count() == mappings_before


def test_statistics_and_fixture_observations_can_share_capture_time(
    session: Session,
) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    created = ingest_fixture_statistics(
        session,
        external_fixture_id="1001",
        statistics=({"team": {"id": 10}, "statistics": []},),
        captured_at=NOW,
    )
    assert created
    assert session.query(StatsSnapshot).count() == 2


def test_odds_ingestion_is_idempotent(session: Session) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    first = ingest_odds(session, [_odds_payload()])
    second = ingest_odds(session, [_odds_payload()])
    assert first.odds_quotes_created == 2
    assert second.odds_quotes_created == 0
    assert second.odds_quotes_deduplicated == 2
    assert session.query(OddsQuote).count() == 2
    assert {quote.market for quote in session.scalars(select(OddsQuote))} == {"TOTALS"}


def test_unsupported_market_is_skipped_and_audited(session: Session) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    payload = _odds_payload()
    payload["bookmakers"][0]["bets"][0]["name"] = "Player To Score"
    summary = ingest_odds(session, [payload])
    assert summary.odds_quotes_created == 0
    assert summary.odds_quotes_unsupported == 2
    event = session.scalar(
        select(AuditEvent).where(AuditEvent.action == "skip_unsupported_odds_market")
    )
    assert event is not None
    assert event.payload["provider_markets"] == ["Player To Score"]


def test_ingested_sources_feed_frozen_feature_snapshot(session: Session) -> None:
    ingest_fixtures(session, [_fixture_payload()], captured_at=NOW)
    ingest_odds(session, [_odds_payload()])
    fixture = session.scalar(select(Fixture))
    stats = session.scalar(select(StatsSnapshot))
    odds = session.scalar(select(OddsQuote))
    assert fixture is not None and stats is not None and odds is not None
    feature = create_feature_snapshot(
        session,
        fixture_id=fixture.id,
        feature_version="api-football-baseline-v1",
        as_of_timestamp=NOW + timedelta(minutes=30),
        features={"market_over_2_5_odds": 2.1},
        stats_snapshot_ids=[stats.id],
        odds_quote_ids=[odds.id],
        imputation_policy_version="explicit-null-v1",
        code_commit="abc123",
    )
    assert isinstance(feature, FeatureSnapshot)
    assert feature.snapshot_ref.startswith("feature-snapshot:")


def test_statistics_before_fixture_raises(session: Session) -> None:
    with pytest.raises(ApiFootballIngestionError, match="must be ingested before its statistics"):
        ingest_fixture_statistics(
            session,
            external_fixture_id="9999",
            statistics=({"team": {"id": 10}, "statistics": []},),
            captured_at=NOW,
        )


def test_window_loader_ignores_odds_for_fixtures_outside_window(session: Session) -> None:
    outside_odds = _odds_payload()
    outside_odds["fixture"] = {"id": 9999}

    class StubClient:
        def fixtures(self, **parameters):
            return (_fixture_payload(),)

        def odds(self, **parameters):
            return (_odds_payload(), outside_odds)

        def fixture_statistics(self, fixture_id):
            raise AssertionError("statistics should not be fetched")

    summary = ingest_walk_forward_window(
        session,
        StubClient(),  # type: ignore[arg-type]
        league_id=39,
        season=2026,
        start_date=date(2026, 9, 6),
        end_date=date(2026, 9, 6),
        captured_at=NOW,
    )
    assert summary.fixtures_created == 1
    assert summary.odds_quotes_created == 2
    assert session.query(OddsQuote).count() == 2


def test_window_loader_can_skip_odds_without_calling_provider(session: Session) -> None:
    class StubClient:
        def fixtures(self, **parameters):
            return (_fixture_payload(),)

        def odds(self, **parameters):
            raise AssertionError("odds should not be fetched when disabled")

        def fixture_statistics(self, fixture_id):
            raise AssertionError("statistics should not be fetched")

    summary = ingest_walk_forward_window(
        session,
        StubClient(),  # type: ignore[arg-type]
        league_id=39,
        season=2026,
        start_date=date(2026, 9, 6),
        end_date=date(2026, 9, 6),
        captured_at=NOW,
        include_odds=False,
    )
    assert summary.fixtures_created == 1
    assert summary.odds_quotes_created == 0
    assert session.query(OddsQuote).count() == 0
