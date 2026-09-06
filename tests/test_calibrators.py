"""Phase 4 calibrator fitting, fallback, and point-in-time leakage tests."""

from datetime import UTC, datetime, timedelta

import pytest

from qwantej.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    CalibrationSegment,
    FittedCalibrator,
    calibrate_binary,
    calibrate_match_result,
    fit_calibrator,
    select_calibrator,
)
from qwantej.models.probabilities import MatchResultProbs

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def _observations(*, future_outcome: int = 0) -> list[CalibrationObservation]:
    observations = [
        CalibrationObservation(
            raw_probability=0.1 + 0.8 * (index % 10) / 9,
            outcome=1 if index % 4 in (0, 1) else 0,
            predicted_at=AS_OF - timedelta(days=60 - index),
            outcome_observed_at=AS_OF - timedelta(days=59 - index),
        )
        for index in range(40)
    ]
    observations.extend(
        CalibrationObservation(
            raw_probability=0.99,
            outcome=future_outcome,
            predicted_at=AS_OF - timedelta(hours=1),
            outcome_observed_at=AS_OF + timedelta(days=index + 1),
        )
        for index in range(5)
    )
    return observations


@pytest.mark.parametrize("method", list(CalibrationMethod))
def test_fit_predicts_finite_unit_probabilities(method: CalibrationMethod) -> None:
    result = fit_calibrator(
        _observations(), method=method, version="cal-v1",
        trained_as_of=AS_OF, minimum_sample_size=30,
    )
    assert result.calibrator.sample_size == 40
    assert result.excluded_future_outcomes == 5
    assert 0 <= result.calibrator.predict(0.4) <= 1


def test_future_outcomes_cannot_change_fitted_calibrator() -> None:
    first = fit_calibrator(
        _observations(future_outcome=0), method=CalibrationMethod.PLATT,
        version="cal-v1", trained_as_of=AS_OF, minimum_sample_size=30,
    )
    second = fit_calibrator(
        _observations(future_outcome=1), method=CalibrationMethod.PLATT,
        version="cal-v1", trained_as_of=AS_OF, minimum_sample_size=30,
    )
    assert first.calibrator.parameters == pytest.approx(second.calibrator.parameters)


def test_sparse_segment_falls_back_to_eligible_parent() -> None:
    global_calibrator = _artifact("global", CalibrationSegment(), AS_OF - timedelta(days=2))
    market_calibrator = _artifact(
        "market", CalibrationSegment(market="1X2"), AS_OF - timedelta(days=1)
    )
    future_local = _artifact(
        "future", CalibrationSegment(market="1X2", competition="EPL"),
        AS_OF + timedelta(days=1),
    )
    selected = select_calibrator(
        [global_calibrator, market_calibrator, future_local], market="1X2",
        competition="EPL", model_family="ensemble", decision_as_of=AS_OF,
    )
    assert selected is market_calibrator


def test_no_eligible_calibrator_returns_none() -> None:
    assert select_calibrator(
        [], market="1X2", competition="EPL", model_family="ensemble",
        decision_as_of=AS_OF,
    ) is None


def test_binary_calibration_derives_complement() -> None:
    result = calibrate_binary(0.7, _artifact("binary", CalibrationSegment(), AS_OF))
    assert result.yes + result.no == pytest.approx(1.0)


def test_match_result_calibration_preserves_exhaustive_sum() -> None:
    raw = MatchResultProbs(home=0.5, draw=0.3, away=0.2)
    calibrators = {
        "home": _artifact("home", CalibrationSegment(), AS_OF),
        "draw": FittedCalibrator(
            version="draw", method=CalibrationMethod.PLATT,
            segment=CalibrationSegment(), trained_as_of=AS_OF,
            training_window_start=AS_OF - timedelta(days=30),
            training_window_end=AS_OF - timedelta(days=1), sample_size=100,
            minimum_sample_size=30, parameters=(-0.2, 0.8),
        ),
        "away": _artifact("away", CalibrationSegment(), AS_OF),
    }
    calibrated = calibrate_match_result(raw, calibrators)
    assert sum(calibrated.as_dict().values()) == pytest.approx(1.0)
    assert sum(calibrated.double_chance().as_dict().values()) == pytest.approx(2.0)


def test_match_result_calibration_requires_complete_outcome_set() -> None:
    with pytest.raises(ValueError, match="exactly"):
        calibrate_match_result(
            MatchResultProbs(home=0.5, draw=0.3, away=0.2),
            {"home": _artifact("home", CalibrationSegment(), AS_OF)},
        )


def test_minimum_sample_and_both_classes_are_required() -> None:
    with pytest.raises(ValueError, match="eligible observations"):
        fit_calibrator(
            _observations()[:5], method=CalibrationMethod.PLATT, version="v",
            trained_as_of=AS_OF, minimum_sample_size=30,
        )
    one_class = [
        CalibrationObservation(0.5, 1, AS_OF - timedelta(days=2), AS_OF - timedelta(days=1))
        for _ in range(3)
    ]
    with pytest.raises(ValueError, match="both outcome classes"):
        fit_calibrator(
            one_class, method=CalibrationMethod.PLATT, version="v",
            trained_as_of=AS_OF, minimum_sample_size=2,
        )


def _artifact(
    version: str, segment: CalibrationSegment, trained_as_of: datetime
) -> FittedCalibrator:
    return FittedCalibrator(
        version=version, method=CalibrationMethod.PLATT, segment=segment,
        trained_as_of=trained_as_of,
        training_window_start=trained_as_of - timedelta(days=30),
        training_window_end=trained_as_of - timedelta(days=1),
        sample_size=100, minimum_sample_size=30, parameters=(0.0, 1.0),
    )
