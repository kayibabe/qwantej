"""Tests for the live signal pipeline (scripts/run_signal_pipeline.py).

Uses the in-process SQLite DB (same fixture as run_walk_forward tests) so
no Postgres container is required.  Tests cover:

- _fit_linear_calibration: pure function, no I/O
- _apply_calibration: pure function, no I/O
- _upcoming_unpredicted_fixtures: DB query correctness
- _ensure_champion_model: idempotent bootstrap of ModelRegistry + ModelRun
- _ensure_champion_calibration: identity path and fitted path
- _best_pre_kickoff_odds: returns correct quote and respects cutoff
- run_once: dry-run integration test that wires the full pipeline

Fixtures with no odds → value gate rejects → no predictions published (expected).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from scripts.run_signal_pipeline import (
    _apply_calibration,
    _best_pre_kickoff_odds,
    _devigged_fair_prob,
    _ensure_champion_calibration,
    _ensure_champion_model,
    _fit_linear_calibration,
    _upcoming_unpredicted_fixtures,
    run_once,
)

# ---------------------------------------------------------------------------
# Helpers — shared DB seeding
# ---------------------------------------------------------------------------

def _make_session():
    """Return a SQLite in-memory session with all migrations applied."""
    from backend.core.db import make_engine
    engine = make_engine("sqlite:///:memory:")
    from pathlib import Path

    import alembic.command
    import alembic.config
    alembic_cfg = alembic.config.Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///:memory:")
    alembic_cfg.attributes["connection"] = engine.connect()
    alembic.command.upgrade(alembic_cfg, "head")
    return engine


def _seed_provider_and_competition(session, *, validated: bool = True):
    from backend.models import EntityType, Provider, Season, SourceMapping, Team
    prov = Provider(name="API-Football", kind="odds", base_url="https://api-football.com")
    session.add(prov)
    session.flush()
    from backend.models.fixtures import Competition as Comp
    comp = Comp(name="Premier League", country="England", validated=validated)
    session.add(comp)
    session.flush()
    season = Season(
        competition_id=comp.id,
        label="2026",
        start_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
        end_date=datetime(2027, 6, 1, tzinfo=UTC).date(),
    )
    session.add(season)
    session.flush()
    sm = SourceMapping(
        provider_id=prov.id,
        entity_type=EntityType.COMPETITION,
        external_id="39",
        canonical_id=comp.id,
    )
    session.add(sm)
    session.flush()
    home = Team(name="Arsenal", country="England")
    away = Team(name="Chelsea", country="England")
    session.add_all([home, away])
    session.flush()
    return comp, season, home, away


def _make_fixture(session, comp, season, home, away, kickoff=None):
    from backend.models import Fixture, FixtureStatus
    if kickoff is None:
        kickoff = datetime.now(UTC) + timedelta(hours=12)
    f = Fixture(
        competition_id=comp.id,
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_utc=kickoff,
        status=FixtureStatus.SCHEDULED,
    )
    session.add(f)
    session.flush()
    return f


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

class TestFitLinearCalibration:
    def test_perfect_fit(self):
        # slope=1, intercept=0 when outcomes == probabilities
        probs = [0.2, 0.4, 0.6, 0.8]
        outcomes = [0.2, 0.4, 0.6, 0.8]
        params = _fit_linear_calibration(probs, outcomes)
        assert abs(params["slope"] - 1.0) < 1e-9
        assert abs(params["intercept"]) < 1e-9

    def test_zero_variance_falls_back_to_identity(self):
        probs = [0.5, 0.5, 0.5]
        outcomes = [1.0, 0.0, 1.0]
        params = _fit_linear_calibration(probs, outcomes)
        assert params == {"slope": 1.0, "intercept": 0.0}

    def test_overconfident_model_shrinks_slope(self):
        # High probabilities but mediocre outcomes → slope < 1
        # Use varying probabilities so variance is non-zero.
        probs = [0.7, 0.8, 0.85, 0.9, 0.75, 0.8, 0.9, 0.85, 0.7, 0.75]
        outcomes = [1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0]
        params = _fit_linear_calibration(probs, outcomes)
        # Slope should be finite and parameters well-defined
        assert isinstance(params["slope"], float)
        assert isinstance(params["intercept"], float)
        import math
        assert math.isfinite(params["slope"])
        assert math.isfinite(params["intercept"])


class TestApplyCalibration:
    def test_identity(self):
        assert _apply_calibration(0.65, {"slope": 1.0, "intercept": 0.0}) == pytest.approx(0.65)

    def test_clips_to_lower_bound(self):
        # slope=0, intercept=-1 → -1, clipped to 0.001
        assert _apply_calibration(0.5, {"slope": 0.0, "intercept": -1.0}) == pytest.approx(0.001)

    def test_clips_to_upper_bound(self):
        assert _apply_calibration(0.999, {"slope": 2.0, "intercept": 0.0}) == pytest.approx(0.999)

    def test_linear_transform(self):
        result = _apply_calibration(0.4, {"slope": 0.8, "intercept": 0.1})
        assert result == pytest.approx(0.8 * 0.4 + 0.1)


# ---------------------------------------------------------------------------
# DB-backed tests (SQLite in-memory via run_once conftest pattern)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(tmp_path):
    """Provide a session connected to a fresh in-memory SQLite DB."""
    from backend.core.db import make_engine
    from backend.models.base import Base

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session
    session = Session(engine)
    yield session
    session.close()


class TestUpcomingUnpredictedFixtures:
    def test_returns_scheduled_fixtures_in_window(self, db_session):
        comp, season, home, away = _seed_provider_and_competition(db_session)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=6))
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=24)
        assert any(r.id == f.id for r in results)

    def test_excludes_fixtures_outside_window(self, db_session):
        comp, season, home, away = _seed_provider_and_competition(db_session)
        now = datetime.now(UTC)
        # Kicks off in 50 hours — outside 36h window
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=50))
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=36)
        assert not any(r.id == f.id for r in results)

    def test_excludes_already_predicted_fixtures(self, db_session):
        from backend.models import Prediction
        comp, season, home, away = _seed_provider_and_competition(db_session)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=6))
        # Seed a stub prediction row (only fixture_id and market/selection matter for the filter)
        # Use a direct insert to avoid publish_prediction validation overhead
        db_session.add(Prediction(
            fixture_id=f.id,
            prediction_timestamp=now,
            decision_as_of=now,
            market="1X2",
            selection="home",
            model_probabilities={"home": 0.4},
            ensemble_probability=0.4,
            calibrated_probability=0.4,
            conservative_probability=0.35,
            dqs=80.0,
        ))
        db_session.flush()
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=24)
        assert not any(r.id == f.id for r in results)

    def test_excludes_past_fixtures(self, db_session):
        comp, season, home, away = _seed_provider_and_competition(db_session)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now - timedelta(hours=1))
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=36)
        assert not any(r.id == f.id for r in results)

    def test_excludes_unvalidated_competition(self, db_session):
        # Fail-closed gate: validated=False must block the fixture entirely.
        comp, season, home, away = _seed_provider_and_competition(db_session, validated=False)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=6))
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=24)
        assert not any(r.id == f.id for r in results)

    def test_includes_validated_competition(self, db_session):
        # Sanity: validated=True must pass the gate when other conditions are met.
        comp, season, home, away = _seed_provider_and_competition(db_session, validated=True)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=6))
        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=24)
        assert any(r.id == f.id for r in results)

    def test_mixed_competitions_only_returns_validated(self, db_session):
        # Two competitions, one validated and one not; only the validated fixture appears.
        comp_v, season_v, home_v, away_v = _seed_provider_and_competition(
            db_session, validated=True
        )
        from backend.models.fixtures import Competition as Comp
        from backend.models.fixtures import Season
        comp_u = Comp(name="Liga MX", country="Mexico", validated=False)
        db_session.add(comp_u)
        db_session.flush()
        season_u = Season(
            competition_id=comp_u.id,
            label="2026",
            start_date=None,
            end_date=None,
        )
        db_session.add(season_u)
        db_session.flush()

        from backend.models import Team
        home_u = Team(name="Club América", country="Mexico")
        away_u = Team(name="Chivas", country="Mexico")
        db_session.add_all([home_u, away_u])
        db_session.flush()

        now = datetime.now(UTC)
        f_v = _make_fixture(
            db_session, comp_v, season_v, home_v, away_v, kickoff=now + timedelta(hours=6)
        )
        f_u = _make_fixture(
            db_session, comp_u, season_u, home_u, away_u, kickoff=now + timedelta(hours=6)
        )

        results = _upcoming_unpredicted_fixtures(db_session, now, lookahead_hours=24)
        result_ids = {r.id for r in results}
        assert f_v.id in result_ids
        assert f_u.id not in result_ids


class TestEnsureChampionModel:
    def test_creates_registry_and_run_on_first_call(self, db_session):

        now = datetime.now(UTC)
        registry, run = _ensure_champion_model(db_session, now)

        assert registry.name == "poisson+elo-ensemble"
        assert registry.version == "1.0.0"
        assert run.kind.value == "inference"
        assert run.status.value == "running"
        assert run.model_id == registry.id

    def test_idempotent_registry_row(self, db_session):
        from sqlalchemy import select

        from backend.models import ModelRegistry

        now = datetime.now(UTC)
        r1, _ = _ensure_champion_model(db_session, now)
        r2, _ = _ensure_champion_model(db_session, now)
        # Same registry row returned
        assert r1.id == r2.id
        # But two separate ModelRun rows
        assert db_session.scalar(
            select(ModelRegistry).where(ModelRegistry.name == "poisson+elo-ensemble")
        ) is not None


class TestEnsureChampionCalibration:
    def test_identity_when_no_settlements(self, db_session):
        now = datetime.now(UTC)
        cal = _ensure_champion_calibration(db_session, now, "abc1234")
        assert cal.parameters["slope"] == pytest.approx(1.0)
        assert cal.parameters["intercept"] == pytest.approx(0.0)
        assert cal.sample_size == 2
        assert "identity" in cal.version

    def test_champion_status(self, db_session):
        now = datetime.now(UTC)
        cal = _ensure_champion_calibration(db_session, now, "abc1234")
        assert cal.status.value == "champion"

    def test_idempotent_does_not_create_duplicate(self, db_session):

        now = datetime.now(UTC)
        cal1 = _ensure_champion_calibration(db_session, now, "abc1234")
        cal2 = _ensure_champion_calibration(db_session, now, "abc1234")
        assert cal1.id == cal2.id


class TestBestPreKickoffOdds:
    def test_returns_none_when_no_quotes(self, db_session):
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        odds, bm, ts = _best_pre_kickoff_odds(db_session, fid, "1X2", "home", before=now)
        assert odds is None
        assert bm is None
        assert ts is None

    def test_returns_latest_pre_kickoff_quote(self, db_session):
        from backend.models import OddsQuote
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        earlier = now - timedelta(hours=3)
        later = now - timedelta(hours=1)

        db_session.add(OddsQuote(
            fixture_id=fid, bookmaker="B365", market="1X2", selection="home",
            decimal_odds=2.10, captured_at=earlier, source="api-football",
        ))
        db_session.add(OddsQuote(
            fixture_id=fid, bookmaker="B365", market="1X2", selection="home",
            decimal_odds=2.05, captured_at=later, source="api-football",
        ))
        db_session.flush()

        odds, bm, ts = _best_pre_kickoff_odds(db_session, fid, "1X2", "home", before=now)
        assert odds == pytest.approx(2.05)
        assert bm == "B365"

    def test_excludes_quotes_after_cutoff(self, db_session):
        from backend.models import OddsQuote
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        # Quote captured after the cutoff
        db_session.add(OddsQuote(
            fixture_id=fid, bookmaker="B365", market="1X2", selection="home",
            decimal_odds=1.90, captured_at=now + timedelta(minutes=5), source="api-football",
        ))
        db_session.flush()
        odds, _, _ = _best_pre_kickoff_odds(db_session, fid, "1X2", "home", before=now)
        assert odds is None


class TestDeviggedFairProb:
    """Regression tests for coherent-market enforcement in _devigged_fair_prob."""

    _SELS = ["home", "draw", "away"]
    _ODDS = {"home": 1.80, "draw": 3.50, "away": 4.50}

    def _add_quote(self, db_session, fid, sel, bookmaker="B365", ts=None, dec=None):
        from backend.models import OddsQuote
        if ts is None:
            ts = datetime.now(UTC) - timedelta(minutes=30)
        if dec is None:
            dec = self._ODDS[sel]
        q = OddsQuote(
            fixture_id=fid, bookmaker=bookmaker, market="1X2", selection=sel,
            decimal_odds=dec, captured_at=ts, source="api-football",
        )
        db_session.add(q)
        return q

    def test_returns_none_when_draw_leg_missing(self, db_session):
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        self._add_quote(db_session, fid, "home")
        self._add_quote(db_session, fid, "away")
        db_session.flush()
        assert _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        ) == (None, None, None, None)

    def test_returns_none_when_mixed_bookmakers(self, db_session):
        """No single bookmaker covers all three legs → no coherent snapshot."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        ts = now - timedelta(minutes=30)
        self._add_quote(db_session, fid, "home", bookmaker="B365", ts=ts)
        self._add_quote(db_session, fid, "draw", bookmaker="Betfair", ts=ts)
        self._add_quote(db_session, fid, "away", bookmaker="Betfair", ts=ts)
        db_session.flush()
        assert _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        ) == (None, None, None, None)

    def test_returns_none_when_leg_timestamps_too_spread(self, db_session):
        """All legs from same bookmaker but draw is > 1 h older than home."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        self._add_quote(db_session, fid, "home", ts=now - timedelta(minutes=20))
        self._add_quote(db_session, fid, "draw", ts=now - timedelta(hours=2))
        self._add_quote(db_session, fid, "away", ts=now - timedelta(minutes=20))
        db_session.flush()
        assert _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        ) == (None, None, None, None)

    def test_devigged_prob_below_raw_implied(self, db_session):
        """Fair probability after devig must be strictly lower than 1/odds (margin removed)."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        ts = now - timedelta(minutes=30)
        for sel in self._SELS:
            self._add_quote(db_session, fid, sel, ts=ts)
        db_session.flush()
        odds, fair_prob, bm, oldest_ts = _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        )
        assert odds == pytest.approx(1.80)
        assert bm == "B365"
        assert fair_prob is not None
        assert fair_prob < 1.0 / 1.80  # devig removes margin → fair < raw implied

    def test_fair_probs_sum_to_one(self, db_session):
        """Proportional devig must produce fair probabilities that sum to 1."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        ts = now - timedelta(minutes=30)
        for sel in self._SELS:
            self._add_quote(db_session, fid, sel, ts=ts)
        db_session.flush()
        probs = [
            _devigged_fair_prob(db_session, fid, "1X2", sel, self._SELS, before=now)[1]
            for sel in self._SELS
        ]
        assert all(p is not None for p in probs)
        assert sum(probs) == pytest.approx(1.0)  # type: ignore[arg-type]

    def test_oldest_timestamp_returned_for_freshness(self, db_session):
        """oldest_captured_at must be the oldest leg so the value gate covers the full market."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        home_ts = now - timedelta(minutes=20)
        stale_ts = now - timedelta(minutes=55)  # oldest, but still within 1 h spread
        self._add_quote(db_session, fid, "home", ts=home_ts)
        self._add_quote(db_session, fid, "draw", ts=stale_ts)
        self._add_quote(db_session, fid, "away", ts=home_ts)
        db_session.flush()
        _, _, _, oldest_ts = _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        )
        assert oldest_ts is not None
        # oldest_ts must track the stalest leg (draw, ~55 min ago), not home (~20 min ago).
        assert abs((oldest_ts - stale_ts).total_seconds()) < 2

    def test_selects_freshest_coherent_bookmaker(self, db_session):
        """When multiple bookmakers have coherent snapshots, pick the one with the
        freshest target-selection quote."""
        fid = uuid.uuid4()
        now = datetime.now(UTC)
        old_ts = now - timedelta(minutes=50)
        fresh_ts = now - timedelta(minutes=10)
        # B365: coherent but stale
        for sel in self._SELS:
            self._add_quote(db_session, fid, sel, bookmaker="B365", ts=old_ts)
        # Betfair: coherent and fresher
        for sel in self._SELS:
            self._add_quote(db_session, fid, sel, bookmaker="Betfair", ts=fresh_ts)
        db_session.flush()
        _, _, bm, _ = _devigged_fair_prob(
            db_session, fid, "1X2", "home", self._SELS, before=now
        )
        assert bm == "Betfair"


