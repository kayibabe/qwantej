"""Bayesian shrinkage, recency, hierarchy and leakage tests for Phase 6."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from qwantej.performance import (
    ReliabilityObservation,
    ReliabilityPolicy,
    ReliabilityStatus,
    build_reliability_matrix,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _observation(
    index: int,
    *,
    league: str = "EPL",
    market: str = "O2.5",
    competition_class: str = "tier-1",
    age_days: int = 1,
    outcome: int = 1,
    probability: float = 0.7,
    profit: float = 0.8,
) -> ReliabilityObservation:
    observed = NOW - timedelta(days=age_days)
    return ReliabilityObservation(
        observation_id=str(index), league=league, market_family=market,
        competition_class=competition_class,
        decision_as_of=observed - timedelta(hours=3), outcome_observed_at=observed,
        predicted_probability=probability, outcome=outcome, profit_units=profit,
        closing_line_value=0.03, model_stability=0.9,
    )


def test_sparse_segment_is_strongly_shrunk_to_parent() -> None:
    rows = [_observation(index) for index in range(7)]
    matrix = build_reliability_matrix(rows, evaluated_as_of=NOW)
    cell = matrix.cells[0]
    estimate = cell.segment_reliability
    assert estimate.shrinkage_weight == pytest.approx(7 / 107, rel=0.01)
    assert abs(estimate.posterior_mean - cell.league_reliability.posterior_mean) < 0.03
    assert estimate.posterior_mean < estimate.raw_score


def test_recency_weighting_reduces_effective_sample_size() -> None:
    rows = [
        _observation(index, age_days=index * 180)
        for index in range(8)
    ]
    estimate = build_reliability_matrix(rows, evaluated_as_of=NOW).global_reliability
    assert 1 < estimate.effective_sample_size < estimate.observation_count


def test_future_outcomes_are_excluded_from_every_hierarchy_level() -> None:
    rows = [_observation(index) for index in range(5)]
    future = replace(
        _observation(99),
        decision_as_of=NOW + timedelta(days=1),
        outcome_observed_at=NOW + timedelta(days=2),
    )
    matrix = build_reliability_matrix([*rows, future], evaluated_as_of=NOW)
    assert matrix.future_rows_excluded == 1
    assert matrix.global_reliability.observation_count == 5
    assert matrix.cells[0].segment_reliability.observation_count == 5


def test_matrix_exposes_league_market_and_segment_estimates() -> None:
    rows = [
        *[_observation(index, league="EPL", market="O2.5") for index in range(10)],
        *[
            _observation(100 + index, league="EPL", market="BTTS")
            for index in range(10)
        ],
        *[
            _observation(200 + index, league="Serie A", market="O2.5")
            for index in range(10)
        ],
    ]
    matrix = build_reliability_matrix(rows, evaluated_as_of=NOW)
    cell = matrix.find("EPL", "O2.5")
    assert cell is not None
    assert cell.league_reliability.observation_count == 20
    assert cell.market_reliability.observation_count == 20
    assert cell.segment_reliability.observation_count == 10
    assert matrix.find("Serie A", "BTTS") is None


def test_status_uses_uncertainty_and_evidence_not_elapsed_time() -> None:
    policy = ReliabilityPolicy(
        prior_strength=1, confidence_z=0, minimum_qualified_effective_sample=5,
        qualified_lower_bound=0.6, watch_lower_bound=0.5,
        restricted_lower_bound=0.4,
    )
    strong = build_reliability_matrix(
        [_observation(index) for index in range(10)],
        evaluated_as_of=NOW, policy=policy,
    ).cells[0].segment_reliability
    sparse = build_reliability_matrix(
        [_observation(index) for index in range(2)],
        evaluated_as_of=NOW, policy=policy,
    ).cells[0].segment_reliability
    assert strong.status is ReliabilityStatus.QUALIFIED
    assert sparse.status is not ReliabilityStatus.QUALIFIED


def test_invalid_inputs_and_ambiguous_league_class_fail_closed() -> None:
    with pytest.raises(ValueError, match="after the decision"):
        replace(_observation(1), outcome_observed_at=_observation(1).decision_as_of)
    with pytest.raises(ValueError, match="unique"):
        build_reliability_matrix([_observation(1), _observation(1)], evaluated_as_of=NOW)
    with pytest.raises(ValueError, match="exactly one"):
        build_reliability_matrix(
            [_observation(1), _observation(2, competition_class="tier-2")],
            evaluated_as_of=NOW,
        )
    with pytest.raises(ValueError, match="sum to 1"):
        ReliabilityPolicy(calibration_weight=0.4)
