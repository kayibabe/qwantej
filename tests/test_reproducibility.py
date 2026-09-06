"""Tests for the prediction reproducibility check (framework §13)."""

from dataclasses import dataclass

from qwantej.audit.reproducibility import (
    REQUIRED_VERSION_FIELDS,
    check_reproducibility,
)


@dataclass
class FakePrediction:
    """A stand-in exposing the version spine — the check is decoupled from
    the ORM, so a plain object is a valid input."""

    model_version_id: object | None = "m-1"
    feature_version: str | None = "fs-1"
    calibration_version: str | None = "cal-1"
    risk_policy_version: str | None = "risk-1"
    optimiser_version: str | None = "opt-1"
    code_commit: str | None = "abc123"


def test_fully_versioned_prediction_is_reproducible() -> None:
    report = check_reproducibility(FakePrediction())
    assert report.reproducible is True
    assert report.missing == ()
    assert bool(report) is True


def test_reports_each_missing_field() -> None:
    report = check_reproducibility(
        FakePrediction(feature_version=None, code_commit="   ")
    )
    assert report.reproducible is False
    assert set(report.missing) == {"feature_version", "code_commit"}
    assert bool(report) is False


def test_blank_and_none_both_count_as_missing() -> None:
    report = check_reproducibility(
        FakePrediction(
            model_version_id=None, feature_version="", calibration_version=None,
            risk_policy_version=None, optimiser_version=None, code_commit=None,
        )
    )
    assert set(report.missing) == set(REQUIRED_VERSION_FIELDS)


def test_missing_order_follows_required_fields() -> None:
    # The report preserves the canonical field order for stable audit output.
    report = check_reproducibility(
        FakePrediction(
            model_version_id=None, feature_version=None, calibration_version=None,
            risk_policy_version=None, optimiser_version=None, code_commit=None,
        )
    )
    assert report.missing == REQUIRED_VERSION_FIELDS
