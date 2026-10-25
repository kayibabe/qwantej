from datetime import datetime, timedelta, timezone

from app.services.score_distribution_evaluation import (
    evaluate_chronological_rows,
    evaluate_logistic_calibration_holdout,
    evaluate_snapshot_capture_readiness,
    evaluate_score_rate_snapshots,
)


def _row(match_id: int, day: int, probability: float, outcome: int) -> dict:
    return {
        "match_id": match_id,
        "market": "home_win",
        "probability": probability,
        "kickoff_at": datetime(2026, 1, day, 12, tzinfo=timezone.utc),
        "outcome": outcome,
        "competition_id": 1,
    }


def test_expanding_climatology_uses_only_earlier_kickoff_dates():
    rows = [
        _row(1, 1, 0.8, 1),
        _row(2, 2, 0.7, 1),
        _row(3, 2, 0.3, 0),
        _row(4, 3, 0.6, 1),
    ]

    report = evaluate_chronological_rows(rows, min_baseline_history=1)

    baseline = report["markets"]["home_win"]["expanding_prior_climatology"]
    assert baseline["n"] == 3
    assert report["match_count"] == 4
    assert report["calendar_years"]["2026"]["home_win"]["n"] == 4
    assert report["chronology"]["baselines_use_earlier_utc_kickoff_dates_only"] is True


def test_empty_chronological_evaluation_is_well_formed():
    report = evaluate_chronological_rows([])
    assert report["status"] == "completed"
    assert report["prediction_count"] == 0
    assert report["kickoff_date_range"] is None
    assert report["markets"] == {}


def test_latest_pre_match_forecast_is_selected_per_market():
    early = _row(1, 1, 0.4, 1)
    early["forecast_at"] = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    late = _row(1, 1, 0.8, 1)
    late["forecast_at"] = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

    report = evaluate_chronological_rows([early, late])

    metrics = report["markets"]["home_win"]["model"]
    assert report["prediction_count"] == 1
    assert report["duplicate_forecasts_collapsed"] == 1
    assert metrics["mean_probability"] == 0.8


def test_reliability_deciles_report_probability_and_outcome_rates():
    rows = [
        _row(1, 1, 0.05, 0),
        _row(2, 2, 0.08, 1),
        _row(3, 3, 0.85, 1),
        _row(4, 4, 0.95, 1),
    ]

    report = evaluate_chronological_rows(rows)
    metrics = report["markets"]["home_win"]["model"]

    assert abs(metrics["expected_calibration_error"] - 0.2675) < 1e-12
    assert metrics["roc_auc"] == 1.0
    assert metrics["reliability_deciles"] == [
        {
            "lower_bound": 0.0,
            "upper_bound": 0.1,
            "n": 2,
            "mean_probability": 0.065,
            "observed_rate": 0.5,
        },
        {
            "lower_bound": 0.8,
            "upper_bound": 0.9,
            "n": 1,
            "mean_probability": 0.85,
            "observed_rate": 1.0,
        },
        {
            "lower_bound": 0.9,
            "upper_bound": 1.0,
            "n": 1,
            "mean_probability": 0.95,
            "observed_rate": 1.0,
        },
    ]


def test_roc_auc_treats_tied_positive_negative_scores_as_half_credit():
    report = evaluate_chronological_rows([
        _row(1, 1, 0.5, 1),
        _row(2, 2, 0.5, 0),
    ])

    assert report["markets"]["home_win"]["model"]["roc_auc"] == 0.5


def test_score_rate_diagnostics_use_saved_distribution_and_one_row_per_match():
    row = _row(1, 1, 0.5, 1)
    row.update({
        "home_goals": 2,
        "away_goals": 1,
        "feature_snapshot": {
            "joint_score_distributions": {
                "poisson_dixon_coles": {
                    "parameters": {
                        "home_rate": 2.0,
                        "away_rate": 1.0,
                        "dixon_coles_rho": 0.0,
                    },
                },
            },
        },
    })
    duplicate = {**row, "market": "away_win"}

    report = evaluate_score_rate_snapshots([row, duplicate])

    assert report["snapshot_match_count"] == 1
    assert report["match_coverage"] == 1.0
    assert report["overall"]["n"] == 1
    assert abs(report["overall"]["predicted_home_goals_mean"] - 2.0) < 1e-4
    assert abs(report["overall"]["predicted_away_goals_mean"] - 1.0) < 1e-4


