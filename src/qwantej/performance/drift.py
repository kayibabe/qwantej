"""Drift detection for Qwantej's model and data pipeline (framework §44).

Five drift types (§44):
    Feature drift      — input distributions changed.
    Prediction drift   — output probability distributions shifted.
    Calibration drift  — observed frequencies no longer match predictions.
    Market drift       — bookmaker pricing relationships changed.
    Execution drift    — prices move faster / less favourable capture.

All functions are pure: they take arrays of numbers and return
interpretable drift metrics.  No I/O or database access here.

Drift should first *reduce reliability or widen uncertainty* — it does
NOT automatically trigger a model swap.  The champion-challenger framework
governs promotion; drift detection feeds into it as evidence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationDriftResult:
    """Result of a calibration-drift check.

    `mean_calibration_error` — average |predicted_p − observed_freq| across bins.
    `slope` — linear regression slope of observed_freq on predicted_p.
               Perfect calibration → 1.0; < 1 means over-confidence.
    `intercept` — linear regression intercept; perfect → 0.0.
    `n_bins` — number of bins with at least one observation.
    `n_samples` — total predictions evaluated.
    `is_drifted` — True when MCE exceeds `threshold`.
    `threshold` — the MCE threshold used.
    """

    mean_calibration_error: float
    slope: float
    intercept: float
    n_bins: int
    n_samples: int
    is_drifted: bool
    threshold: float


@dataclass(frozen=True)
class PredictionDriftResult:
    """Result of a prediction-drift check between two probability series.

    Compares a *reference* distribution (e.g. training window) against a
    *current* distribution (e.g. recent live predictions) using Population
    Stability Index (PSI).

    PSI interpretation (rule of thumb):
        < 0.10  — no significant drift
        0.10–0.25 — moderate drift; monitor
        > 0.25  — significant drift; investigate
    """

    psi: float
    n_bins: int
    n_reference: int
    n_current: int
    is_drifted: bool
    threshold: float


@dataclass(frozen=True)
class ExecutionDriftResult:
    """Drift in price-capture quality over time.

    Compares mean CLV in a reference window vs. a current window.
    Negative shift in mean CLV indicates worsening execution.
    """

    reference_mean_clv: float
    current_mean_clv: float
    clv_shift: float          # current − reference (negative = worse execution)
    n_reference: int
    n_current: int
    is_drifted: bool
    threshold: float          # minimum acceptable shift (should be <= 0)


# ---------------------------------------------------------------------------
# Calibration drift
# ---------------------------------------------------------------------------

def detect_calibration_drift(
    predicted_probabilities: Sequence[float],
    outcomes: Sequence[float],        # 1.0 = win, 0.0 = loss (voids excluded)
    *,
    n_bins: int = 10,
    threshold: float = 0.05,
) -> CalibrationDriftResult:
    """Detect calibration drift via Mean Calibration Error (MCE).

    Bins predictions into `n_bins` equal-width buckets and computes the
    absolute error between the mean predicted probability and the observed
    win rate in each bin.

    Args:
        predicted_probabilities: P_cons values from settled predictions.
        outcomes: 1.0 for win, 0.0 for loss.  Voids/pushes excluded by caller.
        n_bins: number of equal-width calibration bins (default 10).
        threshold: MCE above which `is_drifted` is set True.

    Raises:
        ValueError: if inputs are inconsistent or n_bins < 2.
    """
    preds = list(predicted_probabilities)
    acts = list(outcomes)
    if len(preds) != len(acts):
        raise ValueError("predicted_probabilities and outcomes must have the same length")
    if n_bins < 2:
        raise ValueError("n_bins must be at least 2")
    if not preds:
        raise ValueError("at least one prediction is required")

    bin_width = 1.0 / n_bins
    bin_pred_sum = [0.0] * n_bins
    bin_act_sum = [0.0] * n_bins
    bin_counts = [0] * n_bins

    for p, o in zip(preds, acts, strict=True):
        if not (0 < p <= 1):
            raise ValueError(f"predicted probability {p!r} is not in (0, 1]")
        if o not in (0.0, 1.0):
            raise ValueError(f"outcome {o!r} must be 0.0 or 1.0")
        idx = min(int(p / bin_width), n_bins - 1)
        bin_pred_sum[idx] += p
        bin_act_sum[idx] += o
        bin_counts[idx] += 1

    active_bins = [(bin_pred_sum[i] / bin_counts[i], bin_act_sum[i] / bin_counts[i])
                   for i in range(n_bins) if bin_counts[i] > 0]

    if not active_bins:
        raise ValueError("no active bins — all predictions fell outside (0, 1]")

    mce = sum(abs(pred - act) for pred, act in active_bins) / len(active_bins)

    # Linear calibration slope/intercept via OLS on bin centroids.
    slope, intercept = _ols(
        [pred for pred, _ in active_bins],
        [act for _, act in active_bins],
    )

    return CalibrationDriftResult(
        mean_calibration_error=mce,
        slope=slope,
        intercept=intercept,
        n_bins=len(active_bins),
        n_samples=len(preds),
        is_drifted=mce > threshold,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Prediction drift (Population Stability Index)
# ---------------------------------------------------------------------------

def detect_prediction_drift(
    reference_probabilities: Sequence[float],
    current_probabilities: Sequence[float],
    *,
    n_bins: int = 10,
    threshold: float = 0.10,
) -> PredictionDriftResult:
    """Detect drift in the distribution of predicted probabilities via PSI.

    PSI = Σ (current_pct − reference_pct) × log(current_pct / reference_pct)

    Small smoothing (1e-10) avoids log(0) when a bin is empty in one window.

    Args:
        reference_probabilities: baseline probability series (e.g. training window).
        current_probabilities: recent probability series to compare.
        n_bins: equal-width bins over [0, 1].
        threshold: PSI above which `is_drifted` is set True.
    """
    ref = list(reference_probabilities)
    cur = list(current_probabilities)
    if not ref or not cur:
        raise ValueError("both reference and current series must be non-empty")
    if n_bins < 2:
        raise ValueError("n_bins must be at least 2")

    bin_width = 1.0 / n_bins
    eps = 1e-10

    ref_counts = [0] * n_bins
    cur_counts = [0] * n_bins

    for p in ref:
        ref_counts[min(int(p / bin_width), n_bins - 1)] += 1
    for p in cur:
        cur_counts[min(int(p / bin_width), n_bins - 1)] += 1

    n_ref = len(ref)
    n_cur = len(cur)

    psi = 0.0
    for r, c in zip(ref_counts, cur_counts, strict=True):
        r_pct = r / n_ref + eps
        c_pct = c / n_cur + eps
        psi += (c_pct - r_pct) * math.log(c_pct / r_pct)

    return PredictionDriftResult(
        psi=psi,
        n_bins=n_bins,
        n_reference=n_ref,
        n_current=n_cur,
        is_drifted=psi > threshold,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Execution drift (CLV shift)
# ---------------------------------------------------------------------------

def detect_execution_drift(
    reference_clv: Sequence[float],
    current_clv: Sequence[float],
    *,
    threshold: float = -0.02,
) -> ExecutionDriftResult:
    """Detect worsening price-capture quality by comparing mean CLV windows.

    Args:
        reference_clv: CLV values in the reference (baseline) window.
        current_clv: CLV values in the current window.
        threshold: `clv_shift` below this triggers `is_drifted`.
                   Negative threshold means tolerate a small CLV decline before alarming.
    """
    if not reference_clv or not current_clv:
        raise ValueError("both reference and current CLV series must be non-empty")
    ref_mean = sum(reference_clv) / len(reference_clv)
    cur_mean = sum(current_clv) / len(current_clv)
    shift = cur_mean - ref_mean
    return ExecutionDriftResult(
        reference_mean_clv=ref_mean,
        current_mean_clv=cur_mean,
        clv_shift=shift,
        n_reference=len(list(reference_clv)),
        n_current=len(list(current_clv)),
        is_drifted=shift < threshold,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ols(x: list[float], y: list[float]) -> tuple[float, float]:
    """Ordinary least squares: return (slope, intercept).  Requires len >= 2."""
    n = len(x)
    if n < 2:
        return 1.0, 0.0
    x_bar = sum(x) / n
    y_bar = sum(y) / n
    ss_xx = sum((xi - x_bar) ** 2 for xi in x)
    ss_xy = sum((xi - x_bar) * (yi - y_bar) for xi, yi in zip(x, y, strict=True))
    if ss_xx == 0:
        return 1.0, 0.0
    slope = ss_xy / ss_xx
    intercept = y_bar - slope * x_bar
    return slope, intercept
