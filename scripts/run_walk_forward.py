"""End-to-end walk-forward experiment: ingest -> extract features -> model -> backtest.

Ingests a full league-season from API-Football, builds point-in-time feature
snapshots for each finished fixture in the train and test windows, runs the Poisson model,
applies the configured calibration and value gate, and records the experiment
and its metrics in the database.

Usage:
    python scripts/run_walk_forward.py \\
        [--league 39] [--season 2025] \\
        [--train-from 2025-08-01] [--train-to 2026-01-31] \\
        [--test-from 2026-02-01] [--test-to 2026-05-31] \\
        [--n-recent 30] [--dry-run]

The script never reads the test window's outcomes during fitting - all
calibration is trained on the train window only (framework section 41).
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
    calibration_only: bool = False
    all_leagues: bool = False


def _ingest_season(client: Any, session: Any, cfg: ExperimentConfig) -> None:
    from backend.services.api_football_ingestion import ingest_walk_forward_window

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
        "  fixtures +%d/~%d snapshots=%d odds +%d (deduped=%d unsupported=%d)",
        summary.fixtures_created, summary.fixtures_updated,
        summary.fixture_snapshots_created,
        summary.odds_quotes_created,
        summary.odds_quotes_deduplicated,
        summary.odds_quotes_unsupported,
    )


def _build_backtest_observations(session: Any, cfg: ExperimentConfig) -> list[Any]:  # noqa: C901
    """Build snapshots and observations for the requested train+test window."""

    from sqlalchemy import and_, or_, select

    from backend.models import Fixture, FixtureStatus
    from backend.services.feature_extraction import (
        extract_fixture_features,
        historical_training_hash,
    )
    from backend.services.features import create_feature_snapshot
    from qwantej.features.engineering import features_to_dict
    from qwantej.markets.devig import devig
    from qwantej.models.elo.model import result_probabilities as elo_probs
    from qwantej.models.poisson.model import poisson_scoreline
    from qwantej.performance.backtest import BacktestObservation

    train_from_utc = datetime.combine(cfg.train_from, datetime.min.time(), tzinfo=UTC)
    train_to_utc = datetime.combine(cfg.train_to, datetime.max.time(), tzinfo=UTC)
    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    test_to_utc = datetime.combine(cfg.test_to, datetime.max.time(), tzinfo=UTC)

    if cfg.all_leagues:
        finished_fixtures = session.scalars(
            select(Fixture)
            .where(
                Fixture.status == FixtureStatus.FINISHED,
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
                Fixture.home_goals.is_not(None),
                Fixture.away_goals.is_not(None),
            )
            .order_by(Fixture.kickoff_utc)
        ).all()
    else:
        from backend.models import EntityType, Provider, Season, SourceMapping

        provider_id = session.scalar(
            select(Provider.id).where(Provider.name == "API-Football")
        )
        competition_id = session.scalar(
            select(SourceMapping.canonical_id).where(
                SourceMapping.provider_id == provider_id,
                SourceMapping.entity_type == EntityType.COMPETITION,
                SourceMapping.external_id == str(cfg.league_id),
            )
        )
        if competition_id is None:
            log.warning("No API-Football competition mapping for league=%d", cfg.league_id)
            return []

        season_id = session.scalar(
            select(Season.id).where(
                Season.competition_id == competition_id,
                Season.label == str(cfg.season),
            )
        )
        if season_id is None:
            log.warning("No season mapping for league=%d season=%d", cfg.league_id, cfg.season)
            return []

        finished_fixtures = session.scalars(
            select(Fixture)
            .where(
                Fixture.competition_id == competition_id,
                Fixture.season_id == season_id,
                Fixture.status == FixtureStatus.FINISHED,
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
                Fixture.home_goals.is_not(None),
                Fixture.away_goals.is_not(None),
            )
            .order_by(Fixture.kickoff_utc)
        ).all()

    log.info("Found %d finished fixtures in train+test window", len(finished_fixtures))
    observations: list[BacktestObservation] = []
    skipped = 0
    code_commit = _current_code_commit()

    for fixture in finished_fixtures:
        kickoff = fixture.kickoff_utc
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        as_of = kickoff - timedelta(hours=2)  # simulate 2h pre-match decision

        try:
            features, _stats_ids, odds_ids, hist_rows = extract_fixture_features(
                session, fixture, as_of=as_of, n_recent=cfg.n_recent
            )
        except Exception as exc:
            log.debug("skip fixture %s: %s", fixture.id, exc)
            skipped += 1
            continue

        if features.home_matches < 3 or features.away_matches < 3:
            skipped += 1
            continue

        # In standard mode, skip fixtures without pre-kickoff source data — they
        # cannot produce a replayable feature snapshot nor a valid market baseline.
        # In --calibration-only mode, keep them: they contribute to calibration
        # training even without a market baseline (fair_market_probability=None).
        if not odds_ids and not cfg.calibration_only:
            skipped += 1
            continue

        # Poisson model - home win probability (1X2)
        dist = poisson_scoreline(features.home_xg, features.away_xg)
        poisson_result = dist.match_result()
        model_home_win = float(poisson_result.home)
        model_draw = float(poisson_result.draw)
        model_away_win = float(poisson_result.away)

        # ELO model for ensemble blend
        elo_result = elo_probs(features.elo_home_rating, features.elo_away_rating)
        elo_home_win = float(elo_result.home)

        # Simple ensemble: average Poisson + ELO for home win
        ensemble_home_win = (model_home_win + elo_home_win) / 2.0

        # Best market odds (1X2 home, if available)
        executable_odds: float | None = None
        fair_market_prob: float | None = None
        odds_rows = _best_1x2_odds(session, fixture.id, as_of=as_of)
        if odds_rows is not None:
            best_odds_row = odds_rows["home"]
            raw_home = float(best_odds_row.decimal_odds)
            executable_odds = raw_home
            # de-vig against best available draw and away for a 3-way market
            away_row = odds_rows["away"]
            draw_row = odds_rows["draw"]
            try:
                result = devig([
                    float(best_odds_row.decimal_odds),
                    float(draw_row.decimal_odds),
                    float(away_row.decimal_odds),
                ])
                fair_market_prob = result.fair[0]  # home probability
            except Exception:
                executable_odds = None

        # Include the exact quote bundle used for the market baseline even when
        # it falls outside the extraction service's bounded source-id list.
        source_odds_ids = list(odds_ids)
        if odds_rows is not None:
            for row in odds_rows.values():
                if row.id not in source_odds_ids:
                    source_odds_ids.append(row.id)
        # Build feature dict and embed training-set hash for P1 lineage (P1 fix):
        # historical fixture IDs used by ELO/Poisson are not FK-tracked in the
        # feature snapshot schema, so we commit to them via a content hash that
        # enables independent replay: re-run the same DB query with the same
        # as_of + competition scope, filter to settled rows, sort by ID, and
        # compare the SHA-256 digest.
        feature_dict = features_to_dict(features)
        feature_dict["_training_fixture_count"] = float(len(hist_rows))
        feature_dict["_training_fixture_ids_hash"] = historical_training_hash(hist_rows)

        if _stats_ids or source_odds_ids:
            create_feature_snapshot(
                session,
                fixture_id=fixture.id,
                feature_version="poisson-elo-features:1.0.0",
                as_of_timestamp=as_of,
                features=feature_dict,
                stats_snapshot_ids=_stats_ids,
                odds_quote_ids=source_odds_ids,
                imputation_policy_version="explicit-fallback-v1",
                code_commit=code_commit,
            )

        outcome: int | None = None
        outcome_observed_at: datetime | None = None
        if fixture.home_goals is not None and fixture.away_goals is not None:
            outcome = 1 if fixture.home_goals > fixture.away_goals else 0
            # P2b: outcome_observed_at is an approximation (kickoff + 2 h) used
            # for backtest eligibility only.  It is not a certified point-in-time
            # timestamp — in production, use the actual fixture status change time
            # from the provider (e.g. the stats_snapshot captured after FT status).
            outcome_observed_at = kickoff + timedelta(hours=2)

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
            quote_timestamp=best_odds_row.captured_at if odds_rows else None,
            model_probabilities=(model_home_win, model_draw, model_away_win),
        )
        observations.append(obs)

    log.info("Built %d observations (%d skipped)", len(observations), skipped)
    return observations


def _best_1x2_odds(
    session: Any, fixture_id: Any, *, as_of: datetime
) -> dict[str, Any] | None:
    """Return one coherent pre-kickoff 1X2 quote bundle.

    The three outcomes must come from the same bookmaker and capture timestamp;
    mixing books or post-kickoff prices would invalidate the de-vig baseline.
    """
    from sqlalchemy import select

    from backend.models import OddsQuote

    rows = session.scalars(
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.market == "1X2",
            OddsQuote.selection.in_(("home", "draw", "away")),
            OddsQuote.line.is_(None),
            OddsQuote.captured_at <= as_of,
        )
    ).all()
    bundles: dict[tuple[str, datetime], dict[str, Any]] = {}
    for row in rows:
        key = (row.bookmaker, row.captured_at)
        bundle = bundles.setdefault(key, {})
        current = bundle.get(row.selection)
        if current is None or row.decimal_odds > current.decimal_odds:
            bundle[row.selection] = row
    complete = [bundle for bundle in bundles.values() if len(bundle) == 3]
    return max(complete, key=lambda bundle: bundle["home"].decimal_odds) if complete else None


def _run_backtest(
    observations: list[Any], cfg: ExperimentConfig
) -> Any:
    """Run one fixed train-window/test-window walk-forward fold."""

    from qwantej.calibration import CalibrationMethod, ConservativePolicy
    from qwantej.performance.backtest import (
        WalkForwardConfig,
        walk_forward_backtest,
    )
    from qwantej.value import ValueGatePolicy

    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    # Eligible rows for sizing: must have a valid market baseline (odds).
    # In calibration-only mode, rows without odds still enter the walk-forward
    # and contribute to calibration training, but the min/test sizing uses only
    # observations with a market baseline so the evaluation window is well-defined.
    eligible_train = [
        o for o in observations
        if o.decision_as_of < test_from_utc and _eligible_walk_forward_row(o)
    ]
    eligible_test = [
        o for o in observations
        if o.decision_as_of >= test_from_utc and _eligible_walk_forward_row(o)
    ]

    min_train = 1 if cfg.calibration_only else 10
    if len(eligible_train) < min_train:
        raise ValueError(
            f"only {len(eligible_train)} eligible training rows; "
            f"at least {min_train} are required"
        )
    if not eligible_test:
        raise ValueError("no eligible test rows in the requested test window")

    calibration_method = CalibrationMethod.ISOTONIC
    # Use eligible counts for the walk-forward window sizing, capped at
    # reasonable values so a small calibration-only run doesn't create degenerate folds.
    wf_config = WalkForwardConfig(
        version="walk-forward:1.0.0",
        model_version="poisson+elo-ensemble:1.0.0",
        calibration_method=calibration_method,
        minimum_training_size=max(2, len(eligible_train)),
        test_window_size=max(1, len(eligible_test)),
        bootstrap_samples=500,
        bootstrap_seed=42,
        value_policy=ValueGatePolicy(),
        conservative_policy=ConservativePolicy(),
    )

    report = walk_forward_backtest(observations, config=wf_config)
    return report, wf_config


def _eligible_walk_forward_row(observation: Any) -> bool:
    """Mirror the core evaluator's input contract for train/test sizing."""

    return (
        observation.outcome is not None
        and observation.outcome_observed_at is not None
        and observation.outcome_observed_at > observation.decision_as_of
        and observation.feature_as_of <= observation.decision_as_of
        and observation.fair_market_probability is not None
        and observation.executable_odds is not None
        and observation.quote_timestamp is not None
        and observation.quote_timestamp <= observation.decision_as_of
    )