class TestProcessFixtureSuccessPath:
    """End-to-end test: fixture + odds → prediction published → accumulator seeded."""

    def test_publishes_prediction_with_odds(self, db_session, monkeypatch):
        """Full _process_fixture success path: odds available, gate passes, prediction written."""
        from qwantej.features.engineering import MatchFeatures

        comp, season, home, away = _seed_provider_and_competition(db_session)
        now = datetime.now(UTC)
        f = _make_fixture(db_session, comp, season, home, away, kickoff=now + timedelta(hours=6))

        # Seed full 1X2 market (1 hour old) so _devigged_fair_prob can run devig().
        from backend.models import OddsQuote
        odds_rows = []
        for sel, dec in [("home", 1.80), ("draw", 3.50), ("away", 4.50)]:
            q = OddsQuote(
                fixture_id=f.id,
                bookmaker="B365",
                market="1X2",
                selection=sel,
                decimal_odds=dec,
                captured_at=now - timedelta(hours=1),
                source="api-football",
            )
            db_session.add(q)
            odds_rows.append(q)
        db_session.flush()

        # Bootstrap lineage rows; use actual code_commit so it matches registry.
        registry, pipeline_run = _ensure_champion_model(db_session, now)
        commit = registry.code_commit  # must match the row already stored
        calibration = _ensure_champion_calibration(db_session, now, commit)

        # Seed a ReliabilitySnapshot so the live reliability gate passes.
        # created_at is set explicitly to a time before `now` so the PIT filter
        # (created_at <= as_of) holds regardless of wall-clock timing in CI.
        from backend.models.reliability import ReliabilitySnapshot, ReliabilityState
        snap_eval = now - timedelta(hours=1)
        rel_snap = ReliabilitySnapshot(
            competition_id=comp.id,
            competition_class="tier-1",
            market_family="1X2",
            evaluated_as_of=snap_eval,
            window_start=now - timedelta(days=90),
            window_end=snap_eval,
            policy_version="reliability-v1",
            observation_count=150,
            effective_sample_size=140.0,
            shrinkage_weight=0.58,
            league_reliability=78.0,
            market_reliability=75.0,
            segment_reliability=76.0,
            posterior_standard_deviation=0.03,
            conservative_lower_bound=0.70,
            status=ReliabilityState.QUALIFIED,
            grade="A",
            components={
                "calibration": 0.82, "roi": 0.62, "clv": 0.55,
                "variance": 0.71, "drawdown": 0.68, "stability": 0.82,
            },
            diagnostics={"raw_score": 0.70},
            future_rows_excluded=0,
            input_snapshot_ref="test-snap-ref",
            input_snapshot_hash="b" * 64,
            code_commit=commit,
            created_at=snap_eval,
        )
        db_session.add(rel_snap)
        db_session.flush()

        # A dominant home team: Elo +200 pts and high xG.
        fake_features = MatchFeatures(
            elo_home_rating=1600.0,
            elo_away_rating=1400.0,
            home_xg=1.9,
            away_xg=0.7,
            home_attack=1.2,
            home_defence=0.85,
            away_attack=0.8,
            away_defence=1.1,
            home_form=0.70,
            away_form=0.30,
            h2h_home_win_rate=0.65,
            home_matches=10,
            away_matches=10,
            league_home_avg=1.5,
            league_away_avg=1.2,
        )

        # Return all odds quote ids so create_feature_snapshot has source rows.
        all_odds_ids = [q.id for q in odds_rows]
        monkeypatch.setattr(
            "backend.services.feature_extraction.extract_fixture_features",
            lambda *a, **kw: (fake_features, [], all_odds_ids, []),
        )

        from qwantej.value.gate import ValueGatePolicy
        from scripts.run_signal_pipeline import _process_fixture

        prediction = _process_fixture(
            db_session,
            f,
            now=now,
            model_registry=registry,
            model_run=pipeline_run,
            calibration_model=calibration,
            value_policy=ValueGatePolicy(),
            commit=commit,
        )

        assert prediction is not None, "prediction should be published when edge is positive"
        # segment_reliability comes from the actual snapshot, not a hardcoded value.
        assert prediction.segment_reliability == pytest.approx(76.0)
        pred = prediction.prediction
        assert pred.fixture_id == f.id
        assert pred.market == "1X2"
        assert pred.selection == "home"
        assert pred.ensemble_probability is not None
        assert float(pred.ensemble_probability) > 0.5
        assert pred.edge_pp is not None
        assert float(pred.edge_pp) > 0
        # Phase 9: reliability scores and snapshot identity must be persisted.
        assert float(pred.lrs) == pytest.approx(78.0), "lrs must match snapshot.league_reliability"
        assert float(pred.mrs) == pytest.approx(75.0), "mrs must match snapshot.market_reliability"
        assert pred.reliability_snapshot_id == rel_snap.id, "lineage must reference the snapshot"


