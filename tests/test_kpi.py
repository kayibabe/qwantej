"""Tests for Phase 9: settled-prediction KPI aggregation (framework §39, §40)."""

from __future__ import annotations

import math

import pytest

from qwantej.performance.kpi import (
    KPIReport,
    PerformanceObservation,
    compute_kpis,
    segment_kpis,
)

# ---------------------------------------------------------------------------
# PerformanceObservation validation
# ---------------------------------------------------------------------------

class TestPerformanceObservationValidation:
    def test_valid_win(self) -> None:
        obs = PerformanceObservation(outcome="win", taken_odds=2.00, brier_contribution=0.16)
        assert obs.outcome == "win"

    def test_valid_void(self) -> None:
        obs = PerformanceObservation(outcome="void")
        assert obs.outcome == "void"

    def test_rejects_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="outcome"):
            PerformanceObservation(outcome="cancelled")

    def test_rejects_taken_odds_le_1(self) -> None:
        with pytest.raises(ValueError, match="taken_odds"):
            PerformanceObservation(outcome="win", taken_odds=1.0)

    def test_rejects_non_finite_taken_odds(self) -> None:
        with pytest.raises(ValueError, match="taken_odds"):
            PerformanceObservation(outcome="win", taken_odds=math.inf)

    def test_rejects_negative_stake(self) -> None:
        with pytest.raises(ValueError, match="stake"):
            PerformanceObservation(outcome="win", stake=-1.0)

    def test_rejects_non_finite_profit_loss(self) -> None:
        with pytest.raises(ValueError, match="profit_loss"):
            PerformanceObservation(outcome="win", profit_loss=math.nan)

    def test_rejects_brier_gt_1(self) -> None:
        with pytest.raises(ValueError, match="brier"):
            PerformanceObservation(outcome="win", brier_contribution=1.5)

    def test_rejects_negative_brier(self) -> None:
        with pytest.raises(ValueError, match="brier"):
            PerformanceObservation(outcome="win", brier_contribution=-0.01)

    def test_rejects_non_finite_clv(self) -> None:
        with pytest.raises(ValueError, match="clv"):
            PerformanceObservation(outcome="win", clv=math.inf)

    def test_rejects_taken_probability_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="taken_probability"):
            PerformanceObservation(outcome="win", taken_probability=1.5)

    def test_rejects_zero_taken_probability(self) -> None:
        with pytest.raises(ValueError, match="taken_probability"):
            PerformanceObservation(outcome="win", taken_probability=0.0)

    def test_accepts_taken_probability_unity(self) -> None:
        obs = PerformanceObservation(outcome="win", taken_probability=1.0)
        assert obs.taken_probability == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_kpis — counts
# ---------------------------------------------------------------------------

def _obs(
    outcome: str,
    taken_odds: float | None = 2.0,
    taken_probability: float | None = None,
    brier: float | None = None,
    log_loss: float | None = None,
    clv: float | None = None,
    stake: float | None = None,
    profit_loss: float | None = None,
    market: str | None = None,
    league: str | None = None,
    model_version: str | None = None,
) -> PerformanceObservation:
    return PerformanceObservation(
        outcome=outcome,
        taken_odds=taken_odds,
        taken_probability=taken_probability,
        brier_contribution=brier,
        log_loss_contribution=log_loss,
        clv=clv,
        stake=stake,
        profit_loss=profit_loss,
        market=market,
        league=league,
        model_version=model_version,
    )


class TestComputeKpisCounts:
    def test_empty_input(self) -> None:
        r = compute_kpis([])
        assert isinstance(r, KPIReport)
        assert r.n_total == 0
        assert r.n_settled == 0
        assert r.hit_rate is None
        assert r.brier_score is None

    def test_counts_all_outcomes(self) -> None:
        obs = [_obs("win"), _obs("loss"), _obs("void"), _obs("push")]
        r = compute_kpis(obs)
        assert r.n_total == 4
        assert r.n_wins == 1
        assert r.n_losses == 1
        assert r.n_voids == 1
        assert r.n_pushes == 1
        assert r.n_settled == 2

    def test_hit_rate_all_wins(self) -> None:
        obs = [_obs("win"), _obs("win"), _obs("win")]
        r = compute_kpis(obs)
        assert r.hit_rate == pytest.approx(1.0)

    def test_hit_rate_mixed(self) -> None:
        obs = [_obs("win"), _obs("win"), _obs("loss")]
        r = compute_kpis(obs)
        assert r.hit_rate == pytest.approx(2 / 3)

    def test_hit_rate_none_when_no_settled(self) -> None:
        obs = [_obs("void"), _obs("push")]
        r = compute_kpis(obs)
        assert r.hit_rate is None

    def test_voids_excluded_from_hit_rate_denominator(self) -> None:
        obs = [_obs("win"), _obs("void"), _obs("void")]
        r = compute_kpis(obs)
        assert r.hit_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_kpis — predictive metrics
