"""Tests for the prediction reproducibility check (framework §13).

Two levels: version completeness (attribution) vs replayability (attribution +
recorded execution/input lineage).
"""

from dataclasses import dataclass

from qwantej.audit.reproducibility import (
    REQUIRED_LINEAGE_FIELDS,
    REQUIRED_VERSION_FIELDS,
    check_reproducibility,
)


@dataclass
class FakePrediction:
    """A stand-in exposing the version spine and lineage — the check is
    decoupled from the ORM, so a plain object is a valid input. Defaults are a
    fully lineaged prediction."""

    model_version_id: object | None = "m-1"
    feature_version: str | None = "fs-1"
    calibration_version: str | None = "cal-1"
    risk_policy_version: str | None = "risk-1"
    optimiser_version: str | None = "opt-1"
    code_commit: str | None = "abc123"
    model_run_id: object | None = "run-1"
    input_snapshot_ref: str | None = "snapshots/run-1/input.json"
    input_snapshot_hash: str | None = "sha256:deadbeef"


def test_fully_lineaged_prediction_is_ready_but_not_verified() -> None:
    report = check_reproducibility(FakePrediction())
    assert report.version_complete is True
    assert report.lineage_complete is True
    assert report.replay_verified is False
    assert report.reproducible is False
    assert report.missing_version_fields == ()
    assert report.missing_lineage_fields == ()
    assert bool(report) is False


def test_successful_external_replay_certifies_reproducibility() -> None:
    report = check_reproducibility(FakePrediction(), replay_verified=True)
    assert report.reproducible is True
    assert report.replayable is True
    assert bool(report) is True


def test_version_complete_but_no_lineage_is_not_replayable() -> None:
    # The core distinction: naming a model *version* without the *run* that
    # produced the parameters is attribution, not reproduction.
    report = check_reproducibility(
        FakePrediction(model_run_id=None, input_snapshot_ref=None, input_snapshot_hash=None)
    )
    assert report.version_complete is True
    assert report.lineage_complete is False
    assert report.reproducible is False
    assert set(report.missing_lineage_fields) == set(REQUIRED_LINEAGE_FIELDS)
    assert bool(report) is False


def test_reports_each_missing_version_field() -> None:
    report = check_reproducibility(
        FakePrediction(feature_version=None, code_commit="   ")
    )
    assert report.version_complete is False
    assert report.lineage_complete is False
    assert report.reproducible is False
    assert set(report.missing_version_fields) == {"feature_version", "code_commit"}


def test_blank_and_none_both_count_as_missing() -> None:
    report = check_reproducibility(
        FakePrediction(
            model_version_id=None, feature_version="", calibration_version=None,
            risk_policy_version=None, optimiser_version=None, code_commit=None,
            model_run_id="", input_snapshot_ref="", input_snapshot_hash=None,
        )
    )
    assert set(report.missing_version_fields) == set(REQUIRED_VERSION_FIELDS)
    assert set(report.missing_lineage_fields) == set(REQUIRED_LINEAGE_FIELDS)


def test_missing_order_follows_canonical_fields() -> None:
    report = check_reproducibility(
        FakePrediction(
            model_version_id=None, feature_version=None, calibration_version=None,
            risk_policy_version=None, optimiser_version=None, code_commit=None,
            model_run_id=None, input_snapshot_ref=None, input_snapshot_hash=None,
        )
    )
    assert report.missing_version_fields == REQUIRED_VERSION_FIELDS
    assert report.missing_lineage_fields == REQUIRED_LINEAGE_FIELDS
