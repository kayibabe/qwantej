"""Phase 5 value calculations and reason-coded gate tests."""

from datetime import UTC, datetime, timedelta

import pytest

from qwantej.value import (
    ValueCandidate,
    ValueGatePolicy,
    ValueRejectionReason,
    closing_line_value,
    evaluate_value_gate,
    expected_value,
    fair_decimal_odds,
    probability_edge,
)

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _candidate(**overrides: object) -> ValueCandidate:
    values: dict[str, object] = {
        "decision_as_of": NOW,
        "calibrator_approved": True,
        "calibrated_probability": 0.65,
        "conservative_probability": 0.62,
        "fair_market_probability": 0.55,
        "executable_odds": 1.9,
        "quote_timestamp": NOW - timedelta(minutes=10),
        "data_quality_score": 90.0,
        "league_reliability": 75.0,
        "market_reliability": 75.0,
        "probability_change": 0.02,
        "model_disagreement": 0.03,
    }
    values.update(overrides)
    return ValueCandidate(**values)  # type: ignore[arg-type]


def test_value_formulas_match_framework_definitions() -> None:
    assert probability_edge(0.62, 0.55) == pytest.approx(0.07)
    assert expected_value(0.62, 1.9) == pytest.approx(0.178)
    assert fair_decimal_odds(0.5) == pytest.approx(2.0)
    assert closing_line_value(2.2, 2.0) == pytest.approx(0.1)


def test_qualified_candidate_passes_with_stored_values() -> None:
    result = evaluate_value_gate(_candidate())
    assert result.passed is True
    assert result.reason_codes == ()
    assert result.edge == pytest.approx(0.07)
    assert result.expected_value == pytest.approx(0.178)
    assert result.policy_version == "value-gate-v1"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"calibrator_approved": False}, ValueRejectionReason.CALIBRATION_UNAVAILABLE),
        ({"conservative_probability": 0.4}, ValueRejectionReason.UNCERTAINTY_TOO_HIGH),
        ({"quote_timestamp": NOW - timedelta(hours=3)}, ValueRejectionReason.MARKET_STALE),
        ({"fair_market_probability": 0.61}, ValueRejectionReason.EDGE_TOO_LOW),
        ({"executable_odds": 1.5}, ValueRejectionReason.EV_NON_POSITIVE),
        ({"data_quality_score": 60.0}, ValueRejectionReason.DATA_LOW_DQS),
        ({"league_reliability": None}, ValueRejectionReason.RELIABILITY_LOW),
        (
            {"league_reliability_status": "blacklisted"},
            ValueRejectionReason.RELIABILITY_LOW,
        ),
        ({"model_disagreement": 0.2}, ValueRejectionReason.MODEL_UNSTABLE),
        ({"unresolved_anomaly": True}, ValueRejectionReason.ANOMALY_REVIEW),
        ({"risk_allowed": False}, ValueRejectionReason.RISK_STATE_BLOCK),
    ],
)
def test_each_gate_emits_machine_readable_reason(
    overrides: dict[str, object], reason: ValueRejectionReason
) -> None:
    assert reason in evaluate_value_gate(_candidate(**overrides)).reason_codes


def test_all_failures_are_retained_in_stable_order() -> None:
    result = evaluate_value_gate(
        _candidate(
            calibrator_approved=False, calibrated_probability=None,
            conservative_probability=None, fair_market_probability=None,
            executable_odds=None, quote_timestamp=None, data_quality_score=0,
            league_reliability=None, market_reliability=None,
            probability_change=1.0, model_disagreement=1.0,
            unresolved_anomaly=True, risk_allowed=False,
        )
    )
    assert result.passed is False
    assert len(result.reason_codes) == len(set(result.reason_codes))
    assert result.edge is None and result.expected_value is None


def test_future_quote_is_rejected_before_gate_evaluation() -> None:
    with pytest.raises(ValueError, match="after decision_as_of"):
        _candidate(quote_timestamp=NOW + timedelta(seconds=1))


def test_unknown_reliability_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid reliability state"):
        _candidate(league_reliability_status="good")


def test_research_exception_only_bypasses_reliability_gate() -> None:
    result = evaluate_value_gate(
        _candidate(
            league_reliability=None, market_reliability=None,
            research_reliability_exception=True,
        )
    )
    assert ValueRejectionReason.RELIABILITY_LOW not in result.reason_codes


def test_policy_is_versioned_and_validated() -> None:
    with pytest.raises(ValueError):
        ValueGatePolicy(version="")
    with pytest.raises(ValueError):
        ValueGatePolicy(minimum_dqs=101)
    with pytest.raises(ValueError, match="in \\[0, 1\\]"):
        ValueGatePolicy(minimum_edge=1.01)
    with pytest.raises(ValueError, match="at least minimum_edge"):
        ValueGatePolicy(minimum_edge=0.2, extreme_edge_threshold=0.1)