# ---------------------------------------------------------------------------

class TestComputeKpisPredictive:
    def test_brier_score_mean(self) -> None:
        # Two wins: brier 0.16 and 0.04 → mean 0.10
        obs = [_obs("win", brier=0.16), _obs("win", brier=0.04)]
        r = compute_kpis(obs)
        assert r.brier_score == pytest.approx(0.10)

    def test_brier_none_when_no_contributions(self) -> None:
        obs = [_obs("win"), _obs("loss")]  # no brier_contribution set
        r = compute_kpis(obs)
        assert r.brier_score is None

    def test_brier_excludes_void(self) -> None:
        # void row has brier=None; should not affect mean
        obs = [_obs("win", brier=0.25), _obs("void", brier=None)]
        r = compute_kpis(obs)
        assert r.brier_score == pytest.approx(0.25)

    def test_log_loss_mean(self) -> None:
        obs = [_obs("win", log_loss=0.30), _obs("loss", log_loss=0.70)]
        r = compute_kpis(obs)
        assert r.log_loss == pytest.approx(0.50)

    def test_log_loss_none_without_contributions(self) -> None:
        obs = [_obs("win"), _obs("loss")]
        r = compute_kpis(obs)
        assert r.log_loss is None


# ---------------------------------------------------------------------------
# compute_kpis — CLV
# ---------------------------------------------------------------------------

class TestComputeKpisClv:
    def test_mean_clv_computed(self) -> None:
        obs = [_obs("win", clv=0.05), _obs("loss", clv=-0.02), _obs("void", clv=0.01)]
        r = compute_kpis(obs)
        assert r.mean_clv == pytest.approx((0.05 + -0.02 + 0.01) / 3)
        assert r.n_clv == 3

    def test_mean_clv_none_without_data(self) -> None:
        obs = [_obs("win"), _obs("loss")]
        r = compute_kpis(obs)
        assert r.mean_clv is None
        assert r.n_clv == 0

    def test_n_clv_counts_only_non_none(self) -> None:
        obs = [_obs("win", clv=0.03), _obs("loss")]  # second has no CLV
        r = compute_kpis(obs)
        assert r.n_clv == 1


# ---------------------------------------------------------------------------
# compute_kpis — financial (staked mode)
# ---------------------------------------------------------------------------

class TestComputeKpisFinancial:
    def test_roi_positive(self) -> None:
        # win: stake=10, return=18 → P/L=8; loss: stake=10, P/L=-10
        obs = [
            _obs("win", stake=10.0, profit_loss=8.0),
            _obs("loss", stake=10.0, profit_loss=-10.0),
        ]
        r = compute_kpis(obs)
        assert r.total_stake == pytest.approx(20.0)
        assert r.total_profit == pytest.approx(-2.0)
        assert r.roi == pytest.approx(-2.0 / 20.0)

    def test_roi_none_in_paper_mode(self) -> None:
        obs = [_obs("win"), _obs("loss")]
        r = compute_kpis(obs)
        assert r.roi is None
        assert r.total_stake is None
        assert r.total_profit is None

    def test_financial_fields_accumulate(self) -> None:
        obs = [
            _obs("win", stake=5.0, profit_loss=5.0),
            _obs("win", stake=5.0, profit_loss=5.0),
        ]
        r = compute_kpis(obs)
        assert r.total_stake == pytest.approx(10.0)
        assert r.total_profit == pytest.approx(10.0)
        assert r.roi == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_kpis — max drawdown
# ---------------------------------------------------------------------------

