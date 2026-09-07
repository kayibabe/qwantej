"""Tests for Phase 9: champion-challenger framework (framework §43)."""

from __future__ import annotations

import pytest

from qwantej.performance.champion_challenger import (
    ChallengerEvaluation,
    ChallengerStatus,
    ModelMetrics,
    PromotionCriteria,
    evaluate_challenger,
)


def _metrics(
    version: str = "v1",
    n_samples: int = 500,
    brier_score: float = 0.220,
    log_loss: float = 0.600,
    roi: float = 0.04,
    mean_clv: float = 0.02,
    max_drawdown: float = 0.12,
) -> ModelMetrics:
    return ModelMetrics(
        model_version=version,
        n_samples=n_samples,
        brier_score=brier_score,
        log_loss=log_loss,
        roi=roi,
        mean_clv=mean_clv,
        max_drawdown=max_drawdown,
    )


CRITERIA = PromotionCriteria(
    min_sample_size=200,
    min_brier_improvement=0.002,
    min_roi_improvement=0.0,
    max_drawdown_increase=0.05,
    require_positive_clv=True,
)


# ---------------------------------------------------------------------------
# PromotionCriteria validation
# ---------------------------------------------------------------------------

class TestPromotionCriteria:
    def test_default_values_valid(self) -> None:
        c = PromotionCriteria()
        assert c.min_sample_size == 200
        assert c.require_positive_clv is True

    def test_rejects_zero_sample_size(self) -> None:
        with pytest.raises(ValueError, match="min_sample_size"):
            PromotionCriteria(min_sample_size=0)

    def test_rejects_negative_brier_improvement(self) -> None:
        with pytest.raises(ValueError, match="min_brier_improvement"):
            PromotionCriteria(min_brier_improvement=-0.001)

    def test_rejects_negative_drawdown_tolerance(self) -> None:
        with pytest.raises(ValueError, match="max_drawdown_increase"):
            PromotionCriteria(max_drawdown_increase=-0.01)


# ---------------------------------------------------------------------------
# ModelMetrics validation
# ---------------------------------------------------------------------------

class TestModelMetrics:
    def test_valid_construction(self) -> None:
        m = _metrics()
        assert m.brier_score == pytest.approx(0.220)

    def test_rejects_blank_version(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            _metrics(version="  ")

    def test_rejects_brier_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="brier_score"):
            _metrics(brier_score=1.5)

    def test_rejects_negative_log_loss(self) -> None:
        with pytest.raises(ValueError, match="log_loss"):
            _metrics(log_loss=-0.1)

    def test_rejects_drawdown_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="max_drawdown"):
            _metrics(max_drawdown=1.1)

    def test_rejects_negative_n_samples(self) -> None:
        with pytest.raises(ValueError, match="n_samples"):
            _metrics(n_samples=-1)


# ---------------------------------------------------------------------------
# evaluate_challenger — shadow (insufficient samples)
# ---------------------------------------------------------------------------

class TestEvaluateChallengerShadow:
    def test_shadow_when_insufficient_samples(self) -> None:
        champ = _metrics("champ")
        chal = _metrics("chal", n_samples=50)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert isinstance(result, ChallengerEvaluation)
        assert result.status is ChallengerStatus.SHADOW
        assert any("Insufficient" in r for r in result.blocking_reasons)

    def test_shadow_includes_sample_count_in_reason(self) -> None:
        champ = _metrics("champ")
        chal = _metrics("chal", n_samples=10)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert "10" in result.blocking_reasons[0]


# ---------------------------------------------------------------------------
# evaluate_challenger — eligible (all criteria met)
# ---------------------------------------------------------------------------

class TestEvaluateChallengerEligible:
    def test_eligible_when_challenger_clearly_better(self) -> None:
        champ = _metrics("champ", brier_score=0.240, roi=0.03, max_drawdown=0.12, mean_clv=0.01)
        chal = _metrics("chal",  brier_score=0.230, roi=0.05, max_drawdown=0.12, mean_clv=0.02)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert result.status is ChallengerStatus.ELIGIBLE
        assert result.blocking_reasons == []

    def test_eligible_summary_contains_versions(self) -> None:
        champ = _metrics("champion-v1", brier_score=0.240, roi=0.03, max_drawdown=0.10, mean_clv=0.02)
        chal = _metrics("challenger-v2", brier_score=0.230, roi=0.04, max_drawdown=0.10, mean_clv=0.03)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert "champion-v1" in result.evidence_summary
        assert "challenger-v2" in result.evidence_summary


# ---------------------------------------------------------------------------
# evaluate_challenger — rejected (specific criteria failures)
# ---------------------------------------------------------------------------

class TestEvaluateChallengerRejected:
    def test_rejected_insufficient_brier_improvement(self) -> None:
        champ = _metrics("champ", brier_score=0.240)
        # Only 0.001 improvement, need 0.002
        chal = _metrics("chal", brier_score=0.239, roi=0.05, max_drawdown=0.12, mean_clv=0.02)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert result.status is ChallengerStatus.REJECTED
        assert any("Brier" in r for r in result.blocking_reasons)

    def test_rejected_excess_drawdown(self) -> None:
        champ = _metrics("champ", brier_score=0.240, max_drawdown=0.10)
        chal = _metrics("chal",  brier_score=0.230, max_drawdown=0.20, mean_clv=0.02)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert result.status is ChallengerStatus.REJECTED
        assert any("Drawdown" in r or "drawdown" in r for r in result.blocking_reasons)

    def test_rejected_non_positive_clv(self) -> None:
        champ = _metrics("champ", brier_score=0.240)
        chal = _metrics("chal",  brier_score=0.230, mean_clv=-0.01)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert result.status is ChallengerStatus.REJECTED
        assert any("CLV" in r for r in result.blocking_reasons)

    def test_not_rejected_for_clv_when_flag_off(self) -> None:
        criteria = PromotionCriteria(require_positive_clv=False, min_brier_improvement=0.002)
        champ = _metrics("champ", brier_score=0.240, max_drawdown=0.10)
        chal = _metrics("chal",  brier_score=0.230, mean_clv=-0.01, max_drawdown=0.10)
        result = evaluate_challenger(champ, chal, criteria)
        # CLV not blocking when flag is off; Brier improvement is 0.01 > 0.002
        assert not any("CLV" in r for r in result.blocking_reasons)

    def test_multiple_blocking_reasons_collected(self) -> None:
        champ = _metrics("champ", brier_score=0.240, max_drawdown=0.10)
        chal = _metrics("chal",  brier_score=0.239, max_drawdown=0.20, mean_clv=-0.01)
        result = evaluate_challenger(champ, chal, CRITERIA)
        assert result.status is ChallengerStatus.REJECTED
        assert len(result.blocking_reasons) >= 2
