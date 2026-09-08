"""Tests for the calibration-only walk-forward evaluator.

Verifies:
- Basic walk-forward produces calibration metrics with pit_certified=False
- feature_as_of > decision_as_of → temporal rejection, excluded from evaluation
- outcome_observed_at <= decision_as_of → temporal rejection, excluded
- Model version mismatch → version rejection, excluded
- Zero temporal_order_rejections does NOT imply PIT availability (documented)
- CalibrationOnlyReport always carries pit_certified=False and research_mode=True
- CalibrationOnlyConfig.as_dict always embeds pit_certified=False, research_mode=True
- Duplicate observation_id → ValueError
- Insufficient valid rows → ValueError
- No observations → ValueError
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qwantej.calibration import CalibrationMethod
from qwantej.performance.calibration_backtest import (
    CalibrationObservationRow,
    CalibrationOnlyConfig,
    calibration_only_walk_forward,
)

MODEL_VERSION = "poisson+elo-ensemble:1.0.0"
CONFIG_VERSION = "test:1.0.0"

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _obs(
    idx: int,
    *,
    raw_prob: float = 0.55,
    outcome: int = 1,
    decision_offset_days: int = 0,
    feature_offset_hours: int = -2,
    outcome_offset_hours: int = 3,
    model_version: str = MODEL_VERSION,
) -> CalibrationObservationRow:
    decision = BASE + timedelta(days=decision_offset_days)
    return CalibrationObservationRow(
        observation_id=f"obs-{idx:04d}",
        decision_as_of=decision,
        feature_as_of=decision + timedelta(hours=feature_offset_hours),
        outcome_observed_at=decision + timedelta(hours=outcome_offset_hours),
        model_version=model_version,
        raw_probability=raw_prob,
        outcome=outcome,
    )


def _enough_obs(n: int = 60) -> list[CalibrationObservationRow]:
    """Return *n* valid observations spread over *n* days."""
    return [
        _obs(i, raw_prob=0.4 + (i % 3) * 0.1, outcome=i % 2, decision_offset_days=i)
        for i in range(n)
    ]


def _default_config(min_train: int = 30, test_window: int = 5) -> CalibrationOnlyConfig:
    return CalibrationOnlyConfig(
        version=CONFIG_VERSION,
        model_version=MODEL_VERSION,
        calibration_method=CalibrationMethod.ISOTONIC,
        minimum_training_size=min_train,
        test_window_size=test_window,
    )


# --- Config -------------------------------------------------------------------


class TestCalibrationOnlyConfig:
    def test_as_dict_always_research_flags(self) -> None:
        cfg = _default_config()
        d = cfg.as_dict()
        assert d["pit_certified"] is False
        assert d["research_mode"] is True

    def test_as_dict_method_is_string(self) -> None:
        cfg = CalibrationOnlyConfig(
            version="v1",
            model_version="m1",
            calibration_method=CalibrationMethod.PLATT,
        )
        assert cfg.as_dict()["calibration_method"] == "platt"

    def test_blank_version_raises(self) -> None:
        with pytest.raises(ValueError, match="version"):
            CalibrationOnlyConfig(version="  ", model_version="m1")

    def test_blank_model_version_raises(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            CalibrationOnlyConfig(version="v1", model_version="  ")

    def test_minimum_training_size_too_small(self) -> None:
        with pytest.raises(ValueError, match="minimum_training_size"):
            CalibrationOnlyConfig(version="v1", model_version="m1", minimum_training_size=1)

    def test_test_window_size_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="test_window_size"):
            CalibrationOnlyConfig(version="v1", model_version="m1", test_window_size=0)


# --- Input validation ---------------------------------------------------------


class TestInputValidation:
    def test_empty_observations_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one observation"):
            calibration_only_walk_forward([], _default_config())

    def test_duplicate_ids_raises(self) -> None:
        obs = _enough_obs(40)
        obs[5] = CalibrationObservationRow(
            observation_id=obs[0].observation_id,
            decision_as_of=obs[5].decision_as_of,
            feature_as_of=obs[5].feature_as_of,
            outcome_observed_at=obs[5].outcome_observed_at,
            model_version=MODEL_VERSION,
            raw_probability=0.5,
            outcome=0,
        )
        with pytest.raises(ValueError, match="unique"):
            calibration_only_walk_forward(obs, _default_config())

    def test_insufficient_valid_rows_raises(self) -> None:
        obs = _enough_obs(10)
        with pytest.raises(ValueError, match="not enough temporally-valid rows"):
            calibration_only_walk_forward(obs, _default_config(min_train=30))


# --- Rejection accounting -----------------------------------------------------


class TestRejectionAccounting:
    def test_model_version_mismatch_is_rejected(self) -> None:
        obs = _enough_obs(60)
        obs[0] = _obs(999, model_version="other-model:1.0.0")
        report = calibration_only_walk_forward(obs, _default_config())
        assert report.model_version_rows_rejected == 1

    def test_feature_as_of_after_decision_is_temporal_rejection(self) -> None:
        obs = _enough_obs(60)
        # Replace one valid obs with one that has feature_as_of > decision_as_of
        bad = _obs(999, feature_offset_hours=+1)
        obs.append(bad)
        report = calibration_only_walk_forward(obs, _default_config())
        assert report.temporal_order_rejections >= 1
        # The bad obs must not appear in evaluated sample
        assert report.sample_size <= len(obs) - 1

    def test_outcome_observed_before_decision_is_temporal_rejection(self) -> None:
        obs = _enough_obs(60)
        bad = _obs(999, outcome_offset_hours=-1)
        obs.append(bad)
        report = calibration_only_walk_forward(obs, _default_config())
        assert report.temporal_order_rejections >= 1


# --- Report invariants --------------------------------------------------------


class TestReportInvariants:
    def test_report_pit_certified_always_false(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        assert report.pit_certified is False

    def test_report_research_mode_always_true(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        assert report.research_mode is True

    def test_zero_temporal_rejections_does_not_imply_pit(self) -> None:
        """Temporal ordering being clean does NOT imply historical availability."""
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        # Even when no rows are rejected on temporal grounds, we are NOT PIT-certified
        assert report.temporal_order_rejections == 0
        assert report.pit_certified is False, (
            "Zero temporal_order_rejections must not imply pit_certified=True"
        )

    def test_config_dict_embedded_in_report(self) -> None:
        cfg = _default_config()
        report = calibration_only_walk_forward(_enough_obs(), cfg)
        assert report.config["version"] == CONFIG_VERSION
        assert report.config["pit_certified"] is False
        assert report.config["research_mode"] is True

    def test_sample_size_matches_evaluated_folds(self) -> None:
        cfg = _default_config(min_train=20, test_window=5)
        report = calibration_only_walk_forward(_enough_obs(60), cfg)
        assert report.sample_size == sum(f.evaluated_rows for f in report.folds)

    def test_start_and_end_are_aware(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        assert report.start.tzinfo is not None
        assert report.end.tzinfo is not None

    def test_raw_calibration_populated(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        cal = report.raw_calibration
        assert 0 <= cal.brier_score <= 1
        assert 0 <= cal.expected_calibration_error <= 1

    def test_calibrated_calibration_populated(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        cal = report.calibrated_calibration
        assert 0 <= cal.brier_score <= 1

    def test_folds_training_as_of_monotone(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        cutoffs = [f.training_as_of for f in report.folds]
        assert cutoffs == sorted(cutoffs)

    def test_per_fold_brier_finite(self) -> None:
        report = calibration_only_walk_forward(_enough_obs(), _default_config())
        for fold in report.folds:
            assert 0 <= fold.raw_brier <= 1
            assert 0 <= fold.calibrated_brier <= 1


# --- CalibrationObservationRow validation ------------------------------------


class TestObservationRowValidation:
    def test_blank_id_raises(self) -> None:
        with pytest.raises(ValueError, match="observation_id"):
            CalibrationObservationRow(
                observation_id="  ",
                decision_as_of=BASE,
                feature_as_of=BASE - timedelta(hours=2),
                outcome_observed_at=BASE + timedelta(hours=2),
                model_version=MODEL_VERSION,
                raw_probability=0.5,
                outcome=1,
            )

    def test_naive_decision_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="decision_as_of"):
            CalibrationObservationRow(
                observation_id="x",
                decision_as_of=datetime(2026, 1, 1),
                feature_as_of=BASE - timedelta(hours=2),
                outcome_observed_at=BASE + timedelta(hours=2),
                model_version=MODEL_VERSION,
                raw_probability=0.5,
                outcome=1,
            )

    def test_outcome_not_binary_raises(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            CalibrationObservationRow(
                observation_id="x",
                decision_as_of=BASE,
                feature_as_of=BASE - timedelta(hours=2),
                outcome_observed_at=BASE + timedelta(hours=2),
                model_version=MODEL_VERSION,
                raw_probability=0.5,
                outcome=2,
            )
