"""Settlement engine (framework §38, §42).

Public API::

    from qwantej.settlement import (
        SettlementOutcome,
        SettledPrediction,
        settle,
        clv_probability,
        clv_log_odds,
        calibration_bin,
        brier_contribution,
        log_loss_contribution,
    )
"""

from qwantej.settlement.clv import calibration_bin, clv_log_odds, clv_probability
from qwantej.settlement.engine import brier_contribution, log_loss_contribution, settle
from qwantej.settlement.types import SettledPrediction, SettlementOutcome

__all__ = [
    "SettledPrediction",
    "SettlementOutcome",
    "settle",
    "clv_probability",
    "clv_log_odds",
    "calibration_bin",
    "brier_contribution",
    "log_loss_contribution",
]
