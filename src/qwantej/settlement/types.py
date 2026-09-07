"""Core data types for the settlement engine (framework §38)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SettlementOutcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    VOID = "void"
    PUSH = "push"


@dataclass(frozen=True)
class SettledPrediction:
    """Fully evaluated outcome for a single prediction or accumulator ticket.

    All financial fields are None when stake was not recorded (e.g. paper-only
    tracking mode).  CLV and Brier/log-loss fields require their respective
    inputs — see `clv.py` and `engine.py`.
    """

    subject_type: str           # "prediction" or "accumulator"
    subject_id: str             # UUID string of the prediction or accumulator
    outcome: SettlementOutcome
    settled_at: datetime

    # Financial (may be None in paper-tracking mode)
    stake: float | None
    gross_return: float | None
    profit_loss: float | None

    # Market evaluation
    taken_probability: float | None   # P_cons at decision time
    closing_odds: float | None
    closing_probability: float | None
    clv: float | None                 # see clv.py

    # Predictive evaluation
    brier_contribution: float | None
    log_loss_contribution: float | None
    calibration_bin: str | None       # e.g. "0.60-0.70"

    result_source: str | None
    reason_codes: list[str]

    def __post_init__(self) -> None:
        if self.subject_type not in ("prediction", "accumulator"):
            raise ValueError(
                f"subject_type must be 'prediction' or 'accumulator', got {self.subject_type!r}"
            )
        if not self.subject_id or not self.subject_id.strip():
            raise ValueError("subject_id must be a non-blank string")
        if self.settled_at.tzinfo is None or self.settled_at.utcoffset() is None:
            raise ValueError("settled_at must be timezone-aware")
        if self.stake is not None and self.stake <= 0:
            raise ValueError("stake must be positive")
        if self.taken_probability is not None and not 0 < self.taken_probability <= 1:
            raise ValueError("taken_probability must be in (0, 1]")
        if self.closing_odds is not None and self.closing_odds <= 1:
            raise ValueError("closing_odds must be > 1")
        if self.closing_probability is not None and not 0 < self.closing_probability <= 1:
            raise ValueError("closing_probability must be in (0, 1]")
        if self.brier_contribution is not None:
            if not math.isfinite(self.brier_contribution) or not 0 <= self.brier_contribution <= 1:
                raise ValueError("brier_contribution must be in [0, 1]")
        if self.log_loss_contribution is not None and not math.isfinite(self.log_loss_contribution):
            raise ValueError("log_loss_contribution must be finite")