class TestComputeKpisDrawdown:
    def test_no_drawdown_all_wins(self) -> None:
        obs = [_obs("win", taken_odds=2.0), _obs("win", taken_odds=2.0)]
        r = compute_kpis(obs)
        assert r.max_drawdown == pytest.approx(0.0)

    def test_drawdown_after_two_losses(self) -> None:
        # win(+1), loss(-1), loss(-1) → cumul: 1, 0, -1
        # peak=1, trough=-1 → drawdown=2
        obs = [
            _obs("win", taken_odds=2.0),
            _obs("loss", taken_odds=None),
            _obs("loss", taken_odds=None),
        ]
        r = compute_kpis(obs)
        assert r.max_drawdown == pytest.approx(2.0)

    def test_drawdown_none_when_no_observations(self) -> None:
        r = compute_kpis([])
        assert r.max_drawdown is None

    def test_drawdown_void_contributes_zero(self) -> None:
        obs = [_obs("win", taken_odds=2.0), _obs("void"), _obs("void")]
        r = compute_kpis(obs)
        # Cumulative: 1, 1, 1 — no drawdown
        assert r.max_drawdown == pytest.approx(0.0)

    def test_drawdown_uses_real_pl_when_staked(self) -> None:
        # Two wins: P/L = 9.0 each; then one big loss: P/L = -25.0
        obs = [
            _obs("win", stake=10.0, profit_loss=9.0),
            _obs("win", stake=10.0, profit_loss=9.0),
            _obs("loss", stake=10.0, profit_loss=-25.0),
        ]
        r = compute_kpis(obs)
        # Peak cumulative = 18; trough = 18 + (-25) = -7; drawdown = 25
        assert r.max_drawdown == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# segment_kpis
# ---------------------------------------------------------------------------

class TestSegmentKpis:
    def _make_obs(self) -> list[PerformanceObservation]:
        return [
            _obs("win", market="1X2",   league="EPL",    model_version="v1"),
            _obs("loss", market="1X2",  league="EPL",    model_version="v1"),
            _obs("win", market="BTTS",  league="La Liga", model_version="v1"),
            _obs("loss", market="BTTS", league="La Liga", model_version="v2"),
            _obs("void", market="1X2",  league="EPL",    model_version="v2"),
        ]

    def test_segment_by_market(self) -> None:
        obs = self._make_obs()
        result = segment_kpis(obs, by="market")
        assert set(result.keys()) == {"1X2", "BTTS"}
        assert result["1X2"].n_total == 3  # 2 settled + 1 void
        assert result["BTTS"].n_total == 2

    def test_segment_by_league(self) -> None:
        obs = self._make_obs()
        result = segment_kpis(obs, by="league")
        assert "EPL" in result
        assert "La Liga" in result
        assert result["EPL"].n_wins == 1
        assert result["La Liga"].n_wins == 1

    def test_segment_by_model_version(self) -> None:
        obs = self._make_obs()
        result = segment_kpis(obs, by="model_version")
        assert result["v1"].n_settled == 3
        assert result["v2"].n_settled == 1

    def test_segment_unknown_placed_in_bucket(self) -> None:
        obs = [
            _obs("win",  market=None),
            _obs("loss", market="1X2"),
        ]
        result = segment_kpis(obs, by="market")
        assert "(unknown)" in result
        assert result["(unknown)"].n_wins == 1

    def test_segment_rejects_invalid_by(self) -> None:
        with pytest.raises(ValueError, match="by must be one of"):
            segment_kpis([], by="bookmaker")

    def test_segment_empty_observations(self) -> None:
        result = segment_kpis([], by="market")
        assert result == {}

    def test_each_segment_is_independent_kpi_report(self) -> None:
        obs = self._make_obs()
        result = segment_kpis(obs, by="market")
        for report in result.values():
            assert isinstance(report, KPIReport)


# ---------------------------------------------------------------------------
# compute_kpis — average_odds and break_even_hit_rate
# ---------------------------------------------------------------------------

class TestComputeKpisOdds:
    def test_average_odds_computed(self) -> None:
        obs = [_obs("win", taken_odds=2.0), _obs("loss", taken_odds=3.0)]
        r = compute_kpis(obs)
        assert r.average_odds == pytest.approx(2.5)

    def test_average_odds_none_when_no_odds(self) -> None:
        obs = [_obs("win", taken_odds=None), _obs("loss", taken_odds=None)]
        r = compute_kpis(obs)
        assert r.average_odds is None

    def test_break_even_hit_rate(self) -> None:
        # At 2.0 odds break-even = 0.5; at 4.0 = 0.25; mean = 0.375
        obs = [_obs("win", taken_odds=2.0), _obs("loss", taken_odds=4.0)]
        r = compute_kpis(obs)
        assert r.break_even_hit_rate == pytest.approx(0.375)

    def test_average_odds_excludes_void(self) -> None:
        # void rows are excluded from odds aggregation
        obs = [_obs("win", taken_odds=2.0), _obs("void", taken_odds=3.0)]
        r = compute_kpis(obs)
        assert r.average_odds == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# compute_kpis — calibration (ECE, slope, intercept, BSS)
