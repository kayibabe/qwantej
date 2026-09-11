"""Tests for the multi-league ingestion worker."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.workers.ingestion_worker import (
    RunSummary,
    WorkerConfig,
    _DEFAULT_INTERVAL_ALL,
    _DEFAULT_INTERVAL_SINGLE,
    discover_leagues,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _leagues_payload(*entries: tuple[int, str, str]) -> tuple[dict[str, Any], ...]:
    """Build a fake /leagues API response from (id, name, country) triples."""
    return tuple(
        {"league": {"id": lid, "name": name}, "country": {"name": country}}
        for lid, name, country in entries
    )


class _MockClient:
    """Minimal ApiFootballClient stand-in."""

    def __init__(self, leagues_payload, last_remaining: int | None = None):
        self._leagues_payload = leagues_payload
        self._last_remaining = last_remaining

    def leagues(self, **_kw: Any) -> tuple[dict[str, Any], ...]:
        return self._leagues_payload

    @property
    def last_requests_remaining(self) -> int | None:
        return self._last_remaining


# ---------------------------------------------------------------------------
# discover_leagues
# ---------------------------------------------------------------------------

class TestDiscoverLeagues:
    def test_returns_sorted_league_season_pairs(self):
        client = _MockClient(
            _leagues_payload((78, "Bundesliga", "Germany"), (39, "Premier League", "England"))
        )
        result = discover_leagues(client, 2026)
        assert result == [(39, 2026), (78, 2026)]

    def test_skips_entries_without_league_id(self):
        payload = ({"league": {}, "country": {"name": "Nowhere"}},)
        client = _MockClient(payload)
        result = discover_leagues(client, 2026)
        assert result == []

    def test_empty_response(self):
        client = _MockClient(())
        result = discover_leagues(client, 2026)
        assert result == []


# ---------------------------------------------------------------------------
# WorkerConfig defaults
# ---------------------------------------------------------------------------

class TestWorkerConfig:
    def test_default_leagues_is_none(self):
        cfg = WorkerConfig()
        assert cfg.leagues is None

    def test_default_season_is_current_year(self):
        cfg = WorkerConfig()
        assert cfg.season == date.today().year

    def test_default_interval_is_all_leagues(self):
        cfg = WorkerConfig()
        assert cfg.interval_seconds == _DEFAULT_INTERVAL_ALL

    def test_explicit_leagues_accepted(self):
        cfg = WorkerConfig(leagues=[(39, 2026), (78, 2026)])
        assert cfg.leagues == [(39, 2026), (78, 2026)]

    def test_quota_stop_below_default(self):
        cfg = WorkerConfig()
        assert cfg.quota_stop_below == 100


# ---------------------------------------------------------------------------
# run_once: discovery path
# ---------------------------------------------------------------------------

class TestRunOnce:
    """Targeted tests for run_once behaviour that don't require wiring the full stack."""

    def test_missing_api_key_returns_error(self):
        cfg = WorkerConfig(leagues=[(39, 2026)])
        mock_settings = MagicMock()
        mock_settings.api_football_key = "   "
        with (
            patch("backend.core.config.get_settings", return_value=mock_settings),
            patch("backend.core.logging.configure_logging"),
        ):
            from backend.workers.ingestion_worker import run_once
            summary = run_once(cfg)

        assert summary.errors == 1
        assert summary.leagues_attempted == 0

    def test_quota_guard_skips_leagues_at_threshold(self):
        """Quota guard triggers when remaining ≤ quota_stop_below before a league starts."""
        cfg = WorkerConfig(
            leagues=[(39, 2026), (78, 2026), (61, 2026)],
            quota_stop_below=50,
        )
        mock_settings = MagicMock()
        mock_settings.api_football_key = "test-key"
        mock_client = MagicMock()
        # Quota already at the stop threshold — all leagues should be skipped.
        mock_client.last_requests_remaining = 50

        from backend.services.api_football_ingestion import IngestionSummary

        with (
            patch("backend.core.config.get_settings", return_value=mock_settings),
            patch("backend.core.logging.configure_logging"),
            patch("backend.core.db.make_engine"),
            patch("backend.services.api_football_client.ApiFootballClient.from_settings",
                  return_value=mock_client),
            patch("backend.services.api_football_ingestion.ingest_walk_forward_window",
                  return_value=IngestionSummary()),
            patch("backend.core.db.session_scope"),
        ):
            from backend.workers.ingestion_worker import run_once
            summary = run_once(cfg)

        assert summary.leagues_skipped_quota == 3
        assert summary.leagues_attempted == 0

    def test_discovers_leagues_when_leagues_is_none(self):
        """leagues=None triggers discover_leagues before the ingestion loop."""
        cfg = WorkerConfig(leagues=None, season=2026)
        mock_settings = MagicMock()
        mock_settings.api_football_key = "test-key"
        mock_client = MagicMock()
        mock_client.last_requests_remaining = None

        from backend.services.api_football_ingestion import IngestionSummary

        with (
            patch("backend.core.config.get_settings", return_value=mock_settings),
            patch("backend.core.logging.configure_logging"),
            patch("backend.core.db.make_engine"),
            patch("backend.services.api_football_client.ApiFootballClient.from_settings",
                  return_value=mock_client),
            patch("backend.workers.ingestion_worker.discover_leagues",
                  return_value=[(39, 2026)]) as mock_discover,
            patch("backend.services.api_football_ingestion.ingest_walk_forward_window",
                  return_value=IngestionSummary(fixtures_created=1)),
            patch("backend.core.db.session_scope") as mock_scope,
        ):
            mock_scope.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

            from backend.workers.ingestion_worker import run_once
            summary = run_once(cfg)

        mock_discover.assert_called_once_with(mock_client, 2026)


# ---------------------------------------------------------------------------
# Ingestion service: skip odds when window is empty
# ---------------------------------------------------------------------------

class TestSkipOddsWhenNoFixtures:
    """Verify the ingestion service skips the odds call when window_fixture_ids is empty."""

    def _build_client(self, fixture_payloads, odds_called_flag: list):
        from backend.services.api_football_client import ApiFootballClient

        class _StubTransport:
            def get_json(self, url, *, headers, timeout_seconds):
                if "fixtures" in url:
                    return (200, {"x-ratelimit-requests-remaining": "500"}, {
                        "response": fixture_payloads,
                        "paging": {"current": 1, "total": 1},
                        "errors": {},
                    })
                if "odds" in url:
                    odds_called_flag.append(True)
                    return (200, {"x-ratelimit-requests-remaining": "499"}, {
                        "response": [],
                        "paging": {"current": 1, "total": 1},
                        "errors": {},
                    })
                raise AssertionError(f"Unexpected URL: {url}")

        return ApiFootballClient(api_key="test", transport=_StubTransport())

    def test_odds_not_called_when_window_empty(self):
        """When fixture list returns nothing in the window, odds must not be fetched."""
        from sqlalchemy import create_engine
        from backend.models import Base
        from backend.services.api_football_ingestion import ingest_walk_forward_window

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        odds_calls: list = []
        client = self._build_client(fixture_payloads=[], odds_called_flag=odds_calls)

        with engine.connect() as conn:
            from sqlalchemy.orm import Session
            with Session(conn) as session:
                summary = ingest_walk_forward_window(
                    session, client,
                    league_id=39, season=2026,
                    start_date=date(2026, 9, 10),
                    end_date=date(2026, 9, 17),
                    captured_at=datetime(2026, 9, 11, tzinfo=UTC),
                    include_odds=True,
                )

        assert odds_calls == [], "odds endpoint was called despite empty fixture window"
        assert summary.odds_quotes_created == 0
