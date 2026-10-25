"""Read-only chronological evaluation of detached Poisson score forecasts."""

from __future__ import annotations

import argparse
import asyncio
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from itertools import groupby

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CURRENT_MODEL_VERSION, cat_day_bounds_utc
from app.database import AsyncSessionLocal, engine
from app.models import Competition, Match, MatchStatus, Prediction
from app.services.models.poisson_dc import joint_score_distribution
from app.services.settlement import evaluate_selection


def _binary_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {
            "n": 0,
            "brier": None,
            "log_loss": None,
            "observed_rate": None,
            "mean_probability": None,
            "roc_auc": None,
            "reliability_deciles": [],
            "expected_calibration_error": None,
        }
    probabilities = [min(1 - 1e-15, max(1e-15, row["probability"])) for row in rows]
    outcomes = [row["outcome"] for row in rows]
    bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for probability, outcome in zip(probabilities, outcomes):
        bins[min(9, int(probability * 10))].append((probability, outcome))
    ranked = sorted(zip(probabilities, outcomes), key=lambda row: row[0])
    positive_count = sum(outcomes)
    negative_count = len(outcomes) - positive_count
    positive_rank_sum = 0.0
    rank_start = 0
    while rank_start < len(ranked):
        rank_end = rank_start + 1
        while rank_end < len(ranked) and ranked[rank_end][0] == ranked[rank_start][0]:
            rank_end += 1
        average_rank = ((rank_start + 1) + rank_end) / 2
        positive_rank_sum += average_rank * sum(
            outcome for _, outcome in ranked[rank_start:rank_end]
        )
        rank_start = rank_end
    roc_auc = (
        (positive_rank_sum - positive_count * (positive_count + 1) / 2)
        / (positive_count * negative_count)
        if positive_count and negative_count else None
    )
    reliability_deciles = []
    expected_calibration_error = 0.0
    for index, values in enumerate(bins):
        if not values:
            continue
        mean_probability = sum(probability for probability, _ in values) / len(values)
        observed_rate = sum(outcome for _, outcome in values) / len(values)
        expected_calibration_error += len(values) / len(rows) * abs(
            mean_probability - observed_rate
        )
        reliability_deciles.append({
            "lower_bound": index / 10,
            "upper_bound": (index + 1) / 10,
            "n": len(values),
            "mean_probability": mean_probability,
            "observed_rate": observed_rate,
        })
    return {
        "n": len(rows),
        "brier": sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(rows),
        "log_loss": -sum(
            y * math.log(p) + (1 - y) * math.log(1 - p)
            for p, y in zip(probabilities, outcomes)
        ) / len(rows),
        "observed_rate": sum(outcomes) / len(outcomes),
        "mean_probability": sum(probabilities) / len(probabilities),
        "roc_auc": roc_auc,
        "reliability_deciles": reliability_deciles,
        "expected_calibration_error": expected_calibration_error,
    }


def _paired_baseline_metrics(rows: list[dict]) -> dict:
    model_metrics = _binary_metrics(rows)
    baseline_metrics = _binary_metrics([
        {**row, "probability": row["baseline_probability"]}
        for row in rows
    ])
    baseline_metrics["brier_skill_score"] = (
        1 - model_metrics["brier"] / baseline_metrics["brier"]
        if baseline_metrics["brier"] not in (None, 0)
        else None
    )
    return baseline_metrics


def _score_rate_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    home_biases = [row["predicted_home_rate"] - row["home_goals"] for row in rows]
    away_biases = [row["predicted_away_rate"] - row["away_goals"] for row in rows]
    return {
        "n": len(rows),
        "predicted_home_goals_mean": sum(row["predicted_home_rate"] for row in rows) / len(rows),
        "observed_home_goals_mean": sum(row["home_goals"] for row in rows) / len(rows),
        "home_goals_bias": sum(home_biases) / len(home_biases),
        "home_goals_mae": sum(abs(value) for value in home_biases) / len(home_biases),
        "predicted_away_goals_mean": sum(row["predicted_away_rate"] for row in rows) / len(rows),
        "observed_away_goals_mean": sum(row["away_goals"] for row in rows) / len(rows),
        "away_goals_bias": sum(away_biases) / len(away_biases),
        "away_goals_mae": sum(abs(value) for value in away_biases) / len(away_biases),
    }