# ---------------------------------------------------------------------------

class TestComputeKpisCalibration:
    def _perfect_calibrated(self) -> list[PerformanceObservation]:
        """Perfectly calibrated 50% predictions: always 0.5 taken_probability."""
        return [
            _obs("win",  taken_probability=0.5, brier=0.25),
            _obs("loss", taken_probability=0.5, brier=0.25),
            _obs("win",  taken_probability=0.5, brier=0.25),
            _obs("loss", taken_probability=0.5, brier=0.25),
        ]

    def test_calibration_fields_populated_with_probabilities(self) -> None:
        obs = self._perfect_calibrated()
        r = compute_kpis(obs)
        assert r.ece is not None
        assert r.calibration_slope is not None
        assert r.calibration_intercept is not None

    def test_calibration_none_without_probabilities(self) -> None:
        obs = [_obs("win", brier=0.16), _obs("loss", brier=0.16)]
        r = compute_kpis(obs)
        assert r.ece is None
        assert r.calibration_slope is None
        assert r.calibration_intercept is None

    def test_brier_skill_score_computed(self) -> None:
        # Perfect hit rate 0.5, brier=0.25 → reference_brier=0.25, BSS=0
        obs = [
            _obs("win",  brier=0.25, taken_probability=0.5),
            _obs("loss", brier=0.25, taken_probability=0.5),
        ]
        r = compute_kpis(obs)
        assert r.brier_score == pytest.approx(0.25)
        assert r.hit_rate == pytest.approx(0.5)
        assert r.brier_skill_score == pytest.approx(0.0, abs=1e-9)

    def test_brier_skill_score_none_without_brier(self) -> None:
        obs = [_obs("win"), _obs("loss")]
        r = compute_kpis(obs)
        assert r.brier_skill_score is None

    def test_brier_skill_score_positive_when_better_than_naive(self) -> None:
        # Excellent model: brier=0.04, hit_rate=0.8 → ref=0.16, BSS=0.75
        obs = [
            _obs("win",  brier=0.04, taken_probability=0.8),
            _obs("win",  brier=0.04, taken_probability=0.8),
            _obs("win",  brier=0.04, taken_probability=0.8),
            _obs("win",  brier=0.04, taken_probability=0.8),
            _obs("loss", brier=0.36, taken_probability=0.8),
        ]
        r = compute_kpis(obs)
        assert r.hit_rate == pytest.approx(0.8)
        assert r.brier_score == pytest.approx((0.04 * 4 + 0.36) / 5)
        assert r.brier_skill_score is not None
        assert r.brier_skill_score > 0


# ---------------------------------------------------------------------------
# compute_kpis — volatility
# ---------------------------------------------------------------------------

class TestComputeKpisVolatility:
    def test_volatility_none_when_single_observation(self) -> None:
        obs = [_obs("win", taken_odds=2.0)]
        r = compute_kpis(obs)
        assert r.volatility is None

    def test_volatility_zero_when_all_same_pl(self) -> None:
        obs = [
            _obs("win", stake=10.0, profit_loss=9.0),
            _obs("win", stake=10.0, profit_loss=9.0),
            _obs("win", stake=10.0, profit_loss=9.0),
        ]
        r = compute_kpis(obs)
        assert r.volatility == pytest.approx(0.0, abs=1e-9)

    def test_volatility_positive_for_mixed_results(self) -> None:
        obs = [
            _obs("win",  taken_odds=2.0),
            _obs("loss", taken_odds=None),
            _obs("win",  taken_odds=3.0),
            _obs("loss", taken_odds=None),
        ]
        r = compute_kpis(obs)
        assert r.volatility is not None
        assert r.volatility > 0

    def test_volatility_none_when_empty(self) -> None:
        r = compute_kpis([])
        assert r.volatility is None

    def test_volatility_uses_real_pl_when_staked(self) -> None:
        obs = [
            _obs("win",  stake=10.0, profit_loss=90.0),
            _obs("loss", stake=10.0, profit_loss=-10.0),
        ]
        r = compute_kpis(obs)
        assert r.volatility is not None
        # sample std of [90, -10]: mean=40, deviations=[50, -50], var=5000/1=5000
        assert r.volatility == pytest.approx(50.0 * math.sqrt(2.0), rel=1e-6)
