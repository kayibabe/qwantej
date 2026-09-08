"""Walk-forward evaluation, reliability intelligence, and settled-prediction KPIs."""

from qwantej.performance.backtest import (
    BacktestFold,
    BacktestObservation,
    WalkForwardConfig,
    WalkForwardReport,
    walk_forward_backtest,
)
from qwantej.performance.champion_challenger import (
    ChallengerEvaluation,
    ChallengerStatus,
    ModelMetrics,
    PromotionCriteria,
    evaluate_challenger,
)
from qwantej.performance.drift import (
    CalibrationDriftResult,
    ExecutionDriftResult,
    PredictionDriftResult,
    detect_calibration_drift,
    detect_execution_drift,
    detect_prediction_drift,
)
from qwantej.performance.kpi import (
    KPIReport,
    PerformanceObservation,
    compute_kpis,
    segment_kpis,
)
from qwantej.performance.reliability import (
    ReliabilityCell,
    ReliabilityComponents,
    ReliabilityEstimate,
    ReliabilityMatrix,
    ReliabilityObservation,
    ReliabilityPolicy,
    ReliabilityStatus,
    build_reliability_matrix,
)

__all__ = [
    # Phase 5-6: walk-forward backtest and reliability
    "BacktestFold",
    "BacktestObservation",
    "WalkForwardConfig",
    "WalkForwardReport",
    "walk_forward_backtest",
    "ReliabilityCell",
    "ReliabilityComponents",
    "ReliabilityEstimate",
    "ReliabilityMatrix",
    "ReliabilityObservation",
    "ReliabilityPolicy",
    "ReliabilityStatus",
    "build_reliability_matrix",
    # Phase 9: drift detection
    "CalibrationDriftResult",
    "ExecutionDriftResult",
    "PredictionDriftResult",
    "detect_calibration_drift",
    "detect_execution_drift",
    "detect_prediction_drift",
    # Phase 9: champion-challenger governance
    "ChallengerEvaluation",
    "ChallengerStatus",
    "ModelMetrics",
    "PromotionCriteria",
    "evaluate_challenger",
    # Phase 9: settled-prediction KPI aggregation
    "KPIReport",
    "PerformanceObservation",
    "compute_kpis",
    "segment_kpis",
]
