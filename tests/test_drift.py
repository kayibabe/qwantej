"""Tests for Phase 9: drift detection (framework §44)."""

from __future__ import annotations

import pytest

from qwantej.performance.drift import (
    CalibrationDriftResult,
    ExecutionDriftResult,
    PredictionDriftResult,
    detect_calibration_drift,
    detect_execution_drift,
    detect_prediction_drift,
)

# ---------------------------------------------------------------------------
# Calibration drift
# ---------------------------------------------------------------------------

class TestDetectCalibrationDrift:
    def _perfect(self) -> tuple[list[float], list[float]]:
        """Perfectly calibrated: p=0.6 → win 60% of the time."""
        probs = [0.6] * 10
        outcomes = [1.0] * 6 + [0.0] * 4
        return probs, outcomes

    def test_no_drift_when_well_calibrated(self) -> None:
        probs, outcomes = self._perfect()
        result = detect_calibration_drift(probs, outcomes, threshold=0.05)
        assert isinstance(result, CalibrationDriftResult)
        assert not result.is_drifted

    def test_drifted_when_over_confident(self) -> None:
        # Predict 0.9 but only win 50% → large MCE
        probs = [0.9] * 20
        outcomes = [1.0] * 10 + [0.0] * 10
        result = detect_calibration_drift(probs, outcomes, threshold=0.05)
        assert result.is_drifted
        assert result.mean_calibration_error > 0.05

    def test_mce_is_nonneg(self) -> None:
        probs = [0.3, 0.5, 0.7, 0.8]
        outcomes = [0.0, 1.0, 1.0, 0.0]
        result = detect_calibration_drift(probs, outcomes)
        assert result.mean_calibration_error >= 0

    def test_slope_near_one_for_good_calibration(self) -> None:
        # Spread across three bins, well-calibrated
        probs = [0.25, 0.25, 0.55, 0.55, 0.80, 0.80]
        outcomes = [0.0, 1.0,  0.0, 1.0,  1.0, 1.0]
        result = detect_calibration_drift(probs, outcomes, n_bins=4)
        assert result.slope > 0   # positive correlation

    def test_rejects_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            detect_calibration_drift([0.5, 0.6], [1.0])

    def test_rejects_empty_inputs(self) -> None:
        with pytest.raises(ValueError):
            detect_calibration_drift([], [])

    def test_rejects_invalid_probability(self) -> None:
        with pytest.raises(ValueError):
            detect_calibration_drift([1.5], [1.0])

    def test_rejects_invalid_outcome(self) -> None:
        with pytest.raises(ValueError):
            detect_calibration_drift([0.5], [0.5])

    def test_n_samples_correct(self) -> None:
        probs = [0.5] * 8
        outcomes = [1.0] * 4 + [0.0] * 4
        result = detect_calibration_drift(probs, outcomes)
        assert result.n_samples == 8

    def test_rejects_nbins_less_than_2(self) -> None:
        with pytest.raises(ValueError, match="n_bins"):
            detect_calibration_drift([0.5], [1.0], n_bins=1)


# ---------------------------------------------------------------------------
# Prediction drift (PSI)
# ---------------------------------------------------------------------------

class TestDetectPredictionDrift:
    def test_no_drift_identical_distributions(self) -> None:
        ref = [0.3, 0.5, 0.7, 0.3, 0.5, 0.7]
        cur = [0.3, 0.5, 0.7, 0.3, 0.5, 0.7]
        result = detect_prediction_drift(ref, cur, threshold=0.10)
        assert isinstance(result, PredictionDriftResult)
        assert result.psi < 0.10
        assert not result.is_drifted

    def test_drift_when_distributions_shift(self) -> None:
        # Reference: centred around 0.3; current: centred around 0.8
        ref = [0.25, 0.30, 0.35] * 20
        cur = [0.75, 0.80, 0.85] * 20
        result = detect_prediction_drift(ref, cur, threshold=0.10)
        assert result.is_drifted
        assert result.psi > 0.25

    def test_psi_is_nonneg(self) -> None:
        ref = [0.4, 0.5, 0.6]
        cur = [0.45, 0.55, 0.65]
        result = detect_prediction_drift(ref, cur)
        assert result.psi >= 0

    def test_counts_correct(self) -> None:
        ref = [0.5] * 5
        cur = [0.5] * 8
        result = detect_prediction_drift(ref, cur)
        assert result.n_reference == 5
        assert result.n_current == 8

    def test_rejects_empty_series(self) -> None:
        with pytest.raises(ValueError):
            detect_prediction_drift([], [0.5])
        with pytest.raises(ValueError):
            detect_prediction_drift([0.5], [])

    def test_rejects_nbins_less_than_2(self) -> None:
        with pytest.raises(ValueError, match="n_bins"):
            detect_prediction_drift([0.5], [0.5], n_bins=1)


# ---------------------------------------------------------------------------
# Execution drift (CLV shift)
# ---------------------------------------------------------------------------

class TestDetectExecutionDrift:
    def test_no_drift_stable_clv(self) -> None:
        ref = [0.02, 0.03, 0.01, 0.02]
        cur = [0.02, 0.02, 0.03, 0.01]
        result = detect_execution_drift(ref, cur, threshold=-0.02)
        assert isinstance(result, ExecutionDriftResult)
        assert not result.is_drifted

    def test_drifted_when_clv_falls(self) -> None:
        ref = [0.04, 0.05, 0.03]          # mean ≈ 0.04
        cur = [-0.03, -0.02, -0.04]       # mean ≈ -0.03  →  shift ≈ -0.07
        result = detect_execution_drift(ref, cur, threshold=-0.02)
        assert result.is_drifted
        assert result.clv_shift < -0.02

    def test_clv_shift_formula(self) -> None:
        ref = [0.0, 0.0, 0.0, 0.0]
        cur = [0.10, 0.10, 0.10, 0.10]
        result = detect_execution_drift(ref, cur)
        assert result.clv_shift == pytest.approx(0.10)

    def test_rejects_empty_series(self) -> None:
        with pytest.raises(ValueError):
            detect_execution_drift([], [0.01])
        with pytest.raises(ValueError):
            detect_execution_drift([0.01], [])

    def test_counts_correct(self) -> None:
        result = detect_execution_drift([0.01] * 3, [0.02] * 5)
        assert result.n_reference == 3
        assert result.n_current == 5
