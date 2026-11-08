import math
from app.services.recalibration import (
    brier_score,
    calibrated_probability,
    expected_calibration_error,
    fit_isotonic,
    log_loss,
)


def test_fit_isotonic_monotone_passthrough():
    samples = [(0.1, 0.0), (0.2, 0.0), (0.3, 1.0), (0.4, 1.0)]
    points = fit_isotonic(samples)
    assert len(points) == 4
    for (x, y) in points:
        assert y in (0.0, 1.0)


def test_fit_isotonic_pools_violations():
    samples = [(0.5, 1.0), (0.6, 0.0)]
    points = fit_isotonic(samples)
    assert len(points) == 1
    assert points[0][1] == 0.5


def test_fit_isotonic_empty():
    assert fit_isotonic([]) == []


def test_fit_isotonic_overconfident_tail_shrinks():
    # High-probability picks hitting far less often than claimed.
    samples = [(0.85, 1.0), (0.85, 1.0), (0.85, 0.0), (0.85, 0.0)]
    points = fit_isotonic(samples)
    assert points[0][1] == 0.5


def test_calibrated_probability_interpolates_and_clamps():
    breakpoints = [(0.5, 0.4), (0.9, 0.7)]
    assert calibrated_probability(breakpoints, 0.1) == 0.4
    assert math.isclose(calibrated_probability(breakpoints, 0.7), 0.55)
    assert calibrated_probability(breakpoints, 0.99) == 0.7
    assert calibrated_probability([], 0.63) == 0.63


def test_scoring_metrics():
    perfect = [(0.9, 1.0), (0.2, 0.0)]
    assert brier_score(perfect) == round((0.01 + 0.04) / 2, 6)
    assert log_loss(perfect) is not None
    # ECE measures calibration, not accuracy: a bin's mean prediction must
    # equal its empirical hit rate for zero error.
    assert expected_calibration_error([(0.5, 1.0), (0.5, 0.0)]) == 0.0
    assert expected_calibration_error(perfect) == 0.15
    assert brier_score([]) is None
    assert log_loss([]) is None
    assert expected_calibration_error([]) is None


def test_log_loss_clips_extremes():
    loss = log_loss([(1.0, 1.0), (0.0, 0.0)])
    assert math.isfinite(loss)
