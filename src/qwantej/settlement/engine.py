"""Settlement engine: pure functions to evaluate and settle a prediction (framework §38, §42).

All functions here are pure — no I/O, no database access.  The application
layer (backend/services/) calls these and persists the returned
`SettledPrediction` to the `settlements` table.
"""

from __future__ import annotations

import math
from datetime import datetime

from qwantej.settlement.clv import calibration_bin, closing_probability_from_odds
from qwantej.settlement.types import SettledPrediction, SettlementOutcome


def brier_contribution(predicted_probability: float, outcome: SettlementOutcome) -> float:
    """Per-prediction Brier score contribution: (p − o)².

    Returns a value in [0, 1].  Lower is better.
    Void/push outcomes return 0.0 (they do not contribute to Brier scoring).
    """
    if outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH):
        return 0.0
    o = 1.0 if outcome is SettlementOutcome.WIN else 0.0
    return (predicted_probability - o) ** 2


def log_loss_contribution(predicted_probability: float, outcome: SettlementOutcome) -> float:
    """Per-prediction log-loss contribution: −[o·log(p) + (1−o)·log(1−p)].

    Returns a non-negative finite float.
    Void/push outcomes return 0.0.
    Probability is clamped to [1e-15, 1−1e-15] to avoid log(0).
    """
    if outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH):
        return 0.0
    eps = 1e-15
    p = max(eps, min(1.0 - eps, predicted_probability))
    o = 1.0 if outcome is SettlementOutcome.WIN else 0.0
    return -(o * math.log(p) + (1.0 - o) * math.log(1.0 - p))


def gross_return_for_outcome(
    stake: float,
    decimal_odds: float,
    outcome: SettlementOutcome,
) -> float:
    """Gross return (including stake) for a settled bet.

    - WIN  → stake × decimal_odds
    - LOSS → 0.0
    - VOID / PUSH → stake (stake returned)
    """
    if outcome is SettlementOutcome.WIN:
        return stake * decimal_odds
    if outcome is SettlementOutcome.LOSS:
        return 0.0
    return stake  # void / push: stake returned


def settle(
    *,
    subject_type: str,
    subject_id: str,
    outcome: SettlementOutcome,
    settled_at: datetime,
    taken_probability: float | None = None,
    taken_odds: float | None = None,
    decimal_odds: float | None = None,
    closing_odds: float | None = None,
    closing_vig_factor: float = 1.0,
    stake: float | None = None,
    result_source: str | None = None,
    reason_codes: list[str] | None = None,
) -> SettledPrediction:
    """Compute all settlement metrics and return a `SettledPrediction`.

    This is the single entry point for the settlement engine.  All metrics
    (Brier, log-loss, CLV, P/L) are derived here from first principles so
    the persistence layer records exactly what was computed and why.

    Args:
        subject_type: "prediction" or "accumulator".
        subject_id: UUID string of the subject.
        outcome: win/loss/void/push.
        settled_at: timezone-aware settlement timestamp.
        taken_probability: P_cons recorded at decision time (for Brier/log-loss only).
        taken_odds: decimal odds at which the bet was struck (for CLV; use this,
            not taken_probability, when computing CLV — pass the bookmaker price).
        decimal_odds: alias / synonym for taken_odds when the same value drives P/L.
            If both are supplied, taken_odds is used for CLV; decimal_odds for P/L.
            Prefer supplying taken_odds explicitly.
        closing_odds: final market odds (for CLV).
        closing_vig_factor: total overround of the closing market (default 1.0).
        stake: amount staked (None → paper tracking, financial fields omitted).
        result_source: where the result came from (e.g. "api-football").
        reason_codes: any audit codes to attach (e.g. ["CORRECTION"]).
    """
    # Resolve taken_odds: explicit parameter wins; fall back to decimal_odds.
    _taken_odds: float | None = taken_odds if taken_odds is not None else decimal_odds

    # Financial
    gross_ret: float | None = None
    pl: float | None = None
    if stake is not None and _taken_odds is not None:
        gross_ret = gross_return_for_outcome(stake, _taken_odds, outcome)
        pl = gross_ret - stake

    # CLV — closing_implied − taken_implied so positive = beat the line (§39).
    # Higher taken_odds > closing_odds → taken_implied < closing_implied → CLV > 0.
    # Uses the bookmaker price (taken_odds), NOT the model's P_cons.
    clv_val: float | None = None
    closing_p: float | None = None
    if closing_odds is not None:
        closing_p = closing_probability_from_odds(closing_odds, closing_vig_factor)
        if _taken_odds is not None:
            taken_implied_p = 1.0 / _taken_odds
            clv_val = closing_p - taken_implied_p

    # Brier / log-loss / calibration bin (model probability vs outcome, §38).
    # Calibration bin is only meaningful for settled WIN/LOSS outcomes — voids
    # and pushes have no outcome to contribute to the reliability diagram.
    brier: float | None = None
    ll: float | None = None
    cal_bin: str | None = None
    void_or_push = outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH)
    if taken_probability is not None and not void_or_push:
        brier = brier_contribution(taken_probability, outcome)
        ll = log_loss_contribution(taken_probability, outcome)
        cal_bin = calibration_bin(taken_probability)

    return SettledPrediction(
        subject_type=subject_type,
        subject_id=subject_id,
        outcome=outcome,
        settled_at=settled_at,
        stake=stake,
        gross_return=gross_ret,
        profit_loss=pl,
        taken_odds=_taken_odds,
        taken_probability=taken_probability,
        closing_odds=closing_odds,
        closing_probability=closing_p,
        clv=clv_val,
        brier_contribution=brier,
        log_loss_contribution=ll,
        calibration_bin=cal_bin,
        result_source=result_source,
        reason_codes=reason_codes or [],
    )
