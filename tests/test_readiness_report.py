from datetime import UTC, datetime

from scripts.run_readiness_report import ReadinessEvidence, evaluate_readiness


def _evidence(**overrides):
    values = dict(
        latest_pit_experiment=True,
        experiment_sample_size=30,
        experiment_leakage_rows_rejected=0,
        experiment_metrics_complete=True,
        experiment_metrics={"calibrated_calibration": {"brier_score": 0.2}},
        prediction_count=30,
        predictions_missing_provenance=0,
        settled_prediction_count=30,
        reliability_snapshot_count=1,
        reliability_future_rows_excluded=0,
        champion_model_count=1,
        champion_calibrator_count=1,
        accumulator_count=0,
        live_accumulator_count=0,
    )
    values.update(overrides)
    return ReadinessEvidence(**values)


def test_readiness_passes_only_when_all_evidence_is_present():
    report = evaluate_readiness(
        _evidence(), generated_at=datetime(2026, 9, 12, tzinfo=UTC)
    )
    assert report.ready is True
    assert all(check.passed for check in report.checks)


def test_research_experiment_cannot_pass_pit_check():
    report = evaluate_readiness(_evidence(latest_pit_experiment=False))
    assert report.ready is False
    check = next(item for item in report.checks if item.name == "pit_certified_walk_forward")
    assert check.passed is False


def test_missing_provenance_and_live_accumulator_block_readiness():
    report = evaluate_readiness(
        _evidence(predictions_missing_provenance=1, live_accumulator_count=1)
    )
    blocked = {check.name for check in report.checks if not check.passed}
    assert {"forecast_archive_provenance", "paper_only_boundary"} <= blocked


def test_zero_valued_metrics_are_present_not_missing():
    report = evaluate_readiness(
        _evidence(
            experiment_metrics={
                "calibrated_calibration": {
                    "brier_score": 0.0,
                    "log_loss": 0.0,
                    "expected_calibration_error": 0.0,
                },
                "average_clv": 0.0,
                "roi": 0.0,
            }
        )
    )
    check = next(item for item in report.checks if item.name == "required_metrics_present")
    assert check.passed is True
