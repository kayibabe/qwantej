"""Walk-forward metrics, baseline comparison, and leakage regression tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from qwantej.performance import (
    BacktestObservation,
    WalkForwardConfig,
    walk_forward_backtest,
)
from qwantej.value import ValueGatePolicy

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def _rows(count: int = 80) -> list[BacktestObservation]:
    rows: list[BacktestObservation] = []
    for index in range(count):
        decision = START + timedelta(days=index)
        high = index % 2 == 0
        probability = 0.72 if high else 0.28
        # Both classes occur in both probability groups, avoiding separation.
        outcome = int(index % 10 in ((0, 2, 4, 6, 8, 1, 3) if high else (0, 2, 4)))
        rows.append(
            BacktestObservation(
                observation_id=str(index), decision_as_of=decision,
                feature_as_of=decision - timedelta(hours=1),
                outcome_observed_at=decision + timedelta(hours=3),
                model_version="model-v1", raw_probability=probability,
                outcome=outcome, fair_market_probability=0.50,
                executable_odds=2.10, quote_timestamp=decision - timedelta(minutes=15),
                closing_odds=2.0, closing_quote_timestamp=decision + timedelta(hours=2),
                model_probabilities=(probability - 0.02, probability + 0.02),
                data_quality_score=90, league_reliability=70,
                market_reliability=70, probability_change=0.01, drift_score=0.0,
            )
        )
    return rows


def _config() -> WalkForwardConfig:
    return WalkForwardConfig(
        version="walk-v1", model_version="model-v1", minimum_training_size=20,
        test_window_size=10, bootstrap_samples=200, bootstrap_seed=7,
        value_policy=ValueGatePolicy(
            minimum_conservative_probability=0.40, minimum_edge=0.0,
            minimum_expected_value=0.0, minimum_dqs=0,
            minimum_reliability=0, maximum_probability_change=1,
            maximum_model_disagreement=1, extreme_edge_threshold=1,
        ),
    )


def test_walk_forward_report_contains_required_metrics() -> None:
    report = walk_forward_backtest(_rows(), _config())
    assert report.sample_size == 60
    assert len(report.folds) == 6
    assert report.raw_calibration.sample_size == report.sample_size
    assert report.calibrated_calibration.sample_size == report.sample_size
    assert report.market_calibration.sample_size == report.sample_size
    assert report.raw_calibration.brier_skill_score is not None
    assert report.roi_confidence_interval is not None
    assert report.average_clv == pytest.approx(0.05)
    assert report.maximum_drawdown_units >= 0
    assert report.config["version"] == "walk-v1"
    assert json.dumps(report.config)


def test_future_features_prices_and_results_are_counted_and_excluded() -> None:
    rows = _rows()
    rows[3] = replace(rows[3], feature_as_of=rows[3].decision_as_of + timedelta(seconds=1))
    rows[4] = replace(rows[4], quote_timestamp=rows[4].decision_as_of + timedelta(seconds=1))
    rows[5] = replace(rows[5], outcome_observed_at=rows[5].decision_as_of)
    report = walk_forward_backtest(rows, _config())
    assert report.leakage_rows_rejected == 3
    assert report.sample_size < 60


def test_model_versions_are_never_mixed() -> None:
    rows = _rows()
    rows[10] = replace(rows[10], model_version="other-version")
    report = walk_forward_backtest(rows, _config())
    assert report.model_version_rows_rejected == 1
    assert all(fold.training_sample_size >= 20 for fold in report.folds)


def test_missing_market_rows_do_not_enter_baseline_comparison() -> None:
    rows = _rows()
    rows[8] = replace(
        rows[8], fair_market_probability=None, executable_odds=None, quote_timestamp=None
    )
    report = walk_forward_backtest(rows, _config())
    assert report.missing_market_rows == 1
    assert report.market_calibration.sample_size == report.sample_size
    # Price-less historical outcomes still inform the calibrator once settled;
    # they are excluded only from the market-comparison test set.
    assert report.folds[0].training_sample_size == 21


def test_void_or_unsettled_rows_are_excluded_and_reported() -> None:
    rows = _rows()
    rows[8] = replace(rows[8], outcome=None, outcome_observed_at=None)
    report = walk_forward_backtest(rows, _config())
    assert report.unsettled_or_void_rows == 1
    assert report.sample_size < 60


def test_missing_closing_odds_is_reported_without_affecting_decision() -> None:
    rows = _rows()
    rows[40] = replace(rows[40], closing_odds=None, closing_quote_timestamp=None)
    report = walk_forward_backtest(rows, _config())
    assert report.missing_closing_odds_rows >= 1


def test_pit_certified_true_when_all_observations_carry_snapshot_ref() -> None:
    rows = [
        replace(obs, snapshot_ref=f"feature-snapshot:00000000-0000-0000-0000-{i:012d}")
        for i, obs in enumerate(_rows())
    ]
    report = walk_forward_backtest(rows, _config())
    assert report.pit_certified is True


def test_pit_certified_false_when_any_observation_lacks_snapshot_ref() -> None:
    rows = _rows()
    report = walk_forward_backtest(rows, _config())
    assert report.pit_certified is False


def test_pit_certified_false_when_one_observation_missing_ref() -> None:
    rows = [
        replace(obs, snapshot_ref=f"feature-snapshot:00000000-0000-0000-0000-{i:012d}")
        for i, obs in enumerate(_rows())
    ]
    rows[5] = replace(rows[5], snapshot_ref=None)
    report = walk_forward_backtest(rows, _config())
    assert report.pit_certified is False


def test_snapshot_ref_format_is_validated() -> None:
    row = _rows()[0]
    with pytest.raises(ValueError, match="feature-snapshot:"):
        replace(row, snapshot_ref="not-a-valid-ref")


def test_snapshot_ref_with_invalid_uuid_suffix_is_rejected() -> None:
    row = _rows()[0]
    with pytest.raises(ValueError, match="valid UUID"):
        replace(row, snapshot_ref="feature-snapshot:not-a-uuid")


def test_pit_certified_false_for_leakage_rejected_row_without_ref() -> None:
    """pit_certified is False even when only the leakage-rejected rows lack refs.

    The flag is conservative: it covers all supplied observations, not just the
    subset that passes PIT and market filters.  A row with future features is
    properly rejected by the evaluator but still downgrades certification.
    """
    rows = [
        replace(obs, snapshot_ref=f"feature-snapshot:00000000-0000-0000-0000-{i:012d}")
        for i, obs in enumerate(_rows())
    ]
    # Make one row fail PIT (future feature_as_of) AND remove its snapshot_ref.
    future_row = replace(
        rows[0],
        feature_as_of=rows[0].decision_as_of + timedelta(seconds=1),
        snapshot_ref=None,
    )
    rows[0] = future_row
    report = walk_forward_backtest(rows, _config())
    assert report.leakage_rows_rejected >= 1
    assert report.pit_certified is False


def test_malformed_closing_quote_is_excluded_from_clv_not_decision() -> None:
    rows = _rows()
    rows[40] = replace(rows[40], closing_quote_timestamp=None)
    report = walk_forward_backtest(rows, _config())
    assert report.sample_size == 60
    assert report.leakage_rows_rejected == 0
    assert report.missing_closing_odds_rows >= 1


def test_bootstrap_is_reproducible_from_recorded_seed() -> None:
    first = walk_forward_backtest(_rows(), _config())
    second = walk_forward_backtest(_rows(), _config())
    assert first.roi_confidence_interval == second.roi_confidence_interval


def test_duplicate_ids_and_insufficient_history_fail_closed() -> None:
    duplicate = _rows(30)
    duplicate[1] = replace(duplicate[1], observation_id=duplicate[0].observation_id)
    with pytest.raises(ValueError, match="unique"):
        walk_forward_backtest(duplicate, _config())
    with pytest.raises(ValueError, match="not enough"):
        walk_forward_backtest(_rows(20), _config())
