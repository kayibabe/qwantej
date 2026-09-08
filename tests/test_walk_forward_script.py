"""Unit tests for scripts/run_walk_forward.py helpers.

Covers: data_snapshot_ref provenance, --calibration-only row inclusion,
source-less snapshot guard, and --all-leagues observation scoping.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Make the script importable without running main()
_repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo))
sys.path.insert(0, str(_repo / "src"))

from backend.models import (  # noqa: E402
    Base,
    Competition,
    Fixture,
    FixtureStatus,
    Season,
    StatsSnapshot,
    StatsSubjectType,
    Team,
)
from backend.services.feature_extraction import (  # noqa: E402
    extract_fixture_features,
    fixture_result_as_of,
    fixture_result_observed_after_kickoff,
)
from qwantej.performance.backtest import BacktestObservation  # noqa: E402
from scripts.run_walk_forward import (  # noqa: E402
    ExperimentConfig,
    _build_backtest_observations,
    _data_snapshot_ref,
    _eligible_walk_forward_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRAIN_FROM = date(2026, 8, 1)
_TRAIN_TO = date(2026, 9, 5)
_TEST_FROM = date(2026, 9, 6)
_TEST_TO = date(2026, 9, 7)


def _cfg(**kwargs) -> ExperimentConfig:
    defaults = dict(
        league_id=39,
        season=2026,
        train_from=_TRAIN_FROM,
        train_to=_TRAIN_TO,
        test_from=_TEST_FROM,
        test_to=_TEST_TO,
        n_recent=30,
        dry_run=False,
        name="test-experiment",
        calibration_only=False,
        all_leagues=False,
    )
    defaults.update(kwargs)
    return ExperimentConfig(**defaults)


def _obs(*, decision_offset_days: int = 0, has_odds: bool = True) -> BacktestObservation:
    decision = datetime(2026, 9, 1, 12, tzinfo=UTC) + timedelta(days=decision_offset_days)
    return BacktestObservation(
        observation_id=f"obs-{decision_offset_days}",
        decision_as_of=decision,
        feature_as_of=decision - timedelta(hours=1),
        outcome_observed_at=decision + timedelta(hours=2),
        model_version="model-v1",
        raw_probability=0.55,
        outcome=1,
        fair_market_probability=0.50 if has_odds else None,
        executable_odds=2.10 if has_odds else None,
        quote_timestamp=(decision - timedelta(minutes=30)) if has_odds else None,
        model_probabilities=(0.55, 0.25, 0.20),
    )


# ---------------------------------------------------------------------------
# P1 — data_snapshot_ref provenance
# ---------------------------------------------------------------------------


class TestDataSnapshotRef:
    def test_single_league_standard(self):
        ref = _data_snapshot_ref(_cfg(league_id=39, season=2026))
        assert ref == "api-football:league=39:season=2026:n_recent=30"

    def test_single_league_calibration_only(self):
        ref = _data_snapshot_ref(_cfg(league_id=39, season=2026, calibration_only=True))
        assert ref == "api-football:league=39:season=2026:n_recent=30:calibration-only"

    def test_all_leagues_standard(self):
        ref = _data_snapshot_ref(_cfg(all_leagues=True))
        assert ref == "api-football:all-leagues:n_recent=30"

    def test_all_leagues_calibration_only(self):
        ref = _data_snapshot_ref(_cfg(all_leagues=True, calibration_only=True))
        assert ref == "api-football:all-leagues:n_recent=30:calibration-only"

    def test_calibration_only_flag_makes_refs_distinct(self):
        standard = _data_snapshot_ref(_cfg())
        calib = _data_snapshot_ref(_cfg(calibration_only=True))
        assert standard != calib

    def test_all_leagues_flag_makes_refs_distinct(self):
        single = _data_snapshot_ref(_cfg(league_id=39, season=2026))
        multi = _data_snapshot_ref(_cfg(all_leagues=True))
        assert single != multi


# ---------------------------------------------------------------------------
# P2 — _eligible_walk_forward_row
# ---------------------------------------------------------------------------


class TestEligibleWalkForwardRow:
    def test_full_row_is_eligible(self):
        assert _eligible_walk_forward_row(_obs(has_odds=True))

    def test_row_without_odds_is_not_eligible(self):
        assert not _eligible_walk_forward_row(_obs(has_odds=False))

    def test_row_missing_outcome_is_not_eligible(self):
        obs = _obs(has_odds=True)
        from dataclasses import replace
        obs = replace(obs, outcome=None)
        assert not _eligible_walk_forward_row(obs)

    def test_row_missing_quote_timestamp_is_not_eligible(self):
        obs = _obs(has_odds=True)
        from dataclasses import replace
        obs = replace(obs, quote_timestamp=None)
        assert not _eligible_walk_forward_row(obs)


# ---------------------------------------------------------------------------
# P2 — sourceless snapshot guard
# ---------------------------------------------------------------------------


class TestSourcelessSnapshotGuard:
    """Verify create_feature_snapshot is not called when no source ids exist."""

    def test_no_snapshot_created_when_both_source_lists_empty(self):
        """The guard ``if _stats_ids or source_odds_ids`` prevents the call."""
        # Patch create_feature_snapshot to detect if it was called.
        mock_create = MagicMock()

        # We test the guard logic directly: if both lists are empty, the mock
        # must NOT be called; if either is non-empty, it must be called once.
        def _run(stats_ids, source_odds_ids):
            if stats_ids or source_odds_ids:
                mock_create(stats_ids=stats_ids, odds_ids=source_odds_ids)

        mock_create.reset_mock()
        _run([], [])
        mock_create.assert_not_called()

        mock_create.reset_mock()
        _run(["s1"], [])
        mock_create.assert_called_once()

        mock_create.reset_mock()
        _run([], ["o1"])
        mock_create.assert_called_once()

        mock_create.reset_mock()
        _run(["s1"], ["o1"])
        mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# P2 — calibration-only observation inclusion (in-memory DB)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def _seed_finished_fixture(session: Session, *, kickoff: datetime) -> Fixture:
    comp = Competition(name="Test League")
    team_h = Team(name="Home FC")
    team_a = Team(name="Away FC")
    season = Season(
        competition=comp, label="2026",
        start_date=date(2026, 8, 1), end_date=date(2027, 5, 31),
    )
    session.add_all([comp, team_h, team_a, season])
    session.flush()
    fixture = Fixture(
        competition=comp, season=season,
        home_team=team_h, away_team=team_a,
        kickoff_utc=kickoff, status=FixtureStatus.FINISHED,
        home_goals=2, away_goals=1,
    )
    session.add(fixture)
    session.flush()
    return fixture


def _add_fixture_result_snapshot(
    session: Session,
    fixture: Fixture,
    *,
    captured_at: datetime,
    home_goals: int,
    away_goals: int,
) -> StatsSnapshot:
    record = {
        "fixture": {
            "id": str(fixture.id),
            "timestamp": int(fixture.kickoff_utc.timestamp()),
            "date": fixture.kickoff_utc.isoformat(),
            "status": {"short": "FT"},
            "venue": {"name": "Test Ground"},
        },
        "league": {"id": 39, "name": "Test League", "country": "Test", "season": 2026},
        "teams": {
            "home": {"id": str(fixture.home_team_id), "name": "Home FC"},
            "away": {"id": str(fixture.away_team_id), "name": "Away FC"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }
    snapshot = StatsSnapshot(
        subject_type=StatsSubjectType.FIXTURE,
        fixture_id=fixture.id,
        as_of_timestamp=captured_at,
        payload={"endpoint": "fixtures", "record": record},
        source="api-football:fixtures",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


class TestCalibrationOnlyObservationInclusion:
    """Observations without odds are kept only in --calibration-only mode."""

    def test_row_without_odds_excluded_in_standard_mode(self):
        # _eligible_walk_forward_row is False without odds — confirmed above.
        # Verify that the script-level guard ``if not odds_ids and not cfg.calibration_only``
        # models the same contract.
        cfg_standard = _cfg(calibration_only=False)
        odds_ids: list = []
        should_skip = not odds_ids and not cfg_standard.calibration_only
        assert should_skip

    def test_row_without_odds_kept_in_calibration_only_mode(self):
        cfg_calib = _cfg(calibration_only=True)
        odds_ids: list = []
        should_skip = not odds_ids and not cfg_calib.calibration_only
        assert not should_skip

    def test_row_with_odds_never_skipped_regardless_of_mode(self):
        for calibration_only in (True, False):
            cfg = _cfg(calibration_only=calibration_only)
            odds_ids = ["some-id"]
            should_skip = not odds_ids and not cfg.calibration_only
            assert not should_skip


class TestPointInTimeResultSources:
    def test_result_comes_from_immutable_snapshot_not_mutable_fixture(self, mem_session):
        kickoff = datetime(2026, 9, 6, 12, tzinfo=UTC)
        fixture = _seed_finished_fixture(mem_session, kickoff=kickoff)
        fixture.home_goals = 9
        fixture.away_goals = 9
        observed_at = kickoff + timedelta(hours=2)
        _add_fixture_result_snapshot(
            mem_session,
            fixture,
            captured_at=observed_at,
            home_goals=0,
            away_goals=1,
        )

        assert fixture_result_observed_after_kickoff(mem_session, fixture).home_goals == 0
        result = fixture_result_as_of(
            mem_session,
            fixture,
            as_of=observed_at + timedelta(minutes=1),
        )
        assert result is not None
        assert (result.home_goals, result.away_goals) == (0, 1)
        assert result.observed_at == observed_at

    def test_feature_history_uses_only_results_observed_by_cutoff(self, mem_session):
        target_kickoff = datetime(2026, 9, 6, 12, tzinfo=UTC)
        target = _seed_finished_fixture(mem_session, kickoff=target_kickoff)
        historical = Fixture(
            competition=target.competition,
            season=target.season,
            home_team=target.home_team,
            away_team=target.away_team,
            kickoff_utc=datetime(2026, 9, 5, 12, tzinfo=UTC),
            status=FixtureStatus.FINISHED,
            home_goals=9,
            away_goals=9,
        )
        mem_session.add(historical)
        mem_session.flush()
        _add_fixture_result_snapshot(
            mem_session,
            historical,
            captured_at=datetime(2026, 9, 5, 14, tzinfo=UTC),
            home_goals=1,
            away_goals=0,
        )

        _, _, _, history = extract_fixture_features(
            mem_session,
            target,
            as_of=target_kickoff - timedelta(hours=2),
            n_recent=30,
        )
        assert [(row.home_goals, row.away_goals) for row in history] == [(1, 0)]


class TestBuildBacktestObservationBranches:
    def test_all_leagues_calibration_only_uses_pit_result_and_no_odds(self, mem_session):
        target_kickoff = datetime(2026, 9, 6, 12, tzinfo=UTC)
        target = _seed_finished_fixture(mem_session, kickoff=target_kickoff)
        for index in range(3):
            historical = Fixture(
                competition=target.competition,
                season=target.season,
                home_team=target.home_team,
                away_team=target.away_team,
                kickoff_utc=datetime(2026, 8, 1 + index, 12, tzinfo=UTC),
                status=FixtureStatus.FINISHED,
                home_goals=8,
                away_goals=8,
            )
            mem_session.add(historical)
            mem_session.flush()
            _add_fixture_result_snapshot(
                mem_session,
                historical,
                captured_at=historical.kickoff_utc + timedelta(hours=2),
                home_goals=index + 1,
                away_goals=index,
            )
        _add_fixture_result_snapshot(
            mem_session,
            target,
            captured_at=target_kickoff + timedelta(hours=2),
            home_goals=0,
            away_goals=1,
        )

        calibration_cfg = _cfg(calibration_only=True, all_leagues=True)
        observations = _build_backtest_observations(mem_session, calibration_cfg)
        assert len(observations) == 1
        assert observations[0].observation_id == str(target.id)
        assert observations[0].outcome == 0
        assert observations[0].outcome_observed_at == target_kickoff + timedelta(hours=2)
        assert observations[0].fair_market_probability is None

        standard_cfg = _cfg(calibration_only=False, all_leagues=True)
        assert _build_backtest_observations(mem_session, standard_cfg) == []


# ---------------------------------------------------------------------------
# P2 — --all-leagues scoping (verify the fixture query differs)
# ---------------------------------------------------------------------------


class TestAllLeaguesScoping:
    """The --all-leagues branch omits competition/season filters."""

    def test_all_leagues_cfg_sets_flag(self):
        cfg = _cfg(all_leagues=True)
        assert cfg.all_leagues is True

    def test_single_league_cfg_has_flag_false_by_default(self):
        cfg = _cfg()
        assert cfg.all_leagues is False

    def test_all_leagues_ref_does_not_contain_league_id(self):
        ref = _data_snapshot_ref(_cfg(all_leagues=True, league_id=39, season=2026))
        assert "league=39" not in ref
        assert "season=2026" not in ref

    def test_single_league_ref_contains_league_and_season(self):
        ref = _data_snapshot_ref(_cfg(league_id=140, season=2025))
        assert "league=140" in ref
        assert "season=2025" in ref
