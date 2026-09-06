"""Tests for the Data Quality Score gate (framework §10)."""

import pytest

from qwantej.data.dqs import (
    DQSClassification,
    DQSComponents,
    DQSGrade,
    DQSWeights,
    classify_dqs,
    compute_dqs,
)


def make_components(value: float) -> DQSComponents:
    return DQSComponents(
        completeness=value,
        freshness=value,
        provider_reliability=value,
        sample_sufficiency=value,
        entity_match_confidence=value,
        timestamp_validity=value,
    )


class TestDQSComponents:
    def test_rejects_out_of_range_component(self) -> None:
        with pytest.raises(ValueError, match="completeness"):
            DQSComponents(
                completeness=101,
                freshness=50,
                provider_reliability=50,
                sample_sufficiency=50,
                entity_match_confidence=50,
                timestamp_validity=50,
            )

    def test_rejects_negative_component(self) -> None:
        with pytest.raises(ValueError):
            make_components(-1)


class TestDQSWeights:
    def test_default_weights_sum_to_one(self) -> None:
        DQSWeights()  # must not raise

    def test_rejects_weights_not_summing_to_one(self) -> None:
        with pytest.raises(ValueError, match="must sum to 1.0"):
            DQSWeights(completeness=0.5, freshness=0.5, provider_reliability=0.5,
                       sample_sufficiency=0, entity_match_confidence=0, timestamp_validity=0)


class TestComputeDQS:
    def test_uniform_components_return_that_value(self) -> None:
        assert compute_dqs(make_components(80)) == pytest.approx(80)

    def test_all_zero_is_zero(self) -> None:
        assert compute_dqs(make_components(0)) == pytest.approx(0)

    def test_all_hundred_is_hundred(self) -> None:
        assert compute_dqs(make_components(100)) == pytest.approx(100)

    def test_respects_custom_weights(self) -> None:
        components = DQSComponents(
            completeness=100, freshness=0, provider_reliability=0,
            sample_sufficiency=0, entity_match_confidence=0, timestamp_validity=0,
        )
        weights = DQSWeights(
            completeness=1.0, freshness=0, provider_reliability=0,
            sample_sufficiency=0, entity_match_confidence=0, timestamp_validity=0,
        )
        assert compute_dqs(components, weights) == pytest.approx(100)


class TestClassifyDQS:
    @pytest.mark.parametrize(
        "score,expected_grade",
        [
            (100, DQSGrade.EXCELLENT),
            (90, DQSGrade.EXCELLENT),
            (89.9, DQSGrade.STRONG),
            (80, DQSGrade.STRONG),
            (79.9, DQSGrade.ACCEPTABLE),
            (70, DQSGrade.ACCEPTABLE),
            (69.9, DQSGrade.WEAK),
            (60, DQSGrade.WEAK),
            (59.9, DQSGrade.REJECT),
            (0, DQSGrade.REJECT),
        ],
    )
    def test_boundary_classification(self, score: float, expected_grade: DQSGrade) -> None:
        assert classify_dqs(score).grade == expected_grade

    def test_reject_grade_blocks_live_candidates(self) -> None:
        classification = classify_dqs(50)
        assert classification == DQSClassification(
            DQSGrade.REJECT, "Do not generate live betting candidates"
        )

    def test_rejects_out_of_range_score(self) -> None:
        with pytest.raises(ValueError):
            classify_dqs(101)
        with pytest.raises(ValueError):
            classify_dqs(-1)