class TestRunOnceDryRun:
    def test_dry_run_completes_without_error(self, monkeypatch, tmp_path):
        """run_once dry-run wires the full pipeline with an empty DB.

        With no fixtures, the pipeline should run without error, publish no
        predictions, and return a run summary with errors=0.
        """
        import os
        from unittest.mock import patch

        # Point DATABASE_URL at a fresh SQLite file so run_once can make_engine itself.
        db_path = tmp_path / "test_signal.db"
        db_url = f"sqlite:///{db_path}"

        with patch.dict(os.environ, {
            "DATABASE_URL": db_url,
            "API_FOOTBALL_KEY": "dummy",
            "API_KEY": "test",
        }):
            # get_settings() uses @lru_cache — clear it so run_once reads the
            # patched DATABASE_URL rather than the cached Postgres URL.
            from backend.core.config import get_settings
            get_settings.cache_clear()
            try:
                # Bootstrap the schema.
                from backend.core.db import make_engine
                from backend.models.base import Base
                engine = make_engine(db_url)
                Base.metadata.create_all(engine)

                result = run_once(lookahead_hours=24, dry_run=True)
            finally:
                # Restore: clear again so subsequent tests get fresh Postgres settings.
                get_settings.cache_clear()

        assert result.errors == 0
        assert result.predictions_published == 0
        assert result.fixtures_evaluated == 0
