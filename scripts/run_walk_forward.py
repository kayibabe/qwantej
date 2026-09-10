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
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, replace
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
    observation_manifest_hash: str | None = None


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

    from backend.models import Fixture
    from backend.services.feature_extraction import (
        extract_fixture_features,
        fixture_result_observed_after_kickoff,
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

    log.info("Found %d fixtures in train+test window", len(finished_fixtures))
    observations: list[BacktestObservation] = []
    skipped = 0
    code_commit = _current_code_commit()

    for fixture in finished_fixtures:
        kickoff = fixture.kickoff_utc
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        as_of = kickoff - timedelta(hours=2)  # simulate 2h pre-match decision

        # The mutable canonical fixture row is not a point-in-time result
        # source. Require an immutable provider snapshot observed after
        # kickoff, and carry its actual capture time into the evaluator.
        observed_result = fixture_result_observed_after_kickoff(session, fixture)
        if observed_result is None:
            skipped += 1
            continue

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
        # Build feature dict and embed the immutable result-observation hash.
        # Training results are not FK-tracked in the feature snapshot schema,
        # so this content hash is the replay contract for the exact PIT source
        # rows and capture times used by ELO/Poisson.
        feature_dict = features_to_dict(features)
        feature_dict["_training_fixture_count"] = float(len(hist_rows))
        feature_dict["_training_result_snapshot_hash"] = historical_training_hash(hist_rows)

        snap_ref: str | None = None
        if _stats_ids or source_odds_ids:
            snap = create_feature_snapshot(
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
            snap_ref = snap.snapshot_ref

        outcome = int(observed_result.home_goals > observed_result.away_goals)
        outcome_observed_at = observed_result.observed_at

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
            snapshot_ref=snap_ref,
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
    """Dispatch to the PIT-certified walk-forward or the retrospective calibration evaluator.

    Returns a 2-tuple ``(report, config)`` whose concrete types depend on the path:
    - Standard:           ``(WalkForwardReport, WalkForwardConfig)``
    - Calibration-only:  ``(CalibrationOnlyReport, CalibrationOnlyConfig)``
    """
    if cfg.calibration_only:
        return _run_calibration_only_backtest(observations, cfg)

    from qwantej.calibration import CalibrationMethod, ConservativePolicy
    from qwantej.performance.backtest import (
        WalkForwardConfig,
        walk_forward_backtest,
    )
    from qwantej.value import ValueGatePolicy

    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    eligible_train = [
        o for o in observations
        if o.decision_as_of < test_from_utc and _eligible_walk_forward_row(o)
    ]
    eligible_test = [
        o for o in observations
        if o.decision_as_of >= test_from_utc and _eligible_walk_forward_row(o)
    ]

    if len(eligible_train) < 10:
        raise ValueError(
            f"only {len(eligible_train)} eligible training rows; at least 10 are required"
        )
    if not eligible_test:
        raise ValueError("no eligible test rows in the requested test window")

    wf_config = WalkForwardConfig(
        version="walk-forward:1.0.0",
        model_version="poisson+elo-ensemble:1.0.0",
        calibration_method=CalibrationMethod.ISOTONIC,
        minimum_training_size=max(2, len(eligible_train)),
        test_window_size=max(1, len(eligible_test)),
        bootstrap_samples=500,
        bootstrap_seed=42,
        value_policy=ValueGatePolicy(),
        conservative_policy=ConservativePolicy(),
    )

    report = walk_forward_backtest(observations, config=wf_config)
    manifest = tuple(_observation_manifest(observations))
    return report, replace(wf_config, observation_manifest=manifest)


def _run_calibration_only_backtest(
    observations: list[Any], cfg: ExperimentConfig
) -> Any:
    """Retrospective calibration evaluator — NOT PIT-certified.

    Routes through ``calibration_only_walk_forward`` so the result is stored
    under the research experiment path (start_research_experiment /
    complete_research_experiment) with ``pit_certified=False`` in the registry.
    """
    from qwantej.calibration import CalibrationMethod
    from qwantej.performance.calibration_backtest import (
        CalibrationObservationRow,
        CalibrationOnlyConfig,
        calibration_only_walk_forward,
    )

    test_from_utc = datetime.combine(cfg.test_from, datetime.min.time(), tzinfo=UTC)
    eligible = [o for o in observations if _calibration_eligible(o)]

    eligible_train = [o for o in eligible if o.decision_as_of < test_from_utc]
    eligible_test = [o for o in eligible if o.decision_as_of >= test_from_utc]

    if len(eligible_train) < 1:
        raise ValueError(
            f"only {len(eligible_train)} eligible calibration training rows; "
            "at least 1 is required"
        )
    if not eligible_test:
        raise ValueError("no eligible calibration test rows in the requested test window")

    # Count only training rows whose outcome was already settled at test start.
    # The evaluator's per-fold filter requires outcome_observed_at <= training_as_of;
    # using len(eligible_train) would require every outcome to be settled at the
    # first fold's cutoff, causing ValueError when late results arrive days after kickoff.
    settled_train = [
        o for o in eligible_train
        if o.outcome_observed_at is not None and o.outcome_observed_at <= test_from_utc
    ]
    if len(settled_train) < 2:
        raise ValueError(
            f"only {len(settled_train)} calibration training row(s) with outcome settled by "
            f"{test_from_utc}; calibration requires at least 2 — try widening the training window"
        )

    calib_rows = [
        CalibrationObservationRow(
            observation_id=obs.observation_id,
            decision_as_of=obs.decision_as_of,
            feature_as_of=obs.feature_as_of,
            outcome_observed_at=obs.outcome_observed_at,  # type: ignore[arg-type]
            model_version=obs.model_version,
            raw_probability=obs.raw_probability,
            outcome=obs.outcome,  # type: ignore[arg-type]
            model_probabilities=obs.model_probabilities,
        )
        for obs in eligible
    ]
    calib_config = CalibrationOnlyConfig(
        version="calibration-only:1.0.0",
        model_version="poisson+elo-ensemble:1.0.0",
        calibration_method=CalibrationMethod.ISOTONIC,
        minimum_training_size=max(2, len(settled_train)),
        test_window_size=max(1, len(eligible_test)),
    )
    report = calibration_only_walk_forward(calib_rows, calib_config)
    return report, calib_config


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


def _calibration_eligible(observation: Any) -> bool:
    """Relaxed eligibility for --calibration-only: outcome required, odds not.

    Rows without a market baseline still contribute to calibration training;
    they will carry fair_market_probability=None and be skipped by the
    value-gate evaluator at report time.
    """
    return (
        observation.outcome is not None
        and observation.outcome_observed_at is not None
        and observation.outcome_observed_at > observation.decision_as_of
    )


def _record_experiment(
    session: Any, report: Any, cfg: ExperimentConfig, started_at: datetime
) -> None:
    from backend.services.experiments import ExperimentIdentity
    from qwantej.performance.calibration_backtest import CalibrationOnlyConfig

    try:
        code_commit = _current_code_commit()
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
        data_snapshot_ref=_data_snapshot_ref(cfg),
        training_window_start=train_from_utc,
        training_window_end=train_to_utc,
        test_window_start=test_from_utc,
        test_window_end=test_to_utc,
    )

    actual_report, run_config = report
    if isinstance(run_config, CalibrationOnlyConfig):
        # Retrospective path — not PIT-certified; stored as a research experiment.
        from backend.services.experiments import (
            complete_research_experiment,
            start_research_experiment,
        )
        experiment = start_research_experiment(
            session,
            identity=identity,
            config=run_config,
            started_at=started_at,
        )
        complete_research_experiment(
            session,
            experiment,
            actual_report,
            finished_at=datetime.now(UTC),
        )
    else:
        from backend.services.experiments import (
            complete_walk_forward_experiment,
            start_walk_forward_experiment,
        )
        experiment = start_walk_forward_experiment(
            session,
            identity=identity,
            config=run_config,
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
    if hasattr(report, "leakage_rows_rejected"):
        log.info("  leakage_rejected:     %d", report.leakage_rows_rejected)
    if hasattr(report, "temporal_order_rejections"):
        log.info("  temporal_order_rejected (research): %d", report.temporal_order_rejections)
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
    parts = [base, f"n_recent={cfg.n_recent}"]
    if cfg.calibration_only:
        parts.append("calibration-only")
    if cfg.observation_manifest_hash:
        parts.append(f"manifest={cfg.observation_manifest_hash}")
    return ":".join(parts)


def _observation_manifest(observations: list[Any]) -> list[dict[str, object]]:
    """Return every decision-critical field supplied to the backtest."""

    manifest = []
    for observation in sorted(observations, key=lambda item: item.observation_id):
        row = asdict(observation)
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
            elif isinstance(value, tuple):
                row[key] = list(value)
        manifest.append(row)
    return manifest


def _observation_manifest_hash(observations: list[Any]) -> str:
    """Hash the exact observation rows supplied to the backtest."""

    manifest = _observation_manifest(observations)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


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

    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        log.error("DATABASE_URL must point at Postgres - update your .env file")
        sys.exit(1)

    engine = make_engine(settings.database_url)

    if not args.skip_ingest:
        if cfg.dry_run:
            # Dry-run must not commit any rows.  Ingestion runs in a separate
            # session_scope that commits on success, so skip it entirely rather
            # than risk writing data the caller didn't intend to persist.
            # Use --skip-ingest explicitly when you want to run against existing DB
            # data without triggering this guard.
            log.info("Dry-run: skipping ingestion (add --skip-ingest to suppress this message)")
        else:
            from backend.services.api_football_client import ApiFootballClient

            if not settings.api_football_key:
                log.error(
                    "API_FOOTBALL_KEY is not set in .env — set it or use --skip-ingest"
                )
                sys.exit(1)
            log.warning(
                "Ingesting with captured_at=now; odds will NOT have pre-kickoff PIT "
                "validity for historical fixtures. Add --calibration-only unless you "
                "have a live-ingested snapshot archive. Use --skip-ingest to skip."
            )
            client = ApiFootballClient(
                api_key=settings.api_football_key,
                base_url=settings.api_football_base_url,
                timeout_seconds=settings.api_football_timeout_seconds,
            )
            with session_scope(engine) as ingest_session:
                _ingest_season(client, ingest_session, cfg)

    started_at = datetime.now(UTC)

    # Feature extraction + backtest + record experiment.  A walk-forward run
    # consumes an existing archive of provider snapshots; it must not create
    # current-time captures and then mistake them for historical availability.
    with session_scope(engine) as session:
        observations = _build_backtest_observations(session, cfg)
        cfg.observation_manifest_hash = _observation_manifest_hash(observations)
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
