"""Persist complete, content-addressed walk-forward experiment records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Experiment, ExperimentKind, ExperimentStatus
from qwantej.performance import WalkForwardConfig, WalkForwardReport
from qwantej.performance.calibration_backtest import CalibrationOnlyConfig, CalibrationOnlyReport


@dataclass(frozen=True)
class ExperimentIdentity:
    name: str
    version: str
    calibration_version: str
    code_commit: str
    data_snapshot_ref: str
    training_window_start: datetime
    training_window_end: datetime
    test_window_start: datetime
    test_window_end: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("name", self.name),
            ("version", self.version),
            ("calibration_version", self.calibration_version),
            ("code_commit", self.code_commit),
            ("data_snapshot_ref", self.data_snapshot_ref),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        for timestamp_name, timestamp_value in (
            ("training_window_start", self.training_window_start),
            ("training_window_end", self.training_window_end),
            ("test_window_start", self.test_window_start),
            ("test_window_end", self.test_window_end),
        ):
            if timestamp_value.tzinfo is None or timestamp_value.utcoffset() is None:
                raise ValueError(f"{timestamp_name} must be timezone-aware")
        if self.training_window_start > self.training_window_end:
            raise ValueError("training window is reversed")
        if self.test_window_start > self.test_window_end:
            raise ValueError("test window is reversed")
        if self.training_window_end > self.test_window_start:
            raise ValueError("training window must end before the test window")


def start_walk_forward_experiment(
    session: Session,
    *,
    identity: ExperimentIdentity,
    config: WalkForwardConfig,
    started_at: datetime,
) -> Experiment:
    """Insert and flush the immutable configuration before evaluation starts."""

    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    experiment = Experiment(
        name=identity.name,
        version=identity.version,
        kind=ExperimentKind.WALK_FORWARD_BACKTEST,
        status=ExperimentStatus.RUNNING,
        model_version=config.model_version,
        calibration_version=identity.calibration_version,
        value_policy_version=config.value_policy.version,
        conservative_policy_version=config.conservative_policy.version,
        code_commit=identity.code_commit,
        data_snapshot_ref=identity.data_snapshot_ref,
        baseline="de-vigged-market",
        random_seed=config.bootstrap_seed,
        configuration=config.as_dict(),
        started_at=started_at,
        training_window_start=identity.training_window_start,
        training_window_end=identity.training_window_end,
        test_window_start=identity.test_window_start,
        test_window_end=identity.test_window_end,
    )
    session.add(experiment)
    session.flush()
    return experiment


def complete_walk_forward_experiment(
    session: Session,
    experiment: Experiment,
    report: WalkForwardReport,
    *,
    finished_at: datetime,
) -> None:
    """Finalize a running registry row exactly once with canonical metrics."""

    if experiment.status is not ExperimentStatus.RUNNING:
        raise ValueError("only a running experiment can be completed")
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("finished_at must be timezone-aware")
    if finished_at < experiment.started_at:
        raise ValueError("finished_at cannot precede started_at")
    metrics = _jsonable(report)
    canonical = json.dumps(metrics, sort_keys=True, separators=(",", ":"))
    experiment.status = ExperimentStatus.SUCCEEDED
    experiment.finished_at = finished_at
    experiment.sample_size = report.sample_size
    experiment.leakage_rows_rejected = report.leakage_rows_rejected
    experiment.metrics = metrics
    experiment.result_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    session.flush()


def start_research_experiment(
    session: Session,
    *,
    identity: ExperimentIdentity,
    config: CalibrationOnlyConfig,
    started_at: datetime,
) -> Experiment:
    """Insert and flush an immutable record for a non-PIT-certified research run.

    Fills ``value_policy_version`` and ``conservative_policy_version`` with the
    sentinel ``"not-applicable"`` (no market baseline), ``baseline`` with
    ``"retrospective-research"``, and ``random_seed`` with 0 (no bootstrap).
    ``configuration`` always carries ``pit_certified=False`` and
    ``research_mode=True`` so the record is self-describing.
    """
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    configuration = config.as_dict()
    experiment = Experiment(
        name=identity.name,
        version=identity.version,
        kind=ExperimentKind.WALK_FORWARD_BACKTEST,
        status=ExperimentStatus.RUNNING,
        model_version=config.model_version,
        calibration_version=identity.calibration_version,
        value_policy_version="not-applicable",
        conservative_policy_version="not-applicable",
        code_commit=identity.code_commit,
        data_snapshot_ref=identity.data_snapshot_ref,
        baseline="retrospective-research",
        random_seed=0,
        configuration=configuration,
        started_at=started_at,
        training_window_start=identity.training_window_start,
        training_window_end=identity.training_window_end,
        test_window_start=identity.test_window_start,
        test_window_end=identity.test_window_end,
    )
    session.add(experiment)
    session.flush()
    return experiment


def complete_research_experiment(
    session: Session,
    experiment: Experiment,
    report: CalibrationOnlyReport,
    *,
    finished_at: datetime,
) -> None:
    """Finalize a running research experiment with calibration-only metrics.

    ``leakage_rows_rejected`` is set to 0 — the canonical column tracks true
    PIT leakage, which cannot be measured in a non-PIT-certified run.  The
    weaker ``temporal_order_rejections`` count is preserved inside
    ``report.metrics`` (serialised with every other report field) so it
    is queryable without polluting the PIT-leakage semantic.
    """
    if experiment.status is not ExperimentStatus.RUNNING:
        raise ValueError("only a running experiment can be completed")
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("finished_at must be timezone-aware")
    if finished_at < experiment.started_at:
        raise ValueError("finished_at cannot precede started_at")
    metrics = _jsonable(report)
    canonical = json.dumps(metrics, sort_keys=True, separators=(",", ":"))
    experiment.status = ExperimentStatus.SUCCEEDED
    experiment.finished_at = finished_at
    experiment.sample_size = report.sample_size
    experiment.leakage_rows_rejected = 0
    experiment.metrics = metrics
    experiment.result_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    session.flush()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
