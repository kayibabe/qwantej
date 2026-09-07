"""Calibration monitoring metrics and reliability curves (framework §18)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

_EPSILON = 1e-12


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_probability: float
    event_rate: float


@dataclass(frozen=True)
class CalibrationReport:
    sample_size: int
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    calibration_intercept: float | None
    calibration_slope: float | None
    brier_skill_score: float | None
    reliability_curve: tuple[ReliabilityBin, ...]


def calibration_report(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    reference_probabilities: Sequence[float] | None = None,
    bins: int = 10,
) -> CalibrationReport:
    predicted, observed = _validated_arrays(probabilities, outcomes)
    if bins < 2:
        raise ValueError("bins must be at least 2")
    curve = _reliability_curve(predicted, observed, bins)
    brier = float(np.mean((predicted - observed) ** 2))
    clipped = np.clip(predicted, _EPSILON, 1.0 - _EPSILON)
    loss = float(-np.mean(observed * np.log(clipped) + (1 - observed) * np.log(1 - clipped)))
    ece = sum(
        item.count / len(predicted) * abs(item.mean_probability - item.event_rate)
        for item in curve
    )
    intercept, slope = _calibration_intercept_slope(predicted, observed)

    skill: float | None = None
    if reference_probabilities is not None:
        reference, _ = _validated_arrays(reference_probabilities, outcomes)
        reference_brier = float(np.mean((reference - observed) ** 2))
        if reference_brier > 0:
            skill = 1.0 - brier / reference_brier

    return CalibrationReport(
        sample_size=len(predicted),
        brier_score=brier,
        log_loss=loss,
        expected_calibration_error=ece,
        calibration_intercept=intercept,
        calibration_slope=slope,
        brier_skill_score=skill,
        reliability_curve=curve,
    )


def _validated_arrays(
    probabilities: Sequence[float], outcomes: Sequence[int]
) -> tuple[np.ndarray, np.ndarray]:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be non-empty and equal length")
    predicted = np.asarray(probabilities, dtype=float)
    observed = np.asarray(outcomes, dtype=float)
    if not np.isfinite(predicted).all() or np.any((predicted < 0) | (predicted > 1)):
        raise ValueError("probabilities must be finite and in [0, 1]")
    if not np.isin(observed, (0, 1)).all():
        raise ValueError("outcomes must contain only 0 and 1")
    return predicted, observed


def _reliability_curve(
    probabilities: np.ndarray, outcomes: np.ndarray, bins: int
) -> tuple[ReliabilityBin, ...]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    indices = np.minimum(np.searchsorted(edges, probabilities, side="right") - 1, bins - 1)
    result: list[ReliabilityBin] = []
    for index in range(bins):
        mask = indices == index
        count = int(mask.sum())
        if count:
            result.append(
                ReliabilityBin(
                    lower=float(edges[index]),
                    upper=float(edges[index + 1]),
                    count=count,
                    mean_probability=float(probabilities[mask].mean()),
                    event_rate=float(outcomes[mask].mean()),
                )
            )
    return tuple(result)


def _calibration_intercept_slope(
    probabilities: np.ndarray, outcomes: np.ndarray
) -> tuple[float | None, float | None]:
    if np.unique(outcomes).size < 2 or np.unique(probabilities).size < 2:
        return None, None
    clipped = np.clip(probabilities, _EPSILON, 1.0 - _EPSILON)
    logits = np.log(clipped / (1.0 - clipped))

    def objective(theta: np.ndarray) -> float:
        linear = theta[0] + theta[1] * logits
        fitted = np.empty_like(linear)
        positive = linear >= 0
        fitted[positive] = 1.0 / (1.0 + np.exp(-linear[positive]))
        exponent = np.exp(linear[~positive])
        fitted[~positive] = exponent / (1.0 + exponent)
        fitted = np.clip(fitted, _EPSILON, 1.0 - _EPSILON)
        return float(
            -(outcomes * np.log(fitted) + (1 - outcomes) * np.log(1 - fitted)).sum()
        )

    fit = minimize(objective, np.array([0.0, 1.0]), method="BFGS")
    if not fit.success or not all(math.isfinite(float(value)) for value in fit.x):
        return None, None
    return float(fit.x[0]), float(fit.x[1])
