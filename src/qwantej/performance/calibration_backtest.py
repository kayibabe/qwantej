"""Calibration-only walk-forward for retrospective research (non-PIT-certified).

This evaluator operates without a market baseline. It measures how well the
raw model probabilities are calibrated against outcomes, using the same
walk-forward split discipline as the production backtest but without the
guarantee that training observations were genuinely available at each simulated
decision cutoff.

**Not PIT-certified.** A zero `temporal_order_rejections` count does NOT imply
historical data was available at decision time — it only means the ordering
constraints within the supplied observation set are internally consistent.

Do not use Brier / ECE from this evaluator as evidence of production readiness.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from qwantej.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    calibration_report,
    fit_calibrator,
)
from qwantej.calibration.metrics import CalibrationReport


@dataclass(frozen=True)
class CalibrationObservationRow:
    """Minimal observation for calibration-only evaluation (no market fields)."""

    observation_id: str
    decision_as_of: datetime
    feature_as_of: datetime
    outcome_observed_at: datetime
    model_version: str
    raw_probability: float
    outcome: int
    model_probabilities: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id must not be blank")
        if not self.model_version.strip():
            raise ValueError("model_version must not be blank")
        for name, ts in (
            ("decision_as_of", self.decision_as_of),
            ("feature_as_of", self.feature_as_of),
            ("outcome_observed_at", self.outcome_observed_at),
        ):
            _aware(name, ts)
        _unit("raw_probability", self.raw_probability)
        if self.outcome not in (0, 1):
            raise ValueError("outcome must be 0 or 1")
        for p in self.model_probabilities:
            _unit("model probability", p)


@dataclass(frozen=True)
class CalibrationOnlyConfig:
    """Configuration for a calibration-only (marketless) walk-forward run."""

    version: str
    model_version: str
    calibration_method: CalibrationMethod = CalibrationMethod.PLATT
    minimum_training_size: int = 30
    test_window_size: int = 10

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be blank")
        if not self.model_version.strip():
            raise ValueError("model_version must not be blank")
        if self.minimum_training_size < 2:
            raise ValueError("minimum_training_size must be >= 2")
        if self.test_window_size < 1:
            raise ValueError("test_window_size must be >= 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "model_version": self.model_version,
            "calibration_method": self.calibration_method.value,
            "minimum_training_size": self.minimum_training_size,
            "test_window_size": self.test_window_size,
            "pit_certified": False,
            "research_mode": True,
        }


@dataclass(frozen=True)
class CalibrationFold:
    training_as_of: datetime
    training_sample_size: int
    test_start: datetime
    test_end: datetime
    evaluated_rows: int
    raw_brier: float
    calibrated_brier: float


@dataclass(frozen=True)
class CalibrationOnlyReport:
    config: dict[str, object]
    sample_size: int
    start: datetime
    end: datetime
    folds: tuple[CalibrationFold, ...]
    temporal_order_rejections: int
    model_version_rows_rejected: int
    raw_calibration: CalibrationReport
    calibrated_calibration: CalibrationReport
    pit_certified: bool = False
    research_mode: bool = True


def calibration_only_walk_forward(
    observations: Iterable[CalibrationObservationRow],
    config: CalibrationOnlyConfig,
) -> CalibrationOnlyReport:
    """Walk-forward calibration evaluator without market data.

    Applies the same training/test split discipline as the production evaluator.
    Temporal-order violations (feature_as_of > decision_as_of, or
    outcome_observed_at <= decision_as_of) are counted and rejected from
    evaluation but are distinct from true PIT leakage — historical data
    availability is not verified.

    Raises ValueError when:
    - no observations are supplied
    - observation_ids are not unique
    - insufficient valid rows remain after version and temporal-order filtering
    - no folds have enough training history
    """
    supplied = tuple(observations)
    if not supplied:
        raise ValueError("calibration backtest requires at least one observation")
    ids = [item.observation_id for item in supplied]
    if len(ids) != len(set(ids)):
        raise ValueError("observation_id values must be unique")

    version_rejected = sum(
        item.model_version != config.model_version for item in supplied
    )
    version_rows = [
        item for item in supplied if item.model_version == config.model_version
    ]

    # Temporal-order check: feature_as_of must precede decision_as_of; outcome
    # must be observed strictly after the decision cutoff.  This is NOT the same
    # as PIT certification — it verifies internal ordering only.
    temporal_rejected = sum(
        item.feature_as_of > item.decision_as_of
        or item.outcome_observed_at <= item.decision_as_of
        for item in version_rows
    )
    valid_rows = sorted(
        (
            item
            for item in version_rows
            if item.feature_as_of <= item.decision_as_of
            and item.outcome_observed_at > item.decision_as_of
        ),
        key=lambda item: (item.decision_as_of, item.observation_id),
    )

    if len(valid_rows) <= config.minimum_training_size:
        raise ValueError(
            f"not enough temporally-valid rows ({len(valid_rows)}) for one "
            f"walk-forward test window (minimum_training_size={config.minimum_training_size})"
        )

    evaluated: list[tuple[CalibrationObservationRow, float]] = []
    folds: list[CalibrationFold] = []

    for start_index in range(
        config.minimum_training_size, len(valid_rows), config.test_window_size
    ):
        test_rows = valid_rows[start_index : start_index + config.test_window_size]
        training_as_of = test_rows[0].decision_as_of

        training_rows = [
            item
            for item in valid_rows
            if item.decision_as_of < training_as_of
            and item.outcome_observed_at <= training_as_of
        ]
        if len(training_rows) < config.minimum_training_size:
            continue

        fit = fit_calibrator(
            (
                CalibrationObservation(
                    raw_probability=item.raw_probability,
                    outcome=item.outcome,
                    predicted_at=item.decision_as_of,
                    outcome_observed_at=item.outcome_observed_at,
                )
                for item in training_rows
            ),
            method=config.calibration_method,
            version=f"{config.version}:{training_as_of.isoformat()}",
            trained_as_of=training_as_of,
            minimum_sample_size=config.minimum_training_size,
        )
        calibrator = fit.calibrator
        before = len(evaluated)
        fold_raw: list[float] = []
        fold_calibrated: list[float] = []
        fold_outcomes: list[int] = []
        for item in test_rows:
            calibrated = calibrator.predict(item.raw_probability)
            evaluated.append((item, calibrated))
            fold_raw.append(item.raw_probability)
            fold_calibrated.append(calibrated)
            fold_outcomes.append(item.outcome)
        folds.append(
            CalibrationFold(
                training_as_of=training_as_of,
                training_sample_size=len(training_rows),
                test_start=test_rows[0].decision_as_of,
                test_end=test_rows[-1].decision_as_of,
                evaluated_rows=len(evaluated) - before,
                raw_brier=_brier(fold_raw, fold_outcomes),
                calibrated_brier=_brier(fold_calibrated, fold_outcomes),
            )
        )

    if not evaluated:
        raise ValueError(
            "no walk-forward folds had sufficient training history; "
            "increase the date range or reduce minimum_training_size"
        )

    raw_probs = [item.raw_probability for item, _ in evaluated]
    calibrated_probs = [cal for _, cal in evaluated]
    outcomes = [item.outcome for item, _ in evaluated]

    return CalibrationOnlyReport(
        config=config.as_dict(),
        sample_size=len(evaluated),
        start=evaluated[0][0].decision_as_of,
        end=evaluated[-1][0].decision_as_of,
        folds=tuple(folds),
        temporal_order_rejections=temporal_rejected,
        model_version_rows_rejected=version_rejected,
        raw_calibration=calibration_report(raw_probs, outcomes),
        calibrated_calibration=calibration_report(calibrated_probs, outcomes),
    )


def _brier(probs: list[float], outcomes: list[int]) -> float:
    if not probs:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes, strict=True)) / len(probs)


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unit(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