def evaluate_score_rate_snapshots(rows: list[dict]) -> dict:
    """Compare saved raw score-distribution means with finished score rates."""
    latest_by_match: dict[int, dict] = {}
    for row in rows:
        previous = latest_by_match.get(row["match_id"])
        forecast_at = row.get("forecast_at") or row["kickoff_at"]
        previous_at = (
            previous.get("forecast_at") or previous["kickoff_at"]
            if previous is not None else None
        )
        if previous is None or forecast_at >= previous_at:
            latest_by_match[row["match_id"]] = row

    scored_rows = []
    for row in latest_by_match.values():
        parameters = row.get("score_distribution_parameters")
        if parameters is None:
            snapshot = row.get("feature_snapshot") or {}
            if not isinstance(snapshot, dict):
                continue
            distribution_snapshot = (snapshot.get("joint_score_distributions") or {}).get(
                "poisson_dixon_coles"
            )
            if not isinstance(distribution_snapshot, dict):
                continue
            parameters = distribution_snapshot.get("parameters") or {}
        try:
            distribution = joint_score_distribution(
                float(parameters["home_rate"]),
                float(parameters["away_rate"]),
                float(parameters["dixon_coles_rho"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        matrix = distribution.matrix
        predicted_home_rate = sum(
            goals * float(matrix[goals, :].sum())
            for goals in range(matrix.shape[0])
        )
        predicted_away_rate = sum(
            goals * float(matrix[:, goals].sum())
            for goals in range(matrix.shape[1])
        )
        scored_rows.append({
            "match_id": row["match_id"],
            "competition_id": row.get("competition_id"),
            "home_goals": row["home_goals"],
            "away_goals": row["away_goals"],
            "predicted_home_rate": predicted_home_rate,
            "predicted_away_rate": predicted_away_rate,
        })

    by_competition: dict[int | None, list[dict]] = defaultdict(list)
    for row in scored_rows:
        by_competition[row["competition_id"]].append(row)
    return {
        "status": (
            "completed" if scored_rows else "unavailable_no_saved_joint_score_snapshots"
        ),
        "snapshot_match_count": len(scored_rows),
        "match_coverage": len(scored_rows) / len(latest_by_match) if latest_by_match else None,
        "overall": _score_rate_metrics(scored_rows),
        "competitions": {
            str(competition_id): _score_rate_metrics(competition_rows)
            for competition_id, competition_rows in sorted(
                by_competition.items(), key=lambda item: str(item[0])
            )
        },
    }


def _valid_score_snapshot_parameters(row: dict) -> bool:
    try:
        home_rate, away_rate, rho = (
            float(row[key])
            for key in ("home_rate", "away_rate", "dixon_coles_rho")
        )
    except (KeyError, TypeError, ValueError):
        return False
    return (
        all(math.isfinite(value) for value in (home_rate, away_rate, rho))
        and home_rate > 0
        and away_rate > 0
        and -1 <= rho <= 1
    )


def evaluate_snapshot_capture_readiness(rows: list[dict]) -> dict:
    """Audit latest pre-kickoff forecasts without using match outcomes."""
    latest_by_match_market: dict[tuple[int, str], dict] = {}
    for row in rows:
        forecast_at = row.get("forecast_at")
        kickoff_at = row["kickoff_at"]
        if forecast_at is None or forecast_at >= kickoff_at:
            continue
        key = (row["match_id"], row["market"])
        previous = latest_by_match_market.get(key)
        if previous is None or forecast_at >= previous["forecast_at"]:
            latest_by_match_market[key] = row

    markets: dict[str, list[dict]] = defaultdict(list)
    statuses: dict[str, int] = defaultdict(int)
    status_by_match: dict[int, str] = {}
    build_counts: dict[str, int] = defaultdict(int)
    complete_snapshot_count = 0
    for row in latest_by_match_market.values():
        markets[row["market"]].append(row)
        status_by_match[row["match_id"]] = str(row.get("match_status") or "unknown")
        build_counts[str(row.get("forecast_build_id") or "missing_or_legacy")] += 1
        if _valid_score_snapshot_parameters(row):
            complete_snapshot_count += 1

    market_report = {}
    for market, forecasts in sorted(markets.items()):
        complete = sum(
            _valid_score_snapshot_parameters(row) for row in forecasts
        )
        market_report[market] = {
            "latest_forecast_count": len(forecasts),
            "complete_snapshot_count": complete,
            "snapshot_coverage": complete / len(forecasts) if forecasts else None,
        }

    total_forecasts = len(latest_by_match_market)
    snapshot_coverage = (
        complete_snapshot_count / total_forecasts if total_forecasts else None
    )
    build_ids = {
        build_id for build_id in build_counts if build_id != "missing_or_legacy"
    }
    forecasts_with_build_id = sum(
        count for build_id, count in build_counts.items()
        if build_id != "missing_or_legacy"
    )
    build_id_coverage = (
        forecasts_with_build_id / total_forecasts if total_forecasts else None
    )
    market_snapshot_gate_passed = bool(market_report) and all(
        values["snapshot_coverage"] is not None
        and values["snapshot_coverage"] >= 0.95
        for values in market_report.values()
    )
    single_day_capture_gate_passed = (
        snapshot_coverage is not None
        and snapshot_coverage >= 0.95
        and market_snapshot_gate_passed
        and build_id_coverage is not None
        and build_id_coverage >= 0.95
        and len(build_ids) == 1
    )

    kickoffs = [row["kickoff_at"] for row in latest_by_match_market.values()]
    matches_with_snapshot = {
        row["match_id"]
        for row in latest_by_match_market.values()
        if _valid_score_snapshot_parameters(row)
    }
    match_ids = {match_id for match_id, _ in latest_by_match_market}
    for match_status in status_by_match.values():
        statuses[match_status] += 1
    return {
        "status": (
            "completed_with_saved_snapshots"
            if complete_snapshot_count
            else "unavailable_no_saved_joint_score_snapshots"
        ),
        "latest_forecast_count": total_forecasts,
        "unique_match_count": len(match_ids),
        "matches_with_any_complete_snapshot": len(matches_with_snapshot),
        "complete_snapshot_count": complete_snapshot_count,
        "snapshot_coverage": snapshot_coverage,
        "snapshot_coverage_threshold": 0.95,
        "market_snapshot_gate_passed": market_snapshot_gate_passed,
        "match_status_counts": dict(sorted(statuses.items())),
        "forecast_build_id_counts": dict(sorted(build_counts.items())),
        "forecasts_with_build_id": forecasts_with_build_id,
        "forecast_build_id_coverage": build_id_coverage,
        "single_build_id": next(iter(build_ids)) if len(build_ids) == 1 else None,
        "single_day_capture_gate_passed": single_day_capture_gate_passed,
        "kickoff_utc_date_range": [
            min(kickoffs).date().isoformat(), max(kickoffs).date().isoformat()
        ] if kickoffs else None,
        "markets": market_report,
    }


def evaluate_logistic_calibration_holdout(
    rows: list[dict],
    *,
    train_end: date,
    holdout_start: date,
    min_train_rows: int = 500,
    min_holdout_rows: int = 100,
    min_baseline_history: int = 30,
) -> dict:
    """Fit frozen per-market logistic recalibration and score a later holdout."""
    if holdout_start <= train_end:
        raise ValueError("holdout_start must be after train_end")
    latest_by_match_market: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (row["match_id"], row["market"])
        previous = latest_by_match_market.get(key)
        forecast_at = row.get("forecast_at") or row["kickoff_at"]
        previous_at = (
            previous.get("forecast_at") or previous["kickoff_at"]
            if previous is not None else None
        )
        if previous is None or forecast_at >= previous_at:
            latest_by_match_market[key] = row

    rows = list(latest_by_match_market.values())
    by_market: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_market[row["market"]].append(row)

    from scipy.optimize import minimize
    import numpy as np

    results = {}
    for market, market_rows in sorted(by_market.items()):
        train = [row for row in market_rows if row["kickoff_at"].date() <= train_end]
        holdout = [row for row in market_rows if row["kickoff_at"].date() >= holdout_start]
        market_result = {"train_n": len(train), "holdout_n": len(holdout)}
        if len(train) < min_train_rows or len(holdout) < min_holdout_rows:
            market_result["status"] = "insufficient_sample"
            results[market] = market_result
            continue

        train_probabilities = np.clip(
            np.asarray([row["probability"] for row in train], dtype=float), 1e-8, 1 - 1e-8
        )
        train_logits = np.log(train_probabilities / (1 - train_probabilities))
        train_outcomes = np.asarray([row["outcome"] for row in train], dtype=float)

        def objective(parameters):
            intercept, slope = parameters
            logits = intercept + slope * train_logits
            probabilities = 1 / (1 + np.exp(-np.clip(logits, -40, 40)))
            loss = np.logaddexp(0, logits) - train_outcomes * logits
            gradient = np.asarray([
                np.sum(probabilities - train_outcomes),
                np.dot(probabilities - train_outcomes, train_logits),
            ])
            return float(np.mean(loss)), gradient / len(train)

        fit = minimize(
            objective,
            np.asarray([0.0, 1.0]),
            jac=True,
            method="L-BFGS-B",
            bounds=[(-8.0, 8.0), (0.05, 8.0)],
            options={"maxiter": 500, "ftol": 1e-12},
        )
        if not fit.success or not np.all(np.isfinite(fit.x)):
            market_result["status"] = "fit_failed"
            market_result["fit_message"] = str(fit.message)
            results[market] = market_result
            continue

        intercept, slope = map(float, fit.x)
        market_rows.sort(key=lambda row: (row["kickoff_at"], row["match_id"]))
        prior_outcomes: list[int] = []
        prior_by_competition: dict[int | None, list[int]] = defaultdict(list)
        holdout_by_id: dict[int, dict] = {}
        for _, same_day_iter in groupby(
            market_rows, key=lambda row: row["kickoff_at"].date()
        ):
            same_day_rows = list(same_day_iter)
            global_probability = (
                (sum(prior_outcomes) + 1) / (len(prior_outcomes) + 2)
                if len(prior_outcomes) >= min_baseline_history else None
            )
            for row in same_day_rows:
                if row["kickoff_at"].date() < holdout_start:
                    continue
                competition_id = row.get("competition_id")
                competition_history = prior_by_competition[competition_id]
                competition_probability = (
                    (sum(competition_history) + 1) / (len(competition_history) + 2)
                    if len(competition_history) >= min_baseline_history else None
                )
                if global_probability is not None and competition_probability is not None:
                    raw_probability = min(1 - 1e-8, max(1e-8, row["probability"]))
                    raw_logit = math.log(raw_probability / (1 - raw_probability))
                    calibrated_logit = max(-40, min(40, intercept + slope * raw_logit))
                    holdout_by_id[row["match_id"]] = {
                        **row,
                        "calibrated_probability": 1 / (1 + math.exp(-calibrated_logit)),
                        "global_baseline_probability": global_probability,
                        "competition_baseline_probability": competition_probability,
                    }
            prior_outcomes.extend(row["outcome"] for row in same_day_rows)
            for row in same_day_rows:
                prior_by_competition[row.get("competition_id")].append(row["outcome"])

        scored = list(holdout_by_id.values())
        raw_rows = [{**row, "probability": row["probability"]} for row in scored]
        calibrated_rows = [
            {**row, "probability": row["calibrated_probability"]} for row in scored
        ]
        global_rows = [
            {**row, "probability": row["global_baseline_probability"]} for row in scored
        ]
        competition_rows = [
            {**row, "probability": row["competition_baseline_probability"]}
            for row in scored
        ]
        raw_metrics = _binary_metrics(raw_rows)
        calibrated_metrics = _binary_metrics(calibrated_rows)
        global_metrics = _binary_metrics(global_rows)
        competition_metrics = _binary_metrics(competition_rows)
        common_scored = [
            row for row in scored if row.get("poisson_probability") is not None
        ]
        common_comparison = None
        if common_scored:
            primary_common = _binary_metrics([
                {**row, "probability": row["probability"]} for row in common_scored
            ])
            calibrated_common = _binary_metrics([
                {**row, "probability": row["calibrated_probability"]}
                for row in common_scored
            ])
            poisson_common = _binary_metrics([
                {**row, "probability": row["poisson_probability"]}
                for row in common_scored
            ])
            global_common = _binary_metrics([
                {**row, "probability": row["global_baseline_probability"]}
                for row in common_scored
            ])
            competition_common = _binary_metrics([
                {**row, "probability": row["competition_baseline_probability"]}
                for row in common_scored
            ])
            common_comparison = {
                "n": len(common_scored),
                "selected_raw": primary_common,
                "selected_calibrated": calibrated_common,
                "poisson_reference": poisson_common,
                "global_expanding_baseline": global_common,
                "competition_expanding_baseline": competition_common,
                "selected_raw_brier_skill_vs_global": (
                    1 - primary_common["brier"] / global_common["brier"]
                    if global_common["brier"] else None
                ),
                "poisson_brier_skill_vs_global": (
                    1 - poisson_common["brier"] / global_common["brier"]
                    if global_common["brier"] else None
                ),
                "selected_raw_brier_skill_vs_competition": (
                    1 - primary_common["brier"] / competition_common["brier"]
                    if competition_common["brier"] else None
                ),
                "poisson_brier_skill_vs_competition": (
                    1 - poisson_common["brier"] / competition_common["brier"]
                    if competition_common["brier"] else None
                ),
            }
        market_result.update({
            "status": "completed",
            "scored_holdout_n": len(scored),
            "calibration": {"intercept": intercept, "slope": slope},
            "matched_poisson_comparison": common_comparison,
            "raw": raw_metrics,
            "calibrated": calibrated_metrics,
            "global_expanding_baseline": global_metrics,
            "competition_expanding_baseline": competition_metrics,
            "raw_brier_skill_vs_global": (
                1 - raw_metrics["brier"] / global_metrics["brier"]
                if global_metrics["brier"] else None
            ),
            "calibrated_brier_skill_vs_global": (
                1 - calibrated_metrics["brier"] / global_metrics["brier"]
                if global_metrics["brier"] else None
            ),
            "raw_brier_skill_vs_competition": (
                1 - raw_metrics["brier"] / competition_metrics["brier"]
                if competition_metrics["brier"] else None
            ),
            "calibrated_brier_skill_vs_competition": (
                1 - calibrated_metrics["brier"] / competition_metrics["brier"]
                if competition_metrics["brier"] else None
            ),
        })
        results[market] = market_result

    return {
        "status": "research_only",
        "train_end_inclusive": train_end.isoformat(),
        "holdout_start_inclusive": holdout_start.isoformat(),
        "train_minimum_per_market": min_train_rows,
        "holdout_minimum_per_market": min_holdout_rows,
        "baseline_minimum_prior_outcomes": min_baseline_history,
        "calibration_method": "per_market_logistic_intercept_and_positive_slope",
        "markets": results,
    }


def evaluate_chronological_rows(rows: list[dict], *, min_baseline_history: int = 30) -> dict:
    """Score point-in-time forecasts against a same-market expanding prior.

    Each day's baseline uses only earlier UTC kickoff dates. These metrics are
    descriptive research evidence, not a calibration or promotion decision.
    """
    input_count = len(rows)
    latest_by_match_market: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (row["match_id"], row["market"])
        previous = latest_by_match_market.get(key)
        forecast_at = row.get("forecast_at") or row["kickoff_at"]
        previous_at = (
            previous.get("forecast_at") or previous["kickoff_at"]
            if previous is not None else None
        )
        if previous is None or forecast_at >= previous_at:
            latest_by_match_market[key] = row
    rows = list(latest_by_match_market.values())

    by_market: dict[str, list[dict]] = defaultdict(list)
    by_period: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_market[row["market"]].append(row)
        by_period[row["kickoff_at"].year][row["market"]].append(row)

    market_results = {}
    for market, market_rows in sorted(by_market.items()):
        market_rows.sort(key=lambda row: (row["kickoff_at"], row["match_id"]))
        prior_outcomes: list[int] = []
        paired_baseline_rows: list[dict] = []
        for _, same_day_iter in groupby(market_rows, key=lambda row: row["kickoff_at"].date()):
            same_day_rows = list(same_day_iter)
            prior_n = len(prior_outcomes)
            if prior_n >= min_baseline_history:
                baseline_probability = (sum(prior_outcomes) + 1) / (prior_n + 2)
                paired_baseline_rows.extend(
                    {**row, "baseline_probability": baseline_probability}
                    for row in same_day_rows
                )
            prior_outcomes.extend(row["outcome"] for row in same_day_rows)

        prior_by_competition: dict[int | None, list[int]] = defaultdict(list)
        model_rows_by_competition: dict[int | None, list[dict]] = defaultdict(list)
        day_competition_rows: dict[tuple[date, int | None], list[dict]] = defaultdict(list)
        for row in market_rows:
            competition_id = row.get("competition_id")
            day_competition_rows[(row["kickoff_at"].date(), competition_id)].append(row)
            model_rows_by_competition[competition_id].append(row)
        paired_competition_rows: list[dict] = []
        paired_by_competition: dict[int | None, list[dict]] = defaultdict(list)
        for (_, competition_id), same_day_rows in sorted(
            day_competition_rows.items(),
            key=lambda item: (item[0][0], str(item[0][1])),
        ):
            competition_history = prior_by_competition[competition_id]
            if len(competition_history) >= min_baseline_history:
                baseline_probability = (sum(competition_history) + 1) / (len(competition_history) + 2)
                paired_rows = [
                    {**row, "baseline_probability": baseline_probability}
                    for row in same_day_rows
                ]
                paired_competition_rows.extend(paired_rows)
                paired_by_competition[competition_id].extend(paired_rows)
            competition_history.extend(row["outcome"] for row in same_day_rows)

        model_metrics = _binary_metrics(market_rows)
        baseline_metrics = _paired_baseline_metrics(paired_baseline_rows)
        competition_baseline_metrics = _paired_baseline_metrics(paired_competition_rows)
        market_results[market] = {
            "model": model_metrics,
            "expanding_prior_climatology": baseline_metrics,
            "competition_expanding_prior_climatology": competition_baseline_metrics,
            "competition_segments": {
                str(competition_id): {
                    "competition_name": competition_rows[0].get("competition_name"),
                    "model": _binary_metrics(competition_rows),
                    "expanding_prior_climatology": _paired_baseline_metrics(
                        paired_by_competition.get(competition_id, [])
                    ),
                }
                for competition_id, competition_rows in sorted(
                    model_rows_by_competition.items(), key=lambda item: str(item[0])
                )
            },
        }

    period_results = {}
    for period, market_groups in sorted(by_period.items()):
        period_results[str(period)] = {
            market: _binary_metrics(period_rows)
            for market, period_rows in sorted(market_groups.items())
        }

    kickoffs = [row["kickoff_at"] for row in rows]
    return {
        "status": "completed",
        "research_only": True,
        "release_decision": "none",
        "forecast_source": "point_in_time.poisson_prob",
        "outcome_source": "finished_match_score",
        "chronology": {
            "forecast_timestamp_strictly_before_kickoff": True,
            "baselines_use_earlier_utc_kickoff_dates_only": True,
            "minimum_prior_matches_for_baseline": min_baseline_history,
        },
        "match_count": len({row["match_id"] for row in rows}),
        "prediction_count": len(rows),
        "duplicate_forecasts_collapsed": input_count - len(rows),
        "kickoff_date_range": [
            min(kickoffs).date().isoformat(), max(kickoffs).date().isoformat()
        ] if kickoffs else None,
        "markets": market_results,
        "calendar_years": period_results,
    }


async def evaluate_historical_score_distribution(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    model_version: str | None = None,
    min_baseline_history: int = 30,
    capture_source: str = "historical_backfill",
    probability_field: str = "poisson_prob",
    calibration_train_end: date | None = None,
    calibration_holdout_start: date | None = None,
    calibration_min_train_rows: int = 500,
    calibration_min_holdout_rows: int = 100,
) -> dict:
    """Read detached point-in-time rows and return chronological metrics."""
    if capture_source not in {"historical_backfill", "model_run"}:
        raise ValueError("capture_source must be historical_backfill or model_run")
    if probability_field not in {
        "poisson_prob", "model_probability", "raw_ensemble_probability"
    }:
        raise ValueError("Unsupported probability_field")
    probability_column = getattr(Prediction, probability_field)
    selected_model_version = model_version or CURRENT_MODEL_VERSION
    filters = [
        probability_column.is_not(None),
        Match.status == MatchStatus.FINISHED,
        Match.home_goals.is_not(None),
        Match.away_goals.is_not(None),
        Match.excluded_from_models.is_(False),
    ]
    if capture_source == "historical_backfill":
        filters.extend((
            Prediction.source_odds_provenance["capture_source"].as_string() == "historical_backfill",
            Prediction.as_of_at.is_not(None),
            Prediction.as_of_at < Match.kickoff_at,
        ))
    else:
        filters.extend((
            Prediction.model_run_id.is_not(None),
            func.coalesce(Prediction.decision_at, Prediction.created_at) < Match.kickoff_at,
        ))
    filters.append(Prediction.model_version == selected_model_version)
    if start:
        filters.append(Match.kickoff_at >= cat_day_bounds_utc(start)[0])
    if end:
        filters.append(Match.kickoff_at < cat_day_bounds_utc(end)[1])

    query = (
        select(
            Prediction.id,
            Prediction.match_id,
            Prediction.market,
            probability_column,
            Prediction.poisson_prob,
            Prediction.as_of_at,
            Prediction.decision_at,
            Prediction.created_at,
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["home_rate"].as_float(),
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["away_rate"].as_float(),
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["dixon_coles_rho"].as_float(),
            Match.kickoff_at,
            Match.competition_id,
            Competition.name,
            Match.home_goals,
            Match.away_goals,
        )
        .join(Match, Match.id == Prediction.match_id)
        .outerjoin(Competition, Competition.id == Match.competition_id)
        .where(*filters)
        .order_by(Match.kickoff_at.asc(), Match.id.asc(), Prediction.market.asc())
    )
    result = await db.execute(query)
    rows = []
    for (
        prediction_id, match_id, market, probability, poisson_probability,
        as_of_at, decision_at,
        created_at, joint_home_rate, joint_away_rate, joint_rho, kickoff_at,
        competition_id, competition_name, home_goals, away_goals,
    ) in result.all():
        outcome = evaluate_selection(market, home_goals, away_goals)
        if outcome.value not in ("won", "lost"):
            continue
        rows.append({
            "match_id": match_id,
            "market": market,
            "probability": float(probability),
            "poisson_probability": (
                float(poisson_probability) if poisson_probability is not None else None
            ),
            "kickoff_at": kickoff_at,
            "competition_id": competition_id,
            "competition_name": competition_name,
            "forecast_at": as_of_at or decision_at or created_at,
            "score_distribution_parameters": (
                {
                    "home_rate": float(joint_home_rate),
                    "away_rate": float(joint_away_rate),
                    "dixon_coles_rho": float(joint_rho),
                }
                if joint_home_rate is not None
                and joint_away_rate is not None
                and joint_rho is not None
                else None
            ),
            "prediction_id": prediction_id,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "outcome": int(outcome.value == "won"),
        })
    report = evaluate_chronological_rows(rows, min_baseline_history=min_baseline_history)
    report["score_rate_diagnostics"] = evaluate_score_rate_snapshots(rows)
    if (calibration_train_end is None) != (calibration_holdout_start is None):
        raise ValueError("calibration_train_end and calibration_holdout_start must be supplied together")
    if calibration_train_end is not None and calibration_holdout_start is not None:
        report["chronological_calibration_research"] = evaluate_logistic_calibration_holdout(
            rows,
            train_end=calibration_train_end,
            holdout_start=calibration_holdout_start,
            min_train_rows=calibration_min_train_rows,
            min_holdout_rows=calibration_min_holdout_rows,
            min_baseline_history=min_baseline_history,
        )
    report["forecast_source"] = f"{capture_source}.{probability_field}"
    report["model_version"] = selected_model_version
    report["capture_source"] = capture_source
    report["probability_field"] = probability_field
    report["filters"] = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "model_version": selected_model_version,
        "capture_source": capture_source,
        "probability_field": probability_field,
    }
    return report


async def audit_saved_score_snapshot_capture(
    db: AsyncSession,
    *,
    capture_source: str = "model_run",
    model_version: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Audit saved forecast snapshots across pending and completed matches."""
    if capture_source not in {"historical_backfill", "model_run"}:
        raise ValueError("capture_source must be historical_backfill or model_run")
    selected_model_version = model_version or CURRENT_MODEL_VERSION
    forecast_at = (
        Prediction.as_of_at
        if capture_source == "historical_backfill"
        else func.coalesce(Prediction.decision_at, Prediction.created_at)
    )
    filters = [
        Prediction.model_version == selected_model_version,
        Match.excluded_from_models.is_(False),
        forecast_at < Match.kickoff_at,
    ]
    if capture_source == "historical_backfill":
        filters.extend((
            Prediction.source_odds_provenance["capture_source"].as_string()
            == "historical_backfill",
            Prediction.as_of_at.is_not(None),
        ))
    else:
        filters.append(Prediction.model_run_id.is_not(None))
    if start:
        filters.append(Match.kickoff_at >= cat_day_bounds_utc(start)[0])
    if end:
        filters.append(Match.kickoff_at < cat_day_bounds_utc(end)[1])

    result = await db.execute(
        select(
            Prediction.match_id,
            Prediction.market,
            forecast_at,
            Match.kickoff_at,
            Match.status,
            Prediction.feature_snapshot["forecast_build_id"].as_string(),
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["home_rate"].as_float(),
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["away_rate"].as_float(),
            Prediction.feature_snapshot[
                "joint_score_distributions"
            ]["poisson_dixon_coles"]["parameters"]["dixon_coles_rho"].as_float(),
        )
        .join(Match, Match.id == Prediction.match_id)
        .where(*filters)
        .order_by(Match.kickoff_at.asc(), Match.id.asc(), Prediction.market.asc(), forecast_at.asc())
    )
    rows = [
        {
            "match_id": match_id,
            "market": market,
            "forecast_at": forecast_time,
            "kickoff_at": kickoff_at,
            "match_status": getattr(match_status, "value", match_status),
            "forecast_build_id": build_id,
            "home_rate": home_rate,
            "away_rate": away_rate,
            "dixon_coles_rho": rho,
        }
        for (
            match_id, market, forecast_time, kickoff_at, match_status,
            build_id, home_rate, away_rate, rho,
        ) in result.all()
    ]
    report = evaluate_snapshot_capture_readiness(rows)
    report.update({
        "capture_source": capture_source,
        "model_version": selected_model_version,
        "kickoff_filter": {
            "start_cat_inclusive": start.isoformat() if start else None,
            "end_cat_inclusive": end.isoformat() if end else None,
        },
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    })
    return report


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--model-version")
    parser.add_argument(
        "--capture-source",
        choices=("historical_backfill", "model_run"),
        default="historical_backfill",
    )
    parser.add_argument(
        "--probability-field",
        choices=("poisson_prob", "model_probability", "raw_ensemble_probability"),
        default="poisson_prob",
    )
    parser.add_argument("--min-baseline-history", type=int, default=30)
    parser.add_argument("--calibration-train-end", type=date.fromisoformat)
    parser.add_argument("--calibration-holdout-start", type=date.fromisoformat)
    parser.add_argument("--calibration-min-train-rows", type=int, default=500)
    parser.add_argument("--calibration-min-holdout-rows", type=int, default=100)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--calibration-only", action="store_true")
    parser.add_argument("--snapshot-audit-only", action="store_true")
    args = parser.parse_args()
    # The development engine is configured with SQL echo by default. Keep the
    # research report clean and limited to aggregate forecast metrics.
    engine.echo = False
    import json
    if args.snapshot_audit_only:
        async with AsyncSessionLocal() as db:
            report = await audit_saved_score_snapshot_capture(
                db,
                capture_source=args.capture_source,
                model_version=args.model_version,
                start=args.start,
                end=args.end,
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        await engine.dispose()
        return
    async with AsyncSessionLocal() as db:
        report = await evaluate_historical_score_distribution(
            db,
            start=args.start,
            end=args.end,
            model_version=args.model_version,
            min_baseline_history=args.min_baseline_history,
            capture_source=args.capture_source,
            probability_field=args.probability_field,
            calibration_train_end=args.calibration_train_end,
            calibration_holdout_start=args.calibration_holdout_start,
            calibration_min_train_rows=args.calibration_min_train_rows,
            calibration_min_holdout_rows=args.calibration_min_holdout_rows,
        )
    if args.calibration_only:
        calibration = report.get("chronological_calibration_research")
        if calibration is None:
            raise ValueError("--calibration-only requires both calibration date arguments")
        report = {
            "status": report["status"],
            "research_only": report["research_only"],
            "release_decision": report["release_decision"],
            "capture_source": report["capture_source"],
            "probability_field": report["probability_field"],
            "model_version": report["model_version"],
            "chronological_calibration_research": {
                key: calibration[key]
                for key in (
                    "status", "train_end_inclusive", "holdout_start_inclusive",
                    "train_minimum_per_market", "holdout_minimum_per_market",
                    "baseline_minimum_prior_outcomes", "calibration_method",
                )
            } | {
                "markets": {
                    market: {
                        "train_n": values.get("train_n"),
                        "holdout_n": values.get("holdout_n"),
                        "scored_holdout_n": values.get("scored_holdout_n"),
                        "calibration": values.get("calibration"),
                        "raw": {
                            metric: values.get("raw", {}).get(metric)
                            for metric in ("brier", "log_loss", "roc_auc")
                        },
                        "calibrated": {
                            metric: values.get("calibrated", {}).get(metric)
                            for metric in ("brier", "log_loss", "roc_auc")
                        },
                        "raw_brier_skill_vs_global": values.get(
                            "raw_brier_skill_vs_global"
                        ),
                        "calibrated_brier_skill_vs_global": values.get(
                            "calibrated_brier_skill_vs_global"
                        ),
                        "raw_brier_skill_vs_competition": values.get(
                            "raw_brier_skill_vs_competition"
                        ),
                        "calibrated_brier_skill_vs_competition": values.get(
                            "calibrated_brier_skill_vs_competition"
                        ),
                        "matched_poisson_comparison": (
                            {
                                key: values["matched_poisson_comparison"].get(key)
                                for key in (
                                    "n", "selected_raw_brier_skill_vs_global",
                                    "poisson_brier_skill_vs_global",
                                    "selected_raw_brier_skill_vs_competition",
                                    "poisson_brier_skill_vs_competition",
                                )
                            }
                            | {
                                group: {
                                    metric: values["matched_poisson_comparison"][group].get(metric)
                                    for metric in ("brier", "roc_auc")
                                }
                                for group in (
                                    "selected_raw", "poisson_reference",
                                    "global_expanding_baseline",
                                    "competition_expanding_baseline",
                                )
                            }
                            if values.get("matched_poisson_comparison") is not None
                            else None
                        ),
                    }
                    for market, values in calibration["markets"].items()
                },
            },
        }
    elif args.compact:
        full_report = report
        report = {
            key: report[key]
            for key in (
                "status", "research_only", "release_decision", "capture_source",
                "model_version", "probability_field", "match_count", "prediction_count",
                "duplicate_forecasts_collapsed", "kickoff_date_range", "chronology",
            )
        } | {
            "markets": {
                market: {
                    "n": values["model"]["n"],
                    "model_brier": values["model"]["brier"],
                    "model_log_loss": values["model"]["log_loss"],
                    "observed_rate": values["model"]["observed_rate"],
                    "mean_probability": values["model"]["mean_probability"],
                    "roc_auc": values["model"]["roc_auc"],
                    "expected_calibration_error": values["model"][
                        "expected_calibration_error"
                    ],
                    "baseline_brier": values["expanding_prior_climatology"]["brier"],
                    "baseline_log_loss": values["expanding_prior_climatology"]["log_loss"],
                    "brier_skill_score": values["expanding_prior_climatology"]["brier_skill_score"],
                    "competition_baseline_brier_skill_score": values[
                        "competition_expanding_prior_climatology"
                    ]["brier_skill_score"],
                }
                for market, values in report["markets"].items()
            },
            "score_rate_diagnostics": {
                "snapshot_match_count": report["score_rate_diagnostics"]["snapshot_match_count"],
                "status": report["score_rate_diagnostics"]["status"],
                "match_coverage": report["score_rate_diagnostics"]["match_coverage"],
                "overall": report["score_rate_diagnostics"]["overall"],
                "competition_count": len(report["score_rate_diagnostics"]["competitions"]),
                "largest_competitions": [
                    {"competition_id": competition_id, **metrics}
                    for competition_id, metrics in sorted(
                        report["score_rate_diagnostics"]["competitions"].items(),
                        key=lambda item: item[1]["n"], reverse=True,
                    )[:10]
                ],
            },
        }
        for market, values in full_report["markets"].items():
            segments = values["competition_segments"]
            eligible_segments = [
                {
                    "competition_id": competition_id,
                    "competition_name": segment["competition_name"],
                    "n": segment["model"]["n"],
                    "baseline_n": segment["expanding_prior_climatology"]["n"],
                    "brier_skill_score": segment[
                        "expanding_prior_climatology"
                    ]["brier_skill_score"],
                    "expected_calibration_error": segment["model"][
                        "expected_calibration_error"
                    ],
                    "observed_rate": segment["model"]["observed_rate"],
                    "mean_probability": segment["model"]["mean_probability"],
                }
                for competition_id, segment in segments.items()
                if segment["model"]["n"] >= 30
                and segment["expanding_prior_climatology"]["n"] >= 30
                and segment["expanding_prior_climatology"]["brier_skill_score"] is not None
            ]
            report["markets"][market]["competition_diagnostics"] = {
                "competition_count": len(segments),
                "minimum_segment_forecasts": 30,
                "segments_meeting_minimum": len(eligible_segments),
                "largest_segments": sorted(
                    [
                        {
                            "competition_id": competition_id,
                            "competition_name": segment["competition_name"],
                            "n": segment["model"]["n"],
                            "baseline_n": segment[
                                "expanding_prior_climatology"
                            ]["n"],
                            "brier_skill_score": segment[
                                "expanding_prior_climatology"
                            ]["brier_skill_score"],
                        }
                        for competition_id, segment in segments.items()
                    ],
                    key=lambda item: item["n"],
                    reverse=True,
                )[:3],
                "lowest_skill_segments": sorted(
                    eligible_segments, key=lambda item: item["brier_skill_score"]
                )[:3],
                "highest_skill_segments": sorted(
                    eligible_segments, key=lambda item: item["brier_skill_score"], reverse=True
                )[:3],
            }
            report["markets"][market].pop("competition_segments", None)
        if "chronological_calibration_research" in full_report:
            calibration = full_report["chronological_calibration_research"]
            report["chronological_calibration_research"] = {
                key: calibration[key]
                for key in (
                    "status", "train_end_inclusive", "holdout_start_inclusive",
                    "train_minimum_per_market", "holdout_minimum_per_market",
                    "baseline_minimum_prior_outcomes", "calibration_method",
                )
            } | {
                "markets": {
                    market: {
                        key: values.get(key)
                        for key in (
                            "status", "train_n", "holdout_n", "scored_holdout_n",
                            "calibration", "raw_brier_skill_vs_global",
                            "calibrated_brier_skill_vs_global",
                            "raw_brier_skill_vs_competition",
                            "calibrated_brier_skill_vs_competition",
                        )
                    }
                    | {
                        group: {
                            metric: values.get(group, {}).get(metric)
                            for metric in (
                                "brier", "log_loss", "expected_calibration_error", "roc_auc"
                            )
                        }
                        for group in (
                            "raw", "calibrated", "global_expanding_baseline",
                            "competition_expanding_baseline",
                        )
                    }
                    | {
                        "matched_comparison": (
                            {
                                key: values["matched_poisson_comparison"].get(key)
                                for key in (
                                    "n", "selected_raw_brier_skill_vs_global",
                                    "poisson_brier_skill_vs_global",
                                    "selected_raw_brier_skill_vs_competition",
                                    "poisson_brier_skill_vs_competition",
                                )
                            }
                            | {
                                group: {
                                    metric: values["matched_poisson_comparison"]
                                    [group].get(metric)
                                    for metric in ("brier", "roc_auc")
                                }
                                for group in (
                                    "selected_raw", "poisson_reference",
                                    "global_expanding_baseline",
                                    "competition_expanding_baseline",
                                )
                            }
                            if values.get("matched_poisson_comparison") is not None
                            else None
                        )
                    }
                    for market, values in calibration["markets"].items()
                },
            }
    print(json.dumps(report, indent=2, sort_keys=True))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
