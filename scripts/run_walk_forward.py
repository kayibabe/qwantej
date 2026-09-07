"""End-to-end walk-forward experiment: ingest → extract features → model → backtest.

Ingests a full league-season from API-Football, builds point-in-time feature
snapshots for each finished fixture in the test window, runs the Poisson model,
applies the configured calibration and value gate, and records the experiment
and its metrics in the database.

Usage:
    python scripts/run_walk_forward.py \\
        [--league 39] [--season 2025] \\
        [--train-from 2025-08-01] [--train-to 2026-01-31] \\
        [--test-from 2026-02-01] [--test-to 2026-05-31] \\
        [--n-recent 30] [--dry-run]

The script never reads the training window's test fixtures during fitting —
all calibration is trained on the train window only (framework §41).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("walk_forward")


@dataclass
class ExperimentConfig:
    league_id: int
    season: int
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    n_recent: int
    dry_run: bool
    name: str


def _ingest_season(client: Any, session: Any, cfg: ExperimentConfig) -> None:
    from backend.services.api_football_ingestion import (
        ingest_odds,
        ingest_walk_forward_window,
    )

    captured_at = datetime.now(UTC)
    log.info("Ingesting fixtures for league=%d season=%d ...", cfg.league_id, cfg.season)
    summary = ingest_walk_forward_window(
        session,
        client,
        league_id=cfg.league_id,
        season=cfg.season,
        start_date=cfg.train_from,
        end_date=cfg.test_to,
        captured_at=captured_at,
    )
    log.info(
        "  fixtures +%d/~%d snapshots=%d",
        summary.fixtures_created, summary.fixtures_updated,
        summary.fixture_snapshots_created,
    )

    log.info("Ingesting odds for league=%d season=%d ...", cfg.league_id, cfg.season)
    odds_payloads = client.odds(league=cfg.league_id, season=cfg.season)
    odds_summary = ingest_odds(session, odds_payloads)
    log.info(
        "  odds +%d (deduped=%d unsupported=%d)",
        odds_summary.odds_quotes_created,
        odds_summary.odds_quotes_deduplicated,
        odds_summary.odds_quotes_unsupported,
    )


def _build_backtest_observations(session: Any, cfg: ExperimentConfig) -> list[Any]:
    """Build BacktestObservation list for finished fixtures in the test window."""

    from sqlalchemy import select

    from backend.models import Fixture, FixtureStatus
    from backend.services.feature_extraction import extract_fixture_features
    from qwantej.markets.devig import devig_multiplicative
    from qwantej.models.elo.model import result_probabilities as elo_probs
    from qwantej.models.poisson.model import poisson_scoreline
    from qwantej.performance.backtest import BacktestObservation

    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    test_to_utc = datetime.combine(cfg.test_to, datetime.max.time(), tzinfo=UTC)

    finished_test_fixtures = session.scalars(
        select(Fixture)
        .where(
            Fixture.status == FixtureStatus.FINISHED,
            Fixture.kickoff_utc >= test_from_utc,
            Fixture.kickoff_utc <= test_to_utc,
            Fixture.home_goals.is_not(None),
            Fixture.away_goals.is_not(None),
        )
        .order_by(Fixture.kickoff_utc)
    ).all()

    log.info("Found %d finished fixtures in test window", len(finished_test_fixtures))
    observations: list[BacktestObservation] = []
    skipped = 0

    for fixture in finished_test_fixtures:
        kickoff = fixture.kickoff_utc
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        as_of = kickoff - timedelta(hours=2)  # simulate 2h pre-match decision

        try:
            features, _stats_ids, odds_ids = extract_fixture_features(
                session, fixture, as_of=as_of, n_recent=cfg.n_recent
            )
        except Exception as exc:
            log.debug("skip fixture %s: %s", fixture.id, exc)
            skipped += 1
            continue

        if features.home_matches < 3 or features.away_matches < 3:
            skipped += 1
            continue

        # Poisson model — home win probability (1X2)
        dist = poisson_scoreline(features.home_xg, features.away_xg)
        model_home_win = float(dist.p_home_win())
        model_draw = float(dist.p_draw())
        model_away_win = float(dist.p_away_win())

        # ELO model for ensemble blend
        elo_result = elo_probs(features.elo_home_rating, features.elo_away_rating)
        elo_home_win = float(elo_result.home)

        # Simple ensemble: average Poisson + ELO for home win
        ensemble_home_win = (model_home_win + elo_home_win) / 2.0

        # Best market odds (1X2 home, if available)
        executable_odds: float | None = None
        fair_market_prob: float | None = None
        best_odds_row = _best_odds(session, fixture.id, market="1X2", selection="home")
        if best_odds_row is not None:
            raw_home = float(best_odds_row.decimal_odds)
            executable_odds = raw_home
            # de-vig against best available draw and away for a 3-way market
            away_row = _best_odds(session, fixture.id, market="1X2", selection="away")
            draw_row = _best_odds(session, fixture.id, market="1X2", selection="draw")
            if away_row and draw_row:
                try:
                    devigged = devig_multiplicative(
                        {
                            "home": 1.0 / float(best_odds_row.decimal_odds),
                            "draw": 1.0 / float(draw_row.decimal_odds),
                            "away": 1.0 / float(away_row.decimal_odds),
                        }
                    )
                    fair_market_prob = devigged["home"]
                except Exception:
                    pass

        outcome: int | None = None
        outcome_observed_at: datetime | None = None
        if fixture.home_goals is not None and fixture.away_goals is not None:
            outcome = 1 if fixture.home_goals > fixture.away_goals else 0
            outcome_observed_at = kickoff + timedelta(hours=2)  # approx FT

        obs = BacktestObservation(
            observation_id=str(fixture.id),
            decision_as_of=as_of,
            feature_as_of=as_of,
            outcome_observed_at=outcome_observed_at,
            model_version="poisson+elo-ensemble:1.0.0",
            raw_probability=ensemble_home_win,
            outcome=outcome,
            fair_market_probability=fair_market_prob,
            executable_odds=executable_odds,
            quote_timestamp=best_odds_row.captured_at if best_odds_row else None,
            model_probabilities=(model_home_win, model_draw, model_away_win),
        )
        observations.append(obs)

    log.info("Built %d observations (%d skipped)", len(observations), skipped)
    return observations


def _best_odds(session: Any, fixture_id: Any, *, market: str, selection: str) -> Any:
    """Return the highest decimal-odds row for a market/selection."""
    from sqlalchemy import select

    from backend.models import OddsQuote

    return session.scalar(
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.market == market,
            OddsQuote.selection == selection,
        )
        .order_by(OddsQuote.decimal_odds.desc())
        .limit(1)
    )


def _run_backtest(
    observations: list[Any], cfg: ExperimentConfig
) -> Any:
    """Fit calibrator on train-set subset and evaluate on all observations."""

    from qwantej.calibration import CalibrationMethod, CalibrationObservation, fit_calibrator
    from qwantej.performance.backtest import (
        WalkForwardConfig,
        run_walk_forward,
    )
    from qwantej.value import ValueGatePolicy

    train_to_utc = datetime.combine(cfg.train_to, datetime.min.time(), tzinfo=UTC)

    # Calibration training: use only observations from before the test window
    # (Here we don't have separate train obs as they'd come from a prior season run,
    # so we fit on the same dataset as a research baseline. In production this would
    # use archived predictions from the training window.)
    train_obs = [o for o in observations if o.decision_as_of < train_to_utc]
    calib_obs = [
        CalibrationObservation(predicted=o.raw_probability, actual=float(o.outcome))
        for o in train_obs
        if o.outcome is not None
    ]

    calibration_method = CalibrationMethod.ISOTONIC
    if len(calib_obs) >= 10:
        calibrator = fit_calibrator(calib_obs, method=calibration_method)
    else:
        calibrator = None
        log.warning(
            "Insufficient calibration data (%d obs); using raw probabilities",
            len(calib_obs),
        )

    wf_config = WalkForwardConfig(
        model_version="poisson+elo-ensemble:1.0.0",
        calibration_method=calibration_method,
        calibrator=calibrator,
        value_policy=ValueGatePolicy(),
        conservative_policy=None,
        train_window_months=6,
        test_window_months=1,
        min_observations=10,
        bootstrap_iterations=500,
        bootstrap_seed=42,
    )

    report = run_walk_forward(observations, config=wf_config)
    return report, wf_config


def _record_experiment(
    session: Any, report: Any, cfg: ExperimentConfig, started_at: datetime
) -> None:
    import subprocess

    from backend.services.experiments import (
        ExperimentIdentity,
        complete_walk_forward_experiment,
        start_walk_forward_experiment,
    )

    try:
        code_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except Exception:
        code_commit = "unknown"

    train_from_utc = datetime.combine(cfg.train_from, datetime.min.time(), tzinfo=UTC)
    train_to_utc = datetime.combine(cfg.train_to, datetime.max.time(), tzinfo=UTC)
    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    test_to_utc = datetime.combine(cfg.test_to, datetime.max.time(), tzinfo=UTC)

    identity = ExperimentIdentity(
        name=cfg.name,
        version="1.0.0",
        calibration_version="isotonic:1.0.0",
        code_commit=code_commit,
        data_snapshot_ref=f"api-football:league={cfg.league_id}:season={cfg.season}",
        training_window_start=train_from_utc,
        training_window_end=train_to_utc,
        test_window_start=test_from_utc,
        test_window_end=test_to_utc,
    )

    _, wf_config = report
    actual_report = report[0]
    experiment = start_walk_forward_experiment(
        session,
        identity=identity,
        config=wf_config,
        started_at=started_at,
    )
    complete_walk_forward_experiment(
        session,
        experiment,
        actual_report,
        finished_at=datetime.now(UTC),
    )
    log.info("Experiment recorded: id=%s name=%s", experiment.id, cfg.name)


def _print_report(report: Any) -> None:
    log.info("=== Walk-forward results ===")
    log.info("  sample_size:          %d", report.sample_size)
    log.info("  leakage_rejected:     %d", report.leakage_rows_rejected)
    if hasattr(report, "roi") and report.roi is not None:
        log.info("  ROI:                  %.2f%%", report.roi * 100)
    if hasattr(report, "hit_rate") and report.hit_rate is not None:
        log.info("  hit_rate:             %.2f%%", report.hit_rate * 100)
    if hasattr(report, "calibration") and report.calibration is not None:
        log.info("  brier_score:          %.4f", report.calibration.brier_score)
        log.info("  ece:                  %.4f", report.calibration.ece)


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--league", type=int, default=39, metavar="ID")
    parser.add_argument("--season", type=int, default=today.year - 1, metavar="YEAR")
    parser.add_argument("--name", default="baseline-poisson-elo")
    parser.add_argument(
        "--train-from", type=date.fromisoformat,
        default=date(today.year - 1, 8, 1), metavar="YYYY-MM-DD",
    )
    parser.add_argument(
        "--train-to", type=date.fromisoformat,
        default=date(today.year - 1, 12, 31), metavar="YYYY-MM-DD",
    )
    parser.add_argument(
        "--test-from", type=date.fromisoformat,
        default=date(today.year, 1, 1), metavar="YYYY-MM-DD",
    )
    parser.add_argument(
        "--test-to", type=date.fromisoformat,
        default=date(today.year, 5, 31), metavar="YYYY-MM-DD",
    )
    parser.add_argument("--n-recent", type=int, default=30, metavar="N")
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip API-Football ingestion (use data already in DB)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Roll back after experiment — no DB rows persisted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = ExperimentConfig(
        league_id=args.league,
        season=args.season,
        name=args.name,
        train_from=args.train_from,
        train_to=args.train_to,
        test_from=args.test_from,
        test_to=args.test_to,
        n_recent=args.n_recent,
        dry_run=args.dry_run,
    )

    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.services.api_football_client import ApiFootballClient

    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL must point at Postgres — update your .env file")
        sys.exit(1)

    engine = make_engine(settings.database_url)

    started_at = datetime.now(UTC)

    # Phase 1: ingestion (committed independently)
    if not args.skip_ingest:
        if not settings.api_football_key.strip():
            log.error("API_FOOTBALL_KEY is not set")
            sys.exit(1)
        client = ApiFootballClient.from_settings(settings)
        with session_scope(engine) as session:
            _ingest_season(client, session, cfg)

    # Phase 2: feature extraction + backtest + record experiment
    with session_scope(engine) as session:
        observations = _build_backtest_observations(session, cfg)
        if not observations:
            log.warning("No observations built — cannot run backtest")
            sys.exit(0)

        report, wf_config = _run_backtest(observations, cfg)
        _print_report(report)

        if not cfg.dry_run:
            _record_experiment(session, (report, wf_config), cfg, started_at)
        else:
            log.info("Dry-run: experiment NOT recorded in DB")

    log.info("Walk-forward experiment complete.")


if __name__ == "__main__":
    main()