def _record_experiment(
    session: Any, report: Any, cfg: ExperimentConfig, started_at: datetime
) -> None:
    from backend.services.experiments import (
        ExperimentIdentity,
        complete_walk_forward_experiment,
        start_walk_forward_experiment,
    )

    try:
        code_commit = _current_code_commit()
    except Exception:
        code_commit = "unknown"

    train_from_utc = datetime.combine(cfg.train_from, datetime.min.time(), tzinfo=UTC)
    train_to_utc = datetime.combine(cfg.train_to, datetime.max.time(), tzinfo=UTC)
    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    test_to_utc = datetime.combine(cfg.test_to, datetime.max.time(), tzinfo=UTC)

    data_snapshot_ref = _data_snapshot_ref(cfg)
    identity = ExperimentIdentity(
        name=cfg.name,
        version="1.0.0",
        calibration_version="isotonic:1.0.0",
        code_commit=code_commit,
        data_snapshot_ref=data_snapshot_ref,
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
    if report.calibrated_calibration is not None:
        log.info(
            "  calibrated_brier_score: %.4f",
            report.calibrated_calibration.brier_score,
        )
        log.info(
            "  calibrated_ece:         %.4f",
            report.calibrated_calibration.expected_calibration_error,
        )


def _data_snapshot_ref(cfg: ExperimentConfig) -> str:
    """Build the provenance tag stored in the experiment registry row.

    Encodes all flags that affect which observations are built so every
    experiment row can be reproduced from its stored reference alone.
    """
    base = (
        "api-football:all-leagues"
        if cfg.all_leagues
        else f"api-football:league={cfg.league_id}:season={cfg.season}"
    )
    if cfg.calibration_only:
        return base + ":calibration-only"
    return base


def _current_code_commit() -> str:
    import subprocess

    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, text=True
    ).strip()


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
        help="Roll back after experiment - no DB rows persisted",
    )
    parser.add_argument(
        "--calibration-only", action="store_true",
        help="Build observations for all finished fixtures (no pre-kickoff odds required). "
             "Rows without odds contribute to calibration training only; evaluation "
             "metrics still require at least 3 observations with a valid market baseline.",
    )
    parser.add_argument(
        "--all-leagues", action="store_true",
        help="Pool finished fixtures from ALL competitions in the DB (ignores --league "
             "and --season for observation building). Useful when a single league lacks "
             "enough PIT-valid pre-match odds for a walk-forward split.",
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
        calibration_only=args.calibration_only,
        all_leagues=args.all_leagues,
    )

    from backend.core.config import get_settings
    from backend.core.db import make_engine, session_scope
    from backend.services.api_football_client import ApiFootballClient

    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL must point at Postgres - update your .env file")
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
            if cfg.dry_run:
                session.rollback()
                log.info("Dry-run: ingestion changes rolled back")

    # Phase 2: feature extraction + backtest + record experiment
    with session_scope(engine) as session:
        observations = _build_backtest_observations(session, cfg)
        if not observations:
            log.warning("No observations built - cannot run backtest")
            sys.exit(0)

        report, wf_config = _run_backtest(observations, cfg)
        _print_report(report)

        if not cfg.dry_run:
            _record_experiment(session, (report, wf_config), cfg, started_at)
        else:
            session.rollback()
            log.info("Dry-run: experiment NOT recorded in DB")

    log.info("Walk-forward experiment complete.")


if __name__ == "__main__":
    main()
