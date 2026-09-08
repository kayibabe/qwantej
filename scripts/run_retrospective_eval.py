"""Retrospective calibration evaluator — research use only.

Ingests a full league-season from API-Football (results only; odds are skipped
to save quota), builds features for every finished fixture using canonical
mutable fixture state, runs a calibration-only walk-forward, and records the
experiment in the database.

**Not PIT-certified.** Features are derived from canonical mutable fixture rows,
not from immutable provider snapshots captured before each simulated decision
cutoff.  Calibration metrics from this script are research diagnostics, not
evidence of production readiness.

Usage:
    python scripts/run_retrospective_eval.py \\
        [--league 39] [--season 2025] \\
        [--train-from 2025-08-01] [--train-to 2026-01-31] \\
        [--test-from 2026-02-01] [--test-to 2026-05-31] \\
        [--n-recent 30] [--skip-ingest] [--dry-run]

Pass --skip-ingest when the season is already in the database.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
log = logging.getLogger("retrospective_eval")


def _ingest_season(client, session, args) -> None:
    from backend.services.api_football_ingestion import ingest_walk_forward_window

    train_from = date.fromisoformat(args.train_from)
    test_to = date.fromisoformat(args.test_to)
    captured_at = datetime.now(UTC)
    log.info(
        "Ingesting league=%d season=%d %s→%s (odds skipped)",
        args.league, args.season, train_from, test_to,
    )
    summary = ingest_walk_forward_window(
        session,
        client,
        league_id=args.league,
        season=args.season,
        start_date=train_from,
        end_date=test_to,
        captured_at=captured_at,
        include_odds=False,
    )
    log.info(
        "  fixtures +%d ~%d  snapshots=%d",
        summary.fixtures_created,
        summary.fixtures_updated,
        summary.fixture_snapshots_created,
    )


def _build_observations(session, args) -> list:
    from sqlalchemy import and_, or_, select

    from backend.models import EntityType, Fixture, FixtureStatus, Provider, Season, SourceMapping
    from backend.services.retrospective_extraction import (
        RetrospectiveResult,
        extract_retrospective_features,
    )
    from qwantej.models.elo.model import result_probabilities as elo_probs
    from qwantej.models.poisson.model import poisson_scoreline
    from qwantej.performance.calibration_backtest import CalibrationObservationRow

    train_from_utc = datetime.combine(
        date.fromisoformat(args.train_from), datetime.min.time(), tzinfo=UTC
    )
    test_to_utc = datetime.combine(
        date.fromisoformat(args.test_to), datetime.max.time(), tzinfo=UTC
    )
    test_from_utc = datetime.combine(
        date.fromisoformat(args.test_from), datetime.min.time(), tzinfo=UTC
    )
    train_to_utc = datetime.combine(
        date.fromisoformat(args.train_to), datetime.max.time(), tzinfo=UTC
    )

    provider_id = session.scalar(
        select(Provider.id).where(Provider.name == "API-Football")
    )
    if provider_id is None:
        log.warning("No API-Football provider row — has any data been ingested?")
        return []

    competition_id = session.scalar(
        select(SourceMapping.canonical_id).where(
            SourceMapping.provider_id == provider_id,
            SourceMapping.entity_type == EntityType.COMPETITION,
            SourceMapping.external_id == str(args.league),
        )
    )
    if competition_id is None:
        log.warning("No competition mapping for league=%d", args.league)
        return []

    season_id = session.scalar(
        select(Season.id).where(
            Season.competition_id == competition_id,
            Season.label == str(args.season),
        )
    )
    if season_id is None:
        log.warning("No season row for league=%d season=%d", args.league, args.season)
        return []

    finished = session.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == competition_id,
            Fixture.season_id == season_id,
            Fixture.status == FixtureStatus.FINISHED,
            Fixture.home_goals.is_not(None),
            Fixture.away_goals.is_not(None),
            or_(
                and_(
                    Fixture.kickoff_utc >= train_from_utc,
                    Fixture.kickoff_utc <= train_to_utc,
                ),
                and_(
                    Fixture.kickoff_utc >= test_from_utc,
                    Fixture.kickoff_utc <= test_to_utc,
                ),
            ),
        )
        .order_by(Fixture.kickoff_utc)
    ).all()

    log.info("Found %d finished fixtures in train+test window", len(finished))

    observations: list[CalibrationObservationRow] = []
    all_training_results: list[RetrospectiveResult] = []
    skipped = 0

    for fixture in finished:
        kickoff = fixture.kickoff_utc
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        as_of = kickoff - timedelta(hours=2)

        try:
            features, hist_rows = extract_retrospective_features(
                session, fixture, n_recent=args.n_recent
            )
        except Exception as exc:
            log.debug("skip fixture %s: %s", fixture.id, exc)
            skipped += 1
            continue

        if features.home_matches < 3 or features.away_matches < 3:
            skipped += 1
            continue

        dist = poisson_scoreline(features.home_xg, features.away_xg)
        poisson_result = dist.match_result()
        model_home = float(poisson_result.home)
        model_draw = float(poisson_result.draw)
        model_away = float(poisson_result.away)

        elo_result = elo_probs(features.elo_home_rating, features.elo_away_rating)
        elo_home = float(elo_result.home)

        ensemble_home = (model_home + elo_home) / 2.0

        outcome = int(fixture.home_goals > fixture.away_goals)
        outcome_observed_at = kickoff + timedelta(hours=2)

        observations.append(
            CalibrationObservationRow(
                observation_id=str(fixture.id),
                decision_as_of=as_of,
                feature_as_of=as_of,
                outcome_observed_at=outcome_observed_at,
                model_version="poisson+elo-ensemble:1.0.0",
                raw_probability=ensemble_home,
                outcome=outcome,
                model_probabilities=(model_home, model_draw, model_away),
            )
        )
        all_training_results.extend(hist_rows)

    log.info("Built %d observations (%d skipped)", len(observations), skipped)
    return observations, all_training_results


def _run_calibration_backtest(observations, args):
    from qwantej.calibration import CalibrationMethod
    from qwantej.performance.calibration_backtest import (
        CalibrationOnlyConfig,
        calibration_only_walk_forward,
    )

    test_from_utc = datetime.combine(
        date.fromisoformat(args.test_from), datetime.min.time(), tzinfo=UTC
    )
    train_rows = [o for o in observations if o.decision_as_of < test_from_utc]
    test_rows = [o for o in observations if o.decision_as_of >= test_from_utc]

    min_train = max(2, len(train_rows))
    if len(train_rows) < 2:
        raise ValueError(
            f"only {len(train_rows)} training observations; "
            "increase --train-from/--train-to range or use more fixtures"
        )
    if not test_rows:
        raise ValueError("no test observations; check --test-from/--test-to range")

    config = CalibrationOnlyConfig(
        version="retrospective-eval:1.0.0",
        model_version="poisson+elo-ensemble:1.0.0",
        calibration_method=CalibrationMethod.ISOTONIC,
        minimum_training_size=min_train,
        test_window_size=max(1, len(test_rows)),
    )
    return calibration_only_walk_forward(observations, config), config


def _record_experiment(session, report, config, all_training_results, args, started_at) -> None:
    from backend.services.experiments import (
        ExperimentIdentity,
        complete_research_experiment,
        start_research_experiment,
    )
    from backend.services.retrospective_extraction import retrospective_fixture_hash

    try:
        import subprocess
        code_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(repo_root), text=True
        ).strip()
    except Exception:
        code_commit = "unknown"

    fixture_hash = retrospective_fixture_hash(all_training_results)
    data_snapshot_ref = (
        f"retrospective:league={args.league}:season={args.season}"
        f":n_recent={args.n_recent}:{fixture_hash[:16]}"
    )
    train_from_utc = datetime.combine(
        date.fromisoformat(args.train_from), datetime.min.time(), tzinfo=UTC
    )
    train_to_utc = datetime.combine(
        date.fromisoformat(args.train_to), datetime.max.time(), tzinfo=UTC
    )
    test_from_utc = datetime.combine(
        date.fromisoformat(args.test_from), datetime.min.time(), tzinfo=UTC
    )
    test_to_utc = datetime.combine(
        date.fromisoformat(args.test_to), datetime.max.time(), tzinfo=UTC
    )

    identity = ExperimentIdentity(
        name=args.name,
        version="1.0.0",
        calibration_version="isotonic:1.0.0",
        code_commit=code_commit,
        data_snapshot_ref=data_snapshot_ref,
        training_window_start=train_from_utc,
        training_window_end=train_to_utc,
        test_window_start=test_from_utc,
        test_window_end=test_to_utc,
    )
    experiment = start_research_experiment(
        session, identity=identity, config=config, started_at=started_at
    )
    complete_research_experiment(
        session, experiment, report, finished_at=datetime.now(UTC)
    )
    log.info("Research experiment recorded: id=%s name=%s", experiment.id, args.name)


def _print_report(report) -> None:
    log.info("=== Retrospective calibration results (research only) ===")
    log.info("  sample_size:                %d", report.sample_size)
    log.info("  temporal_order_rejections:  %d", report.temporal_order_rejections)
    log.info("  model_version_rejected:     %d", report.model_version_rows_rejected)
    log.info("  pit_certified:              %s", report.pit_certified)
    cal = report.calibrated_calibration
    raw = report.raw_calibration
    log.info("  raw      brier=%.4f  ece=%.4f", raw.brier_score, raw.expected_calibration_error)
    log.info("  calibrated brier=%.4f  ece=%.4f", cal.brier_score, cal.expected_calibration_error)
    for i, fold in enumerate(report.folds, 1):
        log.info(
            "  fold %2d  train=%d  test=%d  raw_brier=%.4f  cal_brier=%.4f",
            i, fold.training_sample_size, fold.evaluated_rows,
            fold.raw_brier, fold.calibrated_brier,
        )


def parse_args() -> argparse.Namespace:
    today = date.today()
    prev_year = today.year - 1
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--league", type=int, default=39, metavar="ID")
    parser.add_argument("--season", type=int, default=prev_year, metavar="YEAR")
    parser.add_argument("--name", default="retrospective-poisson-elo")
    parser.add_argument(
        "--train-from", default=f"{prev_year}-08-01", metavar="YYYY-MM-DD"
    )
    parser.add_argument(
        "--train-to", default=f"{prev_year}-12-31", metavar="YYYY-MM-DD"
    )
    parser.add_argument(
        "--test-from", default=f"{today.year}-01-01", metavar="YYYY-MM-DD"
    )
    parser.add_argument(
        "--test-to", default=f"{today.year}-05-31", metavar="YYYY-MM-DD"
    )
    parser.add_argument("--n-recent", type=int, default=30, metavar="N")
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip API-Football ingestion (use data already in DB)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Roll back after the run — no rows persisted",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope

    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL must point at Postgres — update your .env file")
        sys.exit(1)

    engine = make_engine(settings.database_url)
    started_at = datetime.now(UTC)

    with session_scope(engine) as session:
        if not args.skip_ingest:
            if not settings.api_football_key.strip():
                log.error("API_FOOTBALL_KEY not set — add it to .env or pass --skip-ingest")
                sys.exit(1)
            from backend.services.api_football_client import ApiFootballClient
            client = ApiFootballClient.from_settings(settings)
            _ingest_season(client, session, args)

        result = _build_observations(session, args)
        if not result or not result[0]:
            log.warning("No observations built — cannot run backtest")
            sys.exit(0)
        observations, all_training_results = result

        try:
            report, config = _run_calibration_backtest(observations, args)
        except ValueError as exc:
            log.error("Backtest failed: %s", exc)
            sys.exit(1)

        _print_report(report)

        if not args.dry_run:
            _record_experiment(
                session, report, config, all_training_results, args, started_at
            )
        else:
            session.rollback()
            log.info("Dry-run: experiment NOT recorded in DB")

    log.info("Retrospective evaluation complete.")


if __name__ == "__main__":
    main()
