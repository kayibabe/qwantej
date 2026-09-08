"""Settled-prediction KPI aggregation (framework §39, §40).

Computes segment-level performance metrics from a sequence of settled
observations.  All functions are pure — no I/O.

KPI dimensions (§40):
  Predictive   — Brier score, log-loss
  Betting      — ROI, hit rate, break-even hit rate, average odds
  Market       — mean CLV
  Risk         — maximum drawdown (unit P/L sequence)

Segmentation (§39): by market, league, or model_version.

Max-drawdown uses the same unit-P/L algorithm as the backtest module —
each observation contributes ``profit_loss`` (if staked) or ``taken_odds − 1``
for a win / ``−1`` for a loss (paper mode).  The ordering of observations
passed in is preserved; callers should supply them in ``settled_at`` order.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

_VALID_OUTCOMES = frozenset({"win", "loss", "void", "push"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerformanceObservation:
    """One settled prediction or accumulator observation.

    Args:
        outcome: "win", "loss", "void", or "push".
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
    Metrics that require settled (win/loss) outcomes are None when no
    such observations are present, or when none carry the required field.
    ROI and total_profit/stake are None for paper-mode segments.
    """

    n_total: int
    n_settled: int       # win + loss only (excludes void and push)
    n_wins: int
    n_losses: int
    n_voids: int
    n_pushes: int
    hit_rate: float | None           # n_wins / n_settled
    brier_score: float | None        # mean brier_contribution over settled rows
    log_loss: float | None           # mean log_loss_contribution over settled rows
    roi: float | None                # sum(profit_loss) / sum(stake)
    mean_clv: float | None           # mean CLV over rows with non-None CLV
    n_clv: int                       # number of observations with CLV data
    total_stake: float | None        # sum(stake); None in paper mode
    total_profit: float | None       # sum(profit_loss); None in paper mode
    max_drawdown: float | None       # peak-to-trough on ordered P/L sequence


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_kpis(observations: Sequence[PerformanceObservation]) -> KPIReport:
    """Compute all KPIs for a flat sequence of observations.

    Observations are processed in the order supplied; pass them sorted by
    ``settled_at`` for a meaningful ``max_drawdown``.

    Returns a :class:`KPIReport` with all available metrics populated.
    Metrics that have no data (e.g. ROI when no stake is recorded) are None.
    """
    n_wins = n_losses = n_voids = n_pushes = 0
    brier_sum = brier_n = 0.0
    log_sum = log_n = 0.0
    clv_sum = clv_n = 0
    stake_sum: float | None = None
    pl_sum: float | None = None
    unit_pl: list[float] = []   # for drawdown when no real stakes

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

        # CLV — any outcome with a recorded value
        if obs.clv is not None:
            clv_sum += obs.clv
            clv_n += 1

        # Financial
        if obs.stake is not None and obs.profit_loss is not None:
            stake_sum = (stake_sum or 0.0) + obs.stake
            pl_sum = (pl_sum or 0.0) + obs.profit_loss

        # Unit P/L for drawdown
        if obs.outcome == "win" and obs.taken_odds is not None:
            unit_pl.append(obs.taken_odds - 1.0)
        elif obs.outcome == "loss":
            unit_pl.append(-1.0)
        # void/push contribute 0 to cumulative drawdown path
        elif obs.outcome in ("void", "push"):
            unit_pl.append(0.0)

    n_settled = n_wins + n_losses
    n_total = n_settled + n_voids + n_pushes

    roi: float | None = None
    if stake_sum is not None and stake_sum > 0 and pl_sum is not None:
        roi = pl_sum / stake_sum

    # Drawdown: use real P/L if staked, else unit sequence
    if stake_sum is not None and pl_sum is not None:
        real_pl = [
            float(obs.profit_loss)
            for obs in observations
            if obs.profit_loss is not None
        ]
        max_dd: float | None = _max_drawdown(real_pl) if real_pl else None
    elif unit_pl:
        max_dd = _max_drawdown(unit_pl)
    else:
        max_dd = None

    return KPIReport(
        n_total=n_total,
        n_settled=n_settled,
        n_wins=n_wins,
        n_losses=n_losses,
        n_voids=n_voids,
        n_pushes=n_pushes,
        hit_rate=n_wins / n_settled if n_settled > 0 else None,
        brier_score=brier_sum / brier_n if brier_n > 0 else None,
        log_loss=log_sum / log_n if log_n > 0 else None,
        roi=roi,
        mean_clv=clv_sum / clv_n if clv_n > 0 else None,
        n_clv=clv_n,
        total_stake=stake_sum,
        total_profit=pl_sum,
        max_drawdown=max_dd,
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
# Helper
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
