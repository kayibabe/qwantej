"""Exact decision-rule tests for the Phase 4 P_cons policy."""

import math

import pytest

from qwantej.calibration import ConservativePolicy


def test_exact_haircut_formula_and_audit_breakdown() -> None:
    policy = ConservativePolicy()
    result = policy.apply(
        0.7, effective_sample_size=100, model_probabilities=[0.65, 0.75],
        data_quality_score=90, calibration_error=0.03, drift_score=0.1,
    )
    sampling = policy.one_sided_z * math.sqrt(0.7 * 0.3 / 100)
    expected_haircut = sampling + 0.025 + 0.005 + 0.015 + 0.005
    assert result.uncertainty_measure == pytest.approx(expected_haircut)
    assert result.conservative_probability == pytest.approx(0.7 - expected_haircut)
    assert result.policy_version == "pcons-v1"


def test_more_uncertainty_never_increases_p_cons() -> None:
    policy = ConservativePolicy()
    baseline = policy.apply(
        0.7, effective_sample_size=500, model_probabilities=[0.69, 0.71],
        data_quality_score=100, calibration_error=0.0, drift_score=0.0,
    )
    uncertain = policy.apply(
        0.7, effective_sample_size=20, model_probabilities=[0.4, 0.9],
        data_quality_score=50, calibration_error=0.2, drift_score=0.5,
    )
    assert uncertain.conservative_probability < baseline.conservative_probability
    assert uncertain.conservative_probability <= uncertain.calibrated_probability


def test_haircut_floors_probability_at_zero() -> None:
    result = ConservativePolicy().apply(
        0.05, effective_sample_size=1, model_probabilities=[0.0, 1.0],
        data_quality_score=0, calibration_error=1.0, drift_score=1.0,
    )
    assert result.conservative_probability == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"effective_sample_size": 0},
        {"data_quality_score": 101},
        {"calibration_error": float("nan")},
        {"drift_score": -0.1},
        {"model_probabilities": []},
    ],
)
def test_invalid_uncertainty_inputs_rejected(kwargs: dict[str, object]) -> None:
    valid: dict[str, object] = {
        "effective_sample_size": 100,
        "model_probabilities": [0.6, 0.7],
        "data_quality_score": 90,
        "calibration_error": 0.02,
        "drift_score": 0.0,
    }
    valid.update(kwargs)
    with pytest.raises(ValueError):
        ConservativePolicy().apply(0.65, **valid)  # type: ignore[arg-type]
