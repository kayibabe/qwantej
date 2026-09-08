"""Settled-prediction KPI aggregation (framework §39, §40).

Computes segment-level performance metrics from a sequence of settled
observations.  All functions are pure — no I/O.

KPI dimensions (§40):
  Predictive   — Brier score, Brier Skill Score, log-loss, ECE,
                 calibration slope/intercept
  Betting      — ROI/yield, hit rate, break-even hit rate, average odds
  Market       — mean CLV
  Risk         — maximum drawdown, volatility (P/L std)

Segmentation (§39): by market, league, or model_version.

Calibration metrics (ECE, slope, intercept, BSS) are computed from the
``taken_probability`` field; observations that omit it contribute only to
the count-based and financial metrics.  Callers should pass them in
``settled_at`` order for a meaningful ``max_drawdown`` and ``volatility``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from qwantej.performance.drift import detect_calibration_drift

_VALID_OUTCOMES = frozenset({"win", "loss", "void", "push"})

_N_BINS_ECE = 10      # bins used for ECE / calibration slope/intercept
_MIN_CALIB_N = 2      # minimum samples to attempt calibration metrics


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerformanceObservation:
    """One settled prediction or accumulator observation.

    Args:
        outcome: "win", "loss", "void", or "push".
        taken_probability: P_cons used at decision time (for calibration
            metrics: ECE, slope/intercept, BSS); None if not recorded.
        taken_odds: decimal odds at which the bet was taken (> 1).
        stake: actual stake (> 0); None for paper-mode observations.
        profit_loss: signed P/L; None when stake is None.
        clv: probability-space CLV (closing_implied − taken_implied).
        brier_contribution: pre-computed (p − outcome)² from the settlement
            engine; None for void/push or when taken_probability is absent.
        log_loss_contribution: pre-computed log-loss contribution; None for
            void/push or when taken_probability is absent.
        market: e.g. "1X2", "BTTS", "DOUBLE_CHANCE", "TOTALS".
        league: competition name or identifier for segmentation.
        model_version: model/policy version string for segmentation.
    """

    outcome: str
    taken_probability: float | None = None
    taken_odds: float | None = None
    stake: float | None = None
    profit_loss: float | None = None
    clv: float | None = None
    brier_contribution: float | None = None
    log_loss_contribution: float | None = None
    market: str | None = None
    league: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(
                f"outcome {self.outcome!r} must be one of {sorted(_VALID_OUTCOMES)}"
            )
        if self.taken_probability is not None:
            if not math.isfinite(self.taken_probability) or not 0 < self.taken_probability <= 1:
                raise ValueError("taken_probability must be finite and in (0, 1]")
        if self.taken_odds is not None:
            if not math.isfinite(self.taken_odds) or self.taken_odds <= 1:
                raise ValueError("taken_odds must be a finite decimal odds > 1")
        if self.stake is not None:
            if not math.isfinite(self.stake) or self.stake <= 0:
                raise ValueError("stake must be a finite positive number")
        if self.profit_loss is not None and not math.isfinite(self.profit_loss):
            raise ValueError("profit_loss must be finite")
        if self.clv is not None and not math.isfinite(self.clv):
            raise ValueError("clv must be finite")
        for name, value in (
            ("brier_contribution", self.brier_contribution),
            ("log_loss_contribution", self.log_loss_contribution),
        ):
            if value is not None:
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"{name} must be a non-negative finite float")
        if self.brier_contribution is not None and self.brier_contribution > 1:
            raise ValueError("brier_contribution must be in [0, 1]")


@dataclass(frozen=True)
class KPIReport:
    """Aggregated performance KPIs for a segment of settled observations.

    Counts cover all observations including voids and pushes.
    Metrics requiring settled (win/loss) outcomes are None when no such
    observations exist.  ROI/financial fields are None in paper mode.
    Calibration fields (ece, calibration_slope/intercept, brier_skill_score)
    are None when fewer than two observations carry taken_probability.
    """

    # --- Counts ---
    n_total: int
    n_settled: int       # win + loss only (excludes void and push)
    n_wins: int
    n_losses: int
    n_voids: int
    n_pushes: int

    # --- Betting ---
    hit_rate: float | None           # n_wins / n_settled
    average_odds: float | None       # mean taken_odds for settled rows with odds
    break_even_hit_rate: float | None  # mean(1/taken_odds) = break-even fraction

    # --- Predictive ---
    brier_score: float | None        # mean brier_contribution over settled rows
    brier_skill_score: float | None  # 1 - brier_score / (hit_rate*(1-hit_rate))
    log_loss: float | None           # mean log_loss_contribution over settled rows
    ece: float | None                # Expected Calibration Error (from taken_probability)
    calibration_slope: float | None  # OLS slope (perfect = 1.0)
    calibration_intercept: float | None  # OLS intercept (perfect = 0.0)

    # --- Market quality ---
    mean_clv: float | None           # mean CLV over rows with non-None CLV
    n_clv: int                       # number of observations with CLV data

    # --- Financial (None in paper mode) ---
    roi: float | None                # sum(profit_loss) / sum(stake); alias: yield
    total_stake: float | None        # sum(stake)
    total_profit: float | None       # sum(profit_loss)

    # --- Risk ---
    max_drawdown: float | None       # peak-to-trough on ordered P/L sequence
    volatility: float | None         # sample std-dev of ordered P/L sequence


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_kpis(observations: Sequence[PerformanceObservation]) -> KPIReport:
    """Compute all KPIs for a flat sequence of observations.

    Observations are processed in the order supplied; pass them sorted by
    ``settled_at`` for meaningful ``max_drawdown`` and ``volatility``.

    Returns a :class:`KPIReport` with all available metrics populated.
    Metrics with insufficient data are None.
    """
    n_wins = n_losses = n_voids = n_pushes = 0
    brier_sum = brier_n = 0.0
    log_sum = log_n = 0.0
    clv_sum = clv_n = 0
    stake_sum: float | None = None
    pl_sum: float | None = None
    unit_pl: list[float] = []   # ordered unit P/L for drawdown/volatility
    real_pl: list[float] = []   # ordered real P/L (staked mode)

    # For calibration metrics: (taken_probability, binary_outcome) pairs
    calib_probs: list[float] = []
    calib_outcomes: list[float] = []

    # For average_odds / break_even_hit_rate
    odds_list: list[float] = []

    for obs in observations:
        if obs.outcome == "win":
            n_wins += 1
        elif obs.outcome == "loss":
            n_losses += 1
        elif obs.outcome == "void":
            n_voids += 1
        else:
            n_pushes += 1

        # Predictive metrics — settled (win/loss) rows only
        if obs.outcome in ("win", "loss"):
            if obs.brier_contribution is not None:
                brier_sum += obs.brier_contribution
                brier_n += 1
            if obs.log_loss_contribution is not None:
                log_sum += obs.log_loss_contribution
                log_n += 1
            if obs.taken_probability is not None:
                calib_probs.append(obs.taken_probability)
                calib_outcomes.append(1.0 if obs.outcome == "win" else 0.0)
            if obs.taken_odds is not None:
                odds_list.append(obs.taken_odds)

        # CLV — any outcome with a recorded value
        if obs.clv is not None:
            clv_sum += obs.clv
            clv_n += 1

        # Financial
        if obs.stake is not None and obs.profit_loss is not None:
            stake_sum = (stake_sum or 0.0) + obs.stake
            pl_sum = (pl_sum or 0.0) + obs.profit_loss
            real_pl.append(obs.profit_loss)

        # Unit P/L for drawdown/volatility when no real stakes
        if obs.outcome == "win" and obs.taken_odds is not None:
            unit_pl.append(obs.taken_odds - 1.0)
        elif obs.outcome == "loss":
            unit_pl.append(-1.0)
        elif obs.outcome in ("void", "push"):
            unit_pl.append(0.0)

    n_settled = n_wins + n_losses
    n_total = n_settled + n_voids + n_pushes

    hit_rate = n_wins / n_settled if n_settled > 0 else None

    # --- Average odds / break-even hit rate ---
    average_odds = sum(odds_list) / len(odds_list) if odds_list else None
    break_even_hit_rate = (
        sum(1.0 / o for o in odds_list) / len(odds_list) if odds_list else None
    )

    # --- Brier Skill Score ---
    brier_score = brier_sum / brier_n if brier_n > 0 else None
    if brier_score is not None and hit_rate is not None:
        reference_brier = hit_rate * (1.0 - hit_rate)
        brier_skill_score: float | None = (
            1.0 - brier_score / reference_brier
            if reference_brier > 0
            else None
        )
    else:
        brier_skill_score = None

    # --- Calibration metrics (ECE, slope, intercept) ---
    ece: float | None = None
    calibration_slope: float | None = None
    calibration_intercept: float | None = None
    if len(calib_probs) >= _MIN_CALIB_N:
        try:
            drift_result = detect_calibration_drift(
                calib_probs, calib_outcomes, n_bins=_N_BINS_ECE
            )
            ece = drift_result.mean_calibration_error
            calibration_slope = drift_result.slope
            calibration_intercept = drift_result.intercept
        except ValueError:
            pass  # not enough data for calibration bins

    # --- ROI ---
    roi: float | None = None
    if stake_sum is not None and stake_sum > 0 and pl_sum is not None:
        roi = pl_sum / stake_sum

    # --- Drawdown and volatility ---
    pl_sequence = real_pl if real_pl else unit_pl
    max_drawdown: float | None = _max_drawdown(pl_sequence) if pl_sequence else None
    volatility: float | None = _sample_std(pl_sequence) if len(pl_sequence) >= 2 else None

    return KPIReport(
        n_total=n_total,
        n_settled=n_settled,
        n_wins=n_wins,
        n_losses=n_losses,
        n_voids=n_voids,
        n_pushes=n_pushes,
        hit_rate=hit_rate,
        average_odds=average_odds,
        break_even_hit_rate=break_even_hit_rate,
        brier_score=brier_score,
        brier_skill_score=brier_skill_score,
        log_loss=log_sum / log_n if log_n > 0 else None,
        ece=ece,
        calibration_slope=calibration_slope,
        calibration_intercept=calibration_intercept,
        mean_clv=clv_sum / clv_n if clv_n > 0 else None,
        n_clv=clv_n,
        roi=roi,
        total_stake=stake_sum,
        total_profit=pl_sum,
        max_drawdown=max_drawdown,
        volatility=volatility,
    )


def segment_kpis(
    observations: Sequence[PerformanceObservation],
    *,
    by: str,
) -> dict[str, KPIReport]:
    """Compute KPIs grouped by a segmentation dimension.

    Args:
        observations: settled observations, ideally sorted by ``settled_at``.
        by: one of ``"market"``, ``"league"``, or ``"model_version"``.

    Returns:
        A dict mapping each segment value to its :class:`KPIReport`.
        Observations whose segmentation attribute is None are collected under
        the key ``"(unknown)"``.

    Raises:
        ValueError: if *by* is not a recognised segmentation dimension.
    """
    valid_by = {"market", "league", "model_version"}
    if by not in valid_by:
        raise ValueError(f"by must be one of {sorted(valid_by)}, got {by!r}")

    groups: dict[str, list[PerformanceObservation]] = {}
    for obs in observations:
        key = getattr(obs, by)
        if key is None:
            key = "(unknown)"
        groups.setdefault(key, []).append(obs)

    return {seg: compute_kpis(group) for seg, group in groups.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _max_drawdown(profits: list[float]) -> float:
    """Max peak-to-trough drawdown on a cumulative P/L series."""
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for profit in profits:
        cumulative += profit
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def _sample_std(values: list[float]) -> float:
    """Sample standard deviation (Bessel-corrected, n-1 denominator)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)
