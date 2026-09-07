"""Tests for Phase 9: settlement engine, CLV and calibration bin (framework §38)."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from qwantej.settlement import (
    SettledPrediction,
    SettlementOutcome,
    brier_contribution,
    calibration_bin,
    clv_log_odds,
    clv_probability,
    log_loss_contribution,
    settle,
)
from qwantej.settlement.clv import closing_probability_from_odds

NOW = datetime(2026, 9, 7, 20, tzinfo=UTC)


# ---------------------------------------------------------------------------
# CLV helpers
# ---------------------------------------------------------------------------

class TestClvProbability:
    def test_positive_clv_when_taken_better(self) -> None:
        # Taken p=0.60, closing p=0.55 → CLV = +0.05 (got the better price)
        assert clv_probability(0.60, 0.55) == pytest.approx(0.05)

    def test_negative_clv_when_taken_worse(self) -> None:
        assert clv_probability(0.50, 0.58) == pytest.approx(-0.08)

    def test_zero_clv_same_probability(self) -> None:
        assert clv_probability(0.55, 0.55) == pytest.approx(0.0)

    def test_rejects_invalid_probability(self) -> None:
        with pytest.raises(ValueError):
            clv_probability(1.1, 0.5)
        with pytest.raises(ValueError):
            clv_probability(0.5, 0.0)


class TestClvLogOdds:
    def test_positive_when_taken_higher_odds(self) -> None:
        # Took 2.00, closing 1.80 → log(2/1.8) > 0
        assert clv_log_odds(2.00, 1.80) > 0

    def test_negative_when_taken_lower_odds(self) -> None:
        assert clv_log_odds(1.80, 2.00) < 0

    def test_zero_when_same_odds(self) -> None:
        assert clv_log_odds(2.0, 2.0) == pytest.approx(0.0)

    def test_rejects_odds_le_1(self) -> None:
        with pytest.raises(ValueError):
            clv_log_odds(1.0, 2.0)
        with pytest.raises(ValueError):
            clv_log_odds(2.0, 0.9)


class TestClosingProbabilityFromOdds:
    def test_basic_conversion(self) -> None:
        assert closing_probability_from_odds(2.0) == pytest.approx(0.5)

    def test_with_vig_factor(self) -> None:
        # 5% vig: 1/2.0 * 1.05 = 0.525
        assert closing_probability_from_odds(2.0, vig_factor=1.05) == pytest.approx(0.525)

    def test_rejects_odds_le_1(self) -> None:
        with pytest.raises(ValueError):
            closing_probability_from_odds(0.5)

    def test_rejects_nonpositive_vig(self) -> None:
        with pytest.raises(ValueError):
            closing_probability_from_odds(2.0, vig_factor=0.0)


class TestCalibrationBin:
    def test_standard_bin(self) -> None:
        assert calibration_bin(0.63) == "0.60-0.70"

    def test_lower_boundary(self) -> None:
        assert calibration_bin(0.60) == "0.60-0.70"

    def test_upper_boundary(self) -> None:
        # 1.0 is the highest probability; it falls in the last bin [0.90, 1.00].
        assert calibration_bin(1.0) == "0.90-1.00"

    def test_zero_edge(self) -> None:
        assert calibration_bin(0.01) == "0.00-0.10"

    def test_custom_width(self) -> None:
        assert calibration_bin(0.63, width=0.05) == "0.60-0.65"

    def test_rejects_invalid_probability(self) -> None:
        with pytest.raises(ValueError):
            calibration_bin(0.0)
        with pytest.raises(ValueError):
            calibration_bin(1.01)


# ---------------------------------------------------------------------------
# Brier and log-loss contributions
# ---------------------------------------------------------------------------

class TestBrierContribution:
    def test_perfect_win_prediction(self) -> None:
        # p=1.0, outcome=win → (1-1)²=0
        assert brier_contribution(1.0, SettlementOutcome.WIN) == pytest.approx(0.0)

    def test_wrong_win_prediction(self) -> None:
        # p=1.0, outcome=loss → (1-0)²=1
        assert brier_contribution(1.0, SettlementOutcome.LOSS) == pytest.approx(1.0)

    def test_fifty_fifty(self) -> None:
        # p=0.5, outcome=win → (0.5-1)²=0.25
        assert brier_contribution(0.5, SettlementOutcome.WIN) == pytest.approx(0.25)

    def test_void_returns_zero(self) -> None:
        assert brier_contribution(0.7, SettlementOutcome.VOID) == pytest.approx(0.0)

    def test_push_returns_zero(self) -> None:
        assert brier_contribution(0.7, SettlementOutcome.PUSH) == pytest.approx(0.0)

    def test_result_in_unit_interval(self) -> None:
        for p in (0.1, 0.5, 0.9):
            for o in (SettlementOutcome.WIN, SettlementOutcome.LOSS):
                assert 0 <= brier_contribution(p, o) <= 1


class TestLogLossContribution:
    def test_perfect_win(self) -> None:
        # p=1-ε, outcome=win → near 0
        assert log_loss_contribution(1.0 - 1e-10, SettlementOutcome.WIN) == pytest.approx(
            0.0, abs=1e-8
        )

    def test_void_returns_zero(self) -> None:
        assert log_loss_contribution(0.6, SettlementOutcome.VOID) == pytest.approx(0.0)

    def test_nonnegative(self) -> None:
        for p in (0.1, 0.5, 0.9):
            assert log_loss_contribution(p, SettlementOutcome.WIN) >= 0
            assert log_loss_contribution(p, SettlementOutcome.LOSS) >= 0

    def test_lower_for_correct_prediction(self) -> None:
        # Correct high-confidence prediction has lower log-loss
        assert (
            log_loss_contribution(0.9, SettlementOutcome.WIN)
            < log_loss_contribution(0.5, SettlementOutcome.WIN)
        )


# ---------------------------------------------------------------------------
# settle() — main entry point
# ---------------------------------------------------------------------------

class TestSettle:
    def _win(self, **kwargs: object) -> SettledPrediction:
        return settle(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.WIN,
            settled_at=NOW,
            taken_probability=0.60,
            decimal_odds=2.00,
            closing_odds=1.80,
            stake=10.0,
            **kwargs,
        )

    def test_financial_win(self) -> None:
        s = self._win()
        assert s.gross_return == pytest.approx(20.0)
        assert s.profit_loss == pytest.approx(10.0)

    def test_financial_loss(self) -> None:
        s = settle(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.LOSS,
            settled_at=NOW,
            stake=10.0,
            decimal_odds=2.00,
        )
        assert s.gross_return == pytest.approx(0.0)
        assert s.profit_loss == pytest.approx(-10.0)

    def test_void_stake_returned(self) -> None:
        s = settle(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.VOID,
            settled_at=NOW,
            stake=10.0,
            decimal_odds=2.00,
        )
        assert s.gross_return == pytest.approx(10.0)
        assert s.profit_loss == pytest.approx(0.0)

    def test_clv_computed(self) -> None:
        s = self._win()
        # taken_p=0.60, closing = 1/1.80 ≈ 0.5556 → CLV ≈ +0.044
        assert s.clv is not None
        assert s.clv > 0

    def test_brier_computed_for_win(self) -> None:
        s = self._win()
        assert s.brier_contribution == pytest.approx((0.60 - 1.0) ** 2)

    def test_calibration_bin_set(self) -> None:
        s = self._win()
        assert s.calibration_bin == "0.60-0.70"

    def test_paper_mode_no_financials(self) -> None:
        s = settle(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.WIN,
            settled_at=NOW,
        )
        assert s.stake is None
        assert s.gross_return is None
        assert s.profit_loss is None

    def test_no_closing_odds_no_clv(self) -> None:
        s = settle(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.WIN,
            settled_at=NOW,
            taken_probability=0.60,
        )
        assert s.clv is None
        assert s.closing_probability is None

    def test_reason_codes_default_empty(self) -> None:
        s = self._win()
        assert s.reason_codes == []

    def test_reason_codes_attached(self) -> None:
        s = self._win(reason_codes=["CORRECTION"])
        assert "CORRECTION" in s.reason_codes

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            settle(
                subject_type="prediction",
                subject_id="pred-001",
                outcome=SettlementOutcome.WIN,
                settled_at=datetime(2026, 9, 7, 20),
            )

    def test_rejects_invalid_subject_type(self) -> None:
        with pytest.raises(ValueError, match="subject_type"):
            settle(
                subject_type="leg",
                subject_id="pred-001",
                outcome=SettlementOutcome.WIN,
                settled_at=NOW,
            )

    def test_accumulator_subject_type_accepted(self) -> None:
        s = settle(
            subject_type="accumulator",
            subject_id="acca-001",
            outcome=SettlementOutcome.WIN,
            settled_at=NOW,
        )
        assert s.subject_type == "accumulator"


# ---------------------------------------------------------------------------
# SettledPrediction validation
# ---------------------------------------------------------------------------

class TestSettledPredictionValidation:
    def _base(self, **kwargs: object) -> SettledPrediction:
        defaults: dict = dict(
            subject_type="prediction",
            subject_id="pred-001",
            outcome=SettlementOutcome.WIN,
            settled_at=NOW,
            stake=None,
            gross_return=None,
            profit_loss=None,
            taken_probability=None,
            closing_odds=None,
            closing_probability=None,
            clv=None,
            brier_contribution=None,
            log_loss_contribution=None,
            calibration_bin=None,
            result_source=None,
            reason_codes=[],
        )
        defaults.update(kwargs)
        return SettledPrediction(**defaults)

    def test_valid_construction(self) -> None:
        s = self._base()
        assert s.outcome is SettlementOutcome.WIN

    def test_rejects_blank_subject_id(self) -> None:
        with pytest.raises(ValueError, match="subject_id"):
            self._base(subject_id="  ")

    def test_rejects_invalid_stake(self) -> None:
        with pytest.raises(ValueError, match="stake"):
            self._base(stake=-1.0)

    def test_rejects_out_of_range_brier(self) -> None:
        with pytest.raises(ValueError, match="brier"):
            self._base(brier_contribution=1.5)

    def test_rejects_non_finite_log_loss(self) -> None:
        with pytest.raises(ValueError, match="log_loss"):
            self._base(log_loss_contribution=math.inf)
