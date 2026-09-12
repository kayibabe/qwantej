"""Evaluate whether Qwantej has evidence to leave the research boundary.

The command is read-only and fail-closed. It inspects persisted experiment,
forecast, settlement, reliability, and registry records. A passing report is
necessary but does not replace human governance approval or a promotion PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

# Direct ``python scripts/run_readiness_report.py`` puts ``scripts`` rather
# than the repository root on sys.path. Keep the operator-facing invocation
# consistent with the other scripts.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.models.experiments import Experiment, ExperimentKind, ExperimentStatus  # noqa: E402
from backend.models.predictions import Prediction  # noqa: E402
from backend.models.registry import ModelRegistry, ModelStatus  # noqa: E402
from backend.models.reliability import ReliabilitySnapshot  # noqa: E402
from backend.models.settlements import Accumulator, Settlement  # noqa: E402


@dataclass(frozen=True)
class ReadinessEvidence:
    latest_pit_experiment: bool
    experiment_sample_size: int
    experiment_leakage_rows_rejected: int
    experiment_metrics_complete: bool
    experiment_metrics: dict[str, Any]
    prediction_count: int
    predictions_missing_provenance: int
    settled_prediction_count: int
    reliability_snapshot_count: int
    reliability_future_rows_excluded: int
    champion_model_count: int
    champion_calibrator_count: int
    accumulator_count: int
    live_accumulator_count: int


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReadinessReport:
    generated_at: str
    minimum_sample_size: int
    ready: bool
    checks: tuple[ReadinessCheck, ...]
    evidence: ReadinessEvidence

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _metric(metrics: dict[str, Any], *path: str) -> Any:
    value: Any = metrics
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def evaluate_readiness(
    evidence: ReadinessEvidence,
    *,
    minimum_sample_size: int = 30,
    generated_at: datetime | None = None,
) -> ReadinessReport:
    """Apply explicit promotion prerequisites to collected evidence."""

    if minimum_sample_size < 1:
        raise ValueError("minimum_sample_size must be positive")
    checks = (
        ReadinessCheck("pit_certified_walk_forward", evidence.latest_pit_experiment,
                       "a succeeded, de-vigged-market walk-forward must be PIT-certified"),
        ReadinessCheck("minimum_walk_forward_sample",
                       evidence.experiment_sample_size >= minimum_sample_size,
                       f"sample={evidence.experiment_sample_size}, required={minimum_sample_size}"),
        ReadinessCheck("no_leakage_rows", evidence.experiment_leakage_rows_rejected == 0,
                       f"leakage_rows_rejected={evidence.experiment_leakage_rows_rejected}"),
        ReadinessCheck("required_metrics_present", evidence.experiment_metrics_complete,
                       "Brier, log loss, calibration, CLV, and ROI must be persisted"),
        ReadinessCheck("forecast_archive_provenance",
                       evidence.prediction_count > 0
                       and evidence.predictions_missing_provenance == 0,
                       f"predictions={evidence.prediction_count}, "
                       f"missing_provenance={evidence.predictions_missing_provenance}"),
        ReadinessCheck("settled_prediction_sample",
                       evidence.settled_prediction_count >= minimum_sample_size,
                       f"settled_predictions={evidence.settled_prediction_count}, "
                       f"required={minimum_sample_size}"),
        ReadinessCheck("reliability_snapshots",
                       evidence.reliability_snapshot_count > 0
                       and evidence.reliability_future_rows_excluded == 0,
                       f"snapshots={evidence.reliability_snapshot_count}, "
                       f"future_rows_excluded={evidence.reliability_future_rows_excluded}"),
        ReadinessCheck("champion_lineage",
                       evidence.champion_model_count == 1
                       and evidence.champion_calibrator_count == 1,
                       f"champion_models={evidence.champion_model_count}, "
                       f"champion_calibrators={evidence.champion_calibrator_count}"),
        ReadinessCheck("paper_only_boundary", evidence.live_accumulator_count == 0,
                       f"live_accumulators={evidence.live_accumulator_count}; "
                       "paper-only remains enforced"),
    )
    return ReadinessReport(
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        minimum_sample_size=minimum_sample_size,
        ready=all(check.passed for check in checks),
        checks=checks,
        evidence=evidence,
    )


def _count(session: Any, statement: Any) -> int:
    return int(session.scalar(statement) or 0)


def collect_evidence(session: Any) -> ReadinessEvidence:
    """Collect persisted facts without writing or mutating any row."""

    experiment = session.scalar(
        select(Experiment).where(
            Experiment.kind == ExperimentKind.WALK_FORWARD_BACKTEST,
            Experiment.status == ExperimentStatus.SUCCEEDED,
        ).order_by(Experiment.finished_at.desc()).limit(1)
    )
    metrics = experiment.metrics if experiment and isinstance(experiment.metrics, dict) else {}
    latest_pit = bool(
        experiment
        and experiment.configuration.get("pit_certified") is True
        and experiment.baseline == "de-vigged-market"
        and experiment.result_hash
    )
    required_metric_values = (
        _metric(metrics, "calibrated_calibration", "brier_score"),
        _metric(metrics, "calibrated_calibration", "log_loss"),
        _metric(metrics, "calibrated_calibration", "expected_calibration_error"),
        metrics.get("average_clv"),
        metrics.get("roi"),
    )
    metrics_complete = all(value is not None for value in required_metric_values)
    prediction_count = _count(session, select(func.count()).select_from(Prediction))
    missing_provenance = _count(session, select(func.count()).select_from(Prediction).where(
        (Prediction.code_commit.is_(None))
        | (Prediction.input_snapshot_ref.is_(None))
        | (Prediction.input_snapshot_hash.is_(None))
        | (Prediction.model_run_id.is_(None))
    ))
    settled_count = _count(session, select(func.count()).select_from(Settlement).where(
        Settlement.subject_type == "prediction"
    ))
    reliability_count = _count(session, select(func.count()).select_from(ReliabilitySnapshot))
    excluded = session.scalar(select(func.coalesce(func.sum(
        ReliabilitySnapshot.future_rows_excluded
    ), 0)))
    champion_models = _count(session, select(func.count()).select_from(ModelRegistry).where(
        ModelRegistry.status == ModelStatus.CHAMPION
    ))
    from backend.models.calibration import CalibrationModel, CalibrationStatus

    champion_calibrators = _count(session, select(func.count()).select_from(CalibrationModel).where(
        CalibrationModel.status == CalibrationStatus.CHAMPION
    ))
    accumulator_count = _count(session, select(func.count()).select_from(Accumulator))
    live_accumulators = _count(session, select(func.count()).select_from(Accumulator).where(
        Accumulator.paper_only.is_(False)
    ))
    return ReadinessEvidence(
        latest_pit_experiment=latest_pit,
        experiment_sample_size=int(experiment.sample_size or 0) if experiment else 0,
        experiment_leakage_rows_rejected=int(experiment.leakage_rows_rejected or 0)
        if experiment else 0,
        experiment_metrics_complete=bool(metrics_complete),
        experiment_metrics=metrics,
        prediction_count=prediction_count,
        predictions_missing_provenance=missing_provenance,
        settled_prediction_count=settled_count,
        reliability_snapshot_count=reliability_count,
        reliability_future_rows_excluded=int(excluded or 0),
        champion_model_count=champion_models,
        champion_calibrator_count=champion_calibrators,
        accumulator_count=accumulator_count,
        live_accumulator_count=live_accumulators,
    )


def _print_report(report: ReadinessReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True, default=str))
        return
    print(f"Readiness: {'PASS' if report.ready else 'BLOCKED'}")
    print(f"Generated: {report.generated_at}")
    for check in report.checks:
        print(f"{'PASS' if check.passed else 'BLOCK'} {check.name}: {check.detail}")
    metrics = report.evidence.experiment_metrics
    print("Metrics: "
          f"brier={_metric(metrics, 'calibrated_calibration', 'brier_score')!r} "
          f"log_loss={_metric(metrics, 'calibrated_calibration', 'log_loss')!r} "
          f"ece={_metric(metrics, 'calibrated_calibration', 'expected_calibration_error')!r} "
          f"clv={metrics.get('average_clv')!r} roi={metrics.get('roi')!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-sample-size", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_sample_size < 1:
        print("--min-sample-size must be positive", file=sys.stderr)
        return 2
    try:
        from backend.core.config import get_settings
        from backend.core.db import make_engine, session_scope

        settings = get_settings()
        if not settings.database_url.startswith("postgresql"):
            print("DATABASE_URL must point at PostgreSQL", file=sys.stderr)
            return 2
        with session_scope(make_engine(settings.database_url)) as session:
            report = evaluate_readiness(
                collect_evidence(session), minimum_sample_size=args.min_sample_size
            )
    except Exception as exc:  # pragma: no cover - operator/database failure
        print(f"Unable to collect readiness evidence: {exc}", file=sys.stderr)
        return 2
    _print_report(report, as_json=args.json)
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
