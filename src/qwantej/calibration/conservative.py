"""Versioned conservative-probability policy (P_cal -> P_cons, framework §19)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import pstdev


@dataclass(frozen=True)
class ConservativeProbability:
    calibrated_probability: float
    conservative_probability: float
    uncertainty_measure: float
    sampling_uncertainty: float
    disagreement_penalty: float
    data_quality_penalty: float
    calibration_penalty: float
    drift_penalty: float
    policy_version: str


@dataclass(frozen=True)
class ConservativePolicy:
    """Auditable v1 haircut whose terms are all probability-point penalties."""

    version: str = "pcons-v1"
    one_sided_z: float = 1.2815515655446004  # 80% one-sided normal bound
    disagreement_weight: float = 0.50
    data_quality_weight: float = 0.05
    calibration_error_weight: float = 0.50
    drift_weight: float = 0.05

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("policy version must not be blank")
        for name, value in (
            ("one_sided_z", self.one_sided_z),
            ("disagreement_weight", self.disagreement_weight),
            ("data_quality_weight", self.data_quality_weight),
            ("calibration_error_weight", self.calibration_error_weight),
            ("drift_weight", self.drift_weight),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative, got {value}")

    def apply(
        self,
        calibrated_probability: float,
        *,
        effective_sample_size: float,
        model_probabilities: Sequence[float],
        data_quality_score: float,
        calibration_error: float,
        drift_score: float,
    ) -> ConservativeProbability:
        _unit("calibrated_probability", calibrated_probability)
        _unit("calibration_error", calibration_error)
        _unit("drift_score", drift_score)
        if not math.isfinite(effective_sample_size) or effective_sample_size <= 0:
            raise ValueError("effective_sample_size must be finite and positive")
        if not math.isfinite(data_quality_score) or not 0 <= data_quality_score <= 100:
            raise ValueError("data_quality_score must be finite and in [0, 100]")
        if not model_probabilities:
            raise ValueError("at least one model probability is required")
        for probability in model_probabilities:
            _unit("model probability", probability)

        sampling = self.one_sided_z * math.sqrt(
            calibrated_probability * (1.0 - calibrated_probability) / effective_sample_size
        )
        disagreement = self.disagreement_weight * (
            pstdev(model_probabilities) if len(model_probabilities) > 1 else 0.0
        )
        data = self.data_quality_weight * (1.0 - data_quality_score / 100.0)
        calibration = self.calibration_error_weight * calibration_error
        drift = self.drift_weight * drift_score
        haircut = sampling + disagreement + data + calibration + drift
        return ConservativeProbability(
            calibrated_probability=calibrated_probability,
            conservative_probability=max(0.0, calibrated_probability - haircut),
            uncertainty_measure=haircut,
            sampling_uncertainty=sampling,
            disagreement_penalty=disagreement,
            data_quality_penalty=data,
            calibration_penalty=calibration,
            drift_penalty=drift,
            policy_version=self.version,
        )


def _unit(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1], got {value}")