def test_snapshot_readiness_audits_latest_pre_kickoff_capture_without_outcomes():
    kickoff = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    complete = {
        "home_rate": 1.8,
        "away_rate": 1.1,
        "dixon_coles_rho": -0.08,
    }
    rows = [
        {
            "match_id": 1,
            "market": "home_win",
            "kickoff_at": kickoff,
            "forecast_at": kickoff - timedelta(hours=8),
            "match_status": "scheduled",
        },
        {
            "match_id": 1,
            "market": "home_win",
            "kickoff_at": kickoff,
            "forecast_at": kickoff - timedelta(hours=2),
            "match_status": "scheduled",
            "forecast_build_id": "build-a",
            **complete,
        },
        {
            "match_id": 1,
            "market": "away_win",
            "kickoff_at": kickoff,
            "forecast_at": kickoff - timedelta(hours=1),
            "match_status": "scheduled",
        },
        {
            "match_id": 2,
            "market": "home_win",
            "kickoff_at": kickoff,
            "forecast_at": kickoff,
            "match_status": "scheduled",
            **complete,
        },
    ]

    report = evaluate_snapshot_capture_readiness(rows)

    assert report["latest_forecast_count"] == 2
    assert report["unique_match_count"] == 1
    assert report["complete_snapshot_count"] == 1
    assert report["matches_with_any_complete_snapshot"] == 1
    assert report["snapshot_coverage"] == 0.5
    assert report["markets"]["home_win"]["complete_snapshot_count"] == 1
    assert report["forecast_build_id_counts"] == {
        "build-a": 1,
        "missing_or_legacy": 1,
    }
    assert report["forecasts_with_build_id"] == 1
    assert report["single_day_capture_gate_passed"] is False


def test_snapshot_readiness_requires_complete_parameters_and_one_build_id():
    kickoff = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    report = evaluate_snapshot_capture_readiness([{
        "match_id": 1,
        "market": "home_win",
        "kickoff_at": kickoff,
        "forecast_at": kickoff - timedelta(hours=1),
        "match_status": "scheduled",
        "forecast_build_id": "build-a",
        "home_rate": 1.8,
        "away_rate": 1.1,
        "dixon_coles_rho": -0.08,
    }])

    assert report["snapshot_coverage"] == 1.0
    assert report["forecast_build_id_coverage"] == 1.0
    assert report["single_build_id"] == "build-a"
    assert report["single_day_capture_gate_passed"] is True
    assert report["match_status_counts"] == {"scheduled": 1}


def test_logistic_calibration_uses_a_later_holdout_and_expanding_baselines():
    rows = []
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    for index in range(31):
        kickoff = start + timedelta(days=index)
        rows.append({
            "match_id": index + 1,
            "market": "home_win",
            "probability": 0.75 if index % 2 else 0.65,
            "poisson_probability": 0.55 if index % 2 else 0.45,
            "kickoff_at": kickoff,
            "forecast_at": kickoff - timedelta(hours=2),
            "competition_id": 1,
            "outcome": int(index % 6 == 0),
        })

    report = evaluate_logistic_calibration_holdout(
        rows,
        train_end=datetime(2026, 1, 24).date(),
        holdout_start=datetime(2026, 1, 25).date(),
        min_train_rows=20,
        min_holdout_rows=5,
        min_baseline_history=5,
    )

    market = report["markets"]["home_win"]
    assert report["status"] == "research_only"
    assert market["status"] == "completed"
    assert market["train_n"] == 24
    assert market["holdout_n"] == 7
    assert market["scored_holdout_n"] == 7
    assert market["calibration"]["slope"] > 0
    assert market["raw_brier_skill_vs_global"] is not None
    assert market["matched_poisson_comparison"]["n"] == 7
