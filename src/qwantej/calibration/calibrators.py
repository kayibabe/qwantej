"""Point-in-time-safe binary probability calibrators (framework §18)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression

from qwantej.models.probabilities import BinaryProbs, MatchResultProbs

_EPSILON = 1e-12


class CalibrationMethod(StrEnum):
    PLATT = "platt"
    ISOTONIC = "isotonic"


@dataclass(frozen=True)
class CalibrationObservation:
    raw_probability: float
    outcome: int
    predicted_at: datetime
    outcome_observed_at: datetime

    def __post_init__(self) -> None:
        _probability("raw_probability", self.raw_probability)
        if self.outcome not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got {self.outcome}")
        _aware("predicted_at", self.predicted_at)
        _aware("outcome_observed_at", self.outcome_observed_at)
        if self.outcome_observed_at < self.predicted_at:
            raise ValueError("outcome_observed_at cannot precede predicted_at")


@dataclass(frozen=True)
class CalibrationSegment:
    """Optional segment dimensions; ``None`` means a broader parent."""

    market: str | None = None
    competition: str | None = None
    model_family: str | None = None

    @property
    def specificity(self) -> int:
        dimensions = (self.market, self.competition, self.model_family)
        return sum(value is not None for value in dimensions)

    def matches(self, *, market: str, competition: str, model_family: str) -> bool:
        return (
            (self.market is None or self.market == market)
            and (self.competition is None or self.competition == competition)
            and (self.model_family is None or self.model_family == model_family)
        )


@dataclass(frozen=True)
class FittedCalibrator:
    version: str
    method: CalibrationMethod
    segment: CalibrationSegment
    trained_as_of: datetime
    training_window_start: datetime
    training_window_end: datetime
    sample_size: int
    minimum_sample_size: int
    # Platt: (intercept, slope). Isotonic: flattened x/y knot pairs.
    parameters: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("calibrator version must not be blank")
        _aware("trained_as_of", self.trained_as_of)
        _aware("training_window_start", self.training_window_start)
        _aware("training_window_end", self.training_window_end)
        if self.training_window_start > self.training_window_end:
            raise ValueError("training window start must not exceed end")
        if self.training_window_end > self.trained_as_of:
            raise ValueError("training data cannot extend beyond trained_as_of")
        if self.minimum_sample_size < 2 or self.sample_size < self.minimum_sample_size:
            raise ValueError("calibrator does not meet its minimum sample size")
        if not all(math.isfinite(value) for value in self.parameters):
            raise ValueError("calibrator parameters must be finite")
        if self.method is CalibrationMethod.PLATT and len(self.parameters) != 2:
            raise ValueError("Platt calibrator requires intercept and slope")
        if self.method is CalibrationMethod.ISOTONIC and (
            len(self.parameters) < 4 or len(self.parameters) % 2
        ):
            raise ValueError("isotonic calibrator requires at least two x/y knots")

    def predict(self, raw_probability: float) -> float:
        _probability("raw_probability", raw_probability)
        if self.method is CalibrationMethod.PLATT:
            intercept, slope = self.parameters
            value = _sigmoid(intercept + slope * _logit(raw_probability))
        else:
            xs = np.asarray(self.parameters[0::2])
            ys = np.asarray(self.parameters[1::2])
            value = float(np.interp(raw_probability, xs, ys))
        return min(max(value, 0.0), 1.0)

    def parameters_dict(self) -> dict[str, object]:
        if self.method is CalibrationMethod.PLATT:
            return {"intercept": self.parameters[0], "slope": self.parameters[1]}
        return {
            "x_thresholds": list(self.parameters[0::2]),
            "y_thresholds": list(self.parameters[1::2]),
        }


@dataclass(frozen=True)
class CalibrationFitResult:
    calibrator: FittedCalibrator
    excluded_future_outcomes: int


GLOBAL_SEGMENT = CalibrationSegment()


def fit_calibrator(
    observations: Iterable[CalibrationObservation],
    *,
    method: CalibrationMethod,
    version: str,
    trained_as_of: datetime,
    segment: CalibrationSegment = GLOBAL_SEGMENT,
    minimum_sample_size: int = 30,
) -> CalibrationFitResult:
    """Fit only from outcomes observable by ``trained_as_of``."""
    _aware("trained_as_of", trained_as_of)
    if minimum_sample_size < 2:
        raise ValueError("minimum_sample_size must be at least 2")
    supplied = tuple(observations)
    eligible = tuple(o for o in supplied if o.outcome_observed_at <= trained_as_of)
    if len(eligible) < minimum_sample_size:
        raise ValueError(
            f"need at least {minimum_sample_size} eligible observations, got {len(eligible)}"
        )
    outcomes = np.asarray([o.outcome for o in eligible], dtype=float)
    if np.unique(outcomes).size < 2:
        raise ValueError("calibration fitting requires both outcome classes")
    probabilities = np.asarray([o.raw_probability for o in eligible], dtype=float)

    if method is CalibrationMethod.PLATT:
        logits = np.asarray([_logit(float(p)) for p in probabilities])

        def objective(theta: np.ndarray) -> float:
            calibrated = np.clip(
                _sigmoid_array(theta[0] + theta[1] * logits), _EPSILON, 1 - _EPSILON
            )
            return float(
                -(outcomes * np.log(calibrated) + (1 - outcomes) * np.log(1 - calibrated)).sum()
            )

        fitted = minimize(objective, np.array([0.0, 1.0]), method="BFGS")
        if not fitted.success or not np.isfinite(fitted.x).all():
            raise ValueError(f"Platt calibration fit failed: {fitted.message}")
        parameters: tuple[float, ...] = (float(fitted.x[0]), float(fitted.x[1]))
    elif method is CalibrationMethod.ISOTONIC:
        if np.unique(probabilities).size < 2:
            raise ValueError("isotonic calibration requires at least two distinct probabilities")
        estimator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        estimator.fit(probabilities, outcomes)
        parameters = tuple(
            value
            for pair in zip(estimator.X_thresholds_, estimator.y_thresholds_, strict=True)
            for value in (float(pair[0]), float(pair[1]))
        )
    else:
        raise ValueError(f"unsupported calibration method {method!r}")

    return CalibrationFitResult(
        calibrator=FittedCalibrator(
            version=version,
            method=method,
            segment=segment,
            trained_as_of=trained_as_of,
            training_window_start=min(o.predicted_at for o in eligible),
            training_window_end=max(o.outcome_observed_at for o in eligible),
            sample_size=len(eligible),
            minimum_sample_size=minimum_sample_size,
            parameters=parameters,
        ),
        excluded_future_outcomes=len(supplied) - len(eligible),
    )


def select_calibrator(
    calibrators: Iterable[FittedCalibrator],
    *,
    market: str,
    competition: str,
    model_family: str,
    decision_as_of: datetime,
) -> FittedCalibrator | None:
    """Choose the most specific eligible calibrator, falling back to parents."""
    _aware("decision_as_of", decision_as_of)
    eligible = [
        calibrator
        for calibrator in calibrators
        if calibrator.trained_as_of <= decision_as_of
        and calibrator.segment.matches(
            market=market, competition=competition, model_family=model_family
        )
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item.segment.specificity, item.trained_as_of))


def calibrate_binary(
    raw_yes_probability: float, calibrator: FittedCalibrator
) -> BinaryProbs:
    """Calibrate one side and derive its complement so the pair remains coherent."""
    yes = calibrator.predict(raw_yes_probability)
    return BinaryProbs(yes=yes, no=1.0 - yes)


def calibrate_match_result(
    raw: MatchResultProbs,
    calibrators: Mapping[str, FittedCalibrator],
) -> MatchResultProbs:
    """Calibrate 1X2 jointly and renormalize the exhaustive outcome vector."""
    required = {"home", "draw", "away"}
    if set(calibrators) != required:
        raise ValueError("1X2 calibration requires exactly home, draw and away calibrators")
    adjusted = {
        selection: calibrators[selection].predict(probability)
        for selection, probability in raw.as_dict().items()
    }
    total = sum(adjusted.values())
    if total <= 0:
        raise ValueError("calibrated 1X2 outcomes have zero total probability")
    return MatchResultProbs(
        home=adjusted["home"] / total,
        draw=adjusted["draw"] / total,
        away=adjusted["away"] / total,
    )


def _probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1], got {value}")


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _logit(probability: float) -> float:
    clipped = min(max(probability, _EPSILON), 1.0 - _EPSILON)
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _sigmoid_array(values: np.ndarray) -> np.ndarray:
    positive = values >= 0
    result = np.empty_like(values)
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    result[~positive] = exp_values / (1.0 + exp_values)
    return result
