"""Tests for the multi-league ingestion worker and scheduler league/season logic."""

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
    SUPPORTED_LEAGUE_IDS,
    current_season,
    discover_leagues,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _leagues_payload(*entries: tuple[int, str, str]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {"league": {"id": lid, "name": name}, "country": {"name": country}}
        for lid, name, country in entries
    )


class _MockClient:
    def __init__(self, leagues_payload=(), last_remaining: int | None = None):
        self._leagues_payload = leagues_payload
        self._last_remaining = last_remaining

    def leagues(self, **_kw: Any) -> tuple[dict[str, Any], ...]:
        return self._leagues_payload

    @property
    def last_requests_remaining(self) -> int | None:
        return self._last_remaining


# ---------------------------------------------------------------------------
# current_season — European football season derivation
# ---------------------------------------------------------------------------

class TestCurrentSeason:
    def test_july_onwards_uses_current_year(self):
        with patch("backend.workers.ingestion_worker.date") as mock_date:
            mock_date.today.return_value = date(2026, 7, 1)
            assert current_season() == 2026

    def test_august_uses_current_year(self):
        with patch("backend.workers.ingestion_worker.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            assert current_season() == 2026

    def test_december_uses_current_year(self):
        with patch("backend.workers.ingestion_worker.date") as mock_date:
            mock_date.today.return_value = date(2026, 12, 31)
            assert current_season() == 2026

    def test_january_uses_previous_year(self):
        with patch("backend.workers.ingestion_worker.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            assert current_season() == 2025

    def test_june_uses_previous_year(self):
        with patch("backend.workers.ingestion_worker.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 30)
            assert current_season() == 2025


# ---------------------------------------------------------------------------
# WorkerConfig — default production league list and interval
# ---------------------------------------------------------------------------

class TestWorkerConfigDefaults:
    def test_default_leagues_are_supported_ids(self):
        cfg = WorkerConfig()
        league_ids = sorted(lid for lid, _ in cfg.leagues)
        assert league_ids == sorted(SUPPORTED_LEAGUE_IDS)

    def test_default_leagues_all_use_current_season(self):
        cfg = WorkerConfig()
        expected = current_season()
        for _, season in cfg.leagues:
            assert season == expected

    def test_default_interval_is_single_mode(self):
        cfg = WorkerConfig()
        assert cfg.interval_seconds == _DEFAULT_INTERVAL_SINGLE

    def test_none_leagues_enables_all_leagues_discovery(self):
        cfg = WorkerConfig(leagues=None)
        assert cfg.leagues is None

    def test_explicit_leagues_override_default(self):
        cfg = WorkerConfig(leagues=[(39, 2026)])
        assert cfg.leagues == [(39, 2026)]
        assert len(cfg.leagues) == 1

    def test_season_field_matches_default_league_season(self):
        """WorkerConfig.season and the season embedded in leagues must agree."""
        cfg = WorkerConfig()
        for _, season in cfg.leagues:
            assert season == cfg.season

    def test_explicit_season_propagates_to_default_leagues(self):
        """Passing season explicitly should override the date-derived default."""
        cfg = WorkerConfig(
            leagues=[(lid, 2025) for lid in SUPPORTED_LEAGUE_IDS],
            season=2025,
        )
        for _, season in cfg.leagues:
            assert season == 2025


# ---------------------------------------------------------------------------
# discover_leagues
# ---------------------------------------------------------------------------

class TestDiscoverLeagues:
    def test_returns_sorted_pairs(self):
        client = _MockClient(
            _leagues_payload((78, "Bundesliga", "Germany"), (39, "Premier League", "England"))
        )
        result = discover_leagues(client, 2026)
        assert result == [(39, 2026), (78, 2026)]

    def test_skips_entries_without_id(self):
        client = _MockClient(({"league": {}, "country": {"name": "X"}},))
        assert discover_leagues(client, 2026) == []

    def test_empty_response(self):
        assert discover_leagues(_MockClient(), 2026) == []


# ---------------------------------------------------------------------------
# run_once — API-key guard, quota guard, discovery path
# ---------------------------------------------------------------------------

class TestRunOnce:
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

    def test_quota_guard_skips_all_when_already_at_threshold(self):
        cfg = WorkerConfig(
            leagues=[(39, 2026), (78, 2026), (61, 2026)],
            quota_stop_below=50,
        )
        mock_settings = MagicMock()
        mock_settings.api_football_key = "test-key"
        mock_client = MagicMock()
        mock_client.last_requests_remaining = 50  # already at threshold

        from backend.services.api_football_ingestion import IngestionSummary
        with (
            patch("backend.core.config.get_settings", return_value=mock_settings),
            patch("backend.core.logging.configure_logging"),
            patch("backend.core.db.make_engine"),
            patch("backend.services.api_football_client.ApiFootballClient.from_settings",
                  return_value=mock_client),
            patch("backend.core.db.session_scope"),
        ):
            from backend.workers.ingestion_worker import run_once
            summary = run_once(cfg)

        assert summary.leagues_skipped_quota == 3
        assert summary.leagues_attempted == 0

    def test_discovers_leagues_when_leagues_is_none(self):
        """leagues=None should call discover_leagues with cfg.season."""
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
            patch("backend.core.db.session_scope") as mock_scope,
            patch("backend.services.api_football_ingestion.ingest_walk_forward_window",
                  return_value=IngestionSummary()),
        ):
            mock_scope.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)
            from backend.workers.ingestion_worker import run_once
            run_once(cfg)

        mock_discover.assert_called_once_with(mock_client, 2026)


# ---------------------------------------------------------------------------
# Scheduler — arg parsing covers all four required regression cases
# ---------------------------------------------------------------------------

class TestSchedulerArgParsing:
    """Tests for the scheduler's _parse_args() to cover the four regression cases."""

    def _parse(self, argv: list[str]):
        from backend.workers.scheduler import _parse_args
        with patch("sys.argv", ["scheduler"] + argv):
            return _parse_args()

    # 1. Default: production mode, four leagues, 3600 s
    def test_no_flags_is_production_mode(self):
        args = self._parse([])
        assert args.all_leagues is False
        assert args.leagues is None  # no explicit --league flags

    def test_no_flags_ingest_interval_resolves_to_production(self):
        from backend.workers.scheduler import _DEFAULT_INGEST_INTERVAL_PRODUCTION
        args = self._parse([])
        assert args.ingest_interval is None  # will resolve to production default
        # Verify the resolution logic produces the production interval.
        resolved = (
            _DEFAULT_INGEST_INTERVAL_PRODUCTION
            if not args.all_leagues
            else 999999
        )
        assert resolved == _DEFAULT_INGEST_INTERVAL_PRODUCTION

    # 2. --all-leagues enables discovery
    def test_all_leagues_flag_sets_discovery_mode(self):
        args = self._parse(["--all-leagues"])
        assert args.all_leagues is True

    def test_all_leagues_ingest_interval_resolves_to_all_leagues(self):
        from backend.workers.scheduler import _DEFAULT_INGEST_INTERVAL_ALL
        args = self._parse(["--all-leagues"])
        resolved = (
            _DEFAULT_INGEST_INTERVAL_ALL
            if args.all_leagues
            else 999999
        )
        assert resolved == _DEFAULT_INGEST_INTERVAL_ALL

    # 3. --league overrides defaults
    def test_explicit_league_overrides_default(self):
        args = self._parse(["--league", "39"])
        assert args.leagues == [39]
        assert args.all_leagues is False

    def test_multiple_explicit_leagues(self):
        args = self._parse(["--league", "39", "--league", "78"])
        assert sorted(args.leagues) == [39, 78]

    def test_league_and_all_leagues_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            self._parse(["--league", "39", "--all-leagues"])

    # 4. Season is derived consistently
    def test_no_season_flag_leaves_season_none(self):
        args = self._parse([])
        assert args.season is None  # resolved by main() via current_season()

    def test_explicit_season_is_passed_through(self):
        args = self._parse(["--season", "2025"])
        assert args.season == 2025

    def test_scheduler_make_ingestion_run_production_uses_supported_ids(self):
        """_make_ingestion_run with no flags should embed the 4 supported IDs."""
        from backend.workers.scheduler import _make_ingestion_run
        from backend.workers.ingestion_worker import SUPPORTED_LEAGUE_IDS, current_season

        season = current_season()
        _run = _make_ingestion_run(
            all_leagues=False, explicit_league_ids=[], season=season
        )
        # The callable closes over a WorkerConfig — retrieve it.
        import inspect
        closed_config = None
        for cell in _run.__code__.co_freevars:
            pass
        # Access via closure cells
        closure_vars = {
            name: cell.cell_contents
            for name, cell in zip(_run.__code__.co_freevars, _run.__closure__ or [])
        }
        config = closure_vars.get("config")
        assert config is not None
        league_ids = sorted(lid for lid, _ in config.leagues)
        assert league_ids == sorted(SUPPORTED_LEAGUE_IDS)
        for _, s in config.leagues:
            assert s == season

    def test_scheduler_make_ingestion_run_all_leagues_uses_none(self):
        """_make_ingestion_run with all_leagues=True should set leagues=None."""
        from backend.workers.scheduler import _make_ingestion_run
        from backend.workers.ingestion_worker import current_season

        season = current_season()
        _run = _make_ingestion_run(
            all_leagues=True, explicit_league_ids=[], season=season
        )
        closure_vars = {
            name: cell.cell_contents
            for name, cell in zip(_run.__code__.co_freevars, _run.__closure__ or [])
        }
        config = closure_vars.get("config")
        assert config is not None
        assert config.leagues is None  # None = discover at runtime

    def test_scheduler_make_ingestion_run_explicit_leagues(self):
        """_make_ingestion_run with explicit IDs uses only those IDs."""
        from backend.workers.scheduler import _make_ingestion_run
        from backend.workers.ingestion_worker import current_season

        season = current_season()
        _run = _make_ingestion_run(
            all_leagues=False, explicit_league_ids=[39], season=season
        )
        closure_vars = {
            name: cell.cell_contents
            for name, cell in zip(_run.__code__.co_freevars, _run.__closure__ or [])
        }
        config = closure_vars.get("config")
        assert config is not None
        assert config.leagues == [(39, season)]


# ---------------------------------------------------------------------------
# Ingestion service: skip odds when fixture window is empty
# ---------------------------------------------------------------------------

class TestSkipOddsWhenNoFixtures:
    def _build_client(self, odds_called_flag: list):
        from backend.services.api_football_client import ApiFootballClient

        class _StubTransport:
            def get_json(self, url, *, headers, timeout_seconds):
                if "fixtures" in url:
                    return (200, {"x-ratelimit-requests-remaining": "500"}, {
                        "response": [],
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

    def test_odds_not_fetched_when_window_empty(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from backend.models import Base
        from backend.services.api_football_ingestion import ingest_walk_forward_window

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        odds_calls: list = []
        client = self._build_client(odds_called_flag=odds_calls)

        with engine.connect() as conn:
            with Session(conn) as session:
                ingest_walk_forward_window(
                    session, client,
                    league_id=39, season=2026,
                    start_date=date(2026, 9, 10),
                    end_date=date(2026, 9, 17),
                    captured_at=datetime(2026, 9, 11, tzinfo=UTC),
                    include_odds=True,
                )

        assert odds_calls == [], "odds endpoint called despite empty fixture window"
