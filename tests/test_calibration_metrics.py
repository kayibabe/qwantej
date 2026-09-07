"""Numerical sanity and boundary tests for Phase 4 calibration monitoring."""

import math

import pytest

from qwantej.calibration import calibration_report


def test_brier_log_loss_ece_and_skill_match_closed_form() -> None:
    report = calibration_report(
        [0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1],
        reference_probabilities=[0.5, 0.5, 0.5, 0.5], bins=2,
    )
    assert report.sample_size == 4
    assert report.brier_score == pytest.approx(0.025)
    assert report.log_loss == pytest.approx(
        -(math.log(0.9) + math.log(0.8) + math.log(0.8) + math.log(0.9)) / 4
    )
    assert report.expected_calibration_error == pytest.approx(0.15)
    assert report.brier_skill_score == pytest.approx(0.9)
    assert sum(item.count for item in report.reliability_curve) == 4


def test_probability_one_is_in_final_bin() -> None:
    report = calibration_report([0.0, 1.0], [0, 1], bins=5)
    assert sum(item.count for item in report.reliability_curve) == 2


@pytest.mark.parametrize(
    "probabilities,outcomes",
    [([], []), ([0.5], []), ([float("nan")], [1]), ([1.1], [1]), ([0.5], [2])],
)
def test_invalid_monitoring_inputs_rejected(
    probabilities: list[float], outcomes: list[int]
) -> None:
    with pytest.raises(ValueError):
        calibration_report(probabilities, outcomes)
