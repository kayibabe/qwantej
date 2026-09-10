"""Time-ordered walk-forward evaluation with explicit leakage accounting (§41)."""

from __future__ import annotations

import math
import uuid as _uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np

from qwantej.calibration import (
    CalibrationMethod,
    CalibrationObservation,
    ConservativePolicy,
    calibration_report,
    fit_calibrator,
)
from qwantej.calibration.metrics import CalibrationReport
from qwantej.value import (
    ValueCandidate,
    ValueGatePolicy,
    closing_line_value,
    evaluate_value_gate,
)


@dataclass(frozen=True)
class BacktestObservation:
    observation_id: str
    decision_as_of: datetime
    feature_as_of: datetime
    outcome_observed_at: datetime | None
    model_version: str
    raw_probability: float
    outcome: int | None
    fair_market_probability: float | None
    executable_odds: float | None
    quote_timestamp: datetime | None
    closing_odds: float | None = None
    closing_quote_timestamp: datetime | None = None
    model_probabilities: tuple[float, ...] = ()
    data_quality_score: float = 100.0
    league_reliability: float | None = None
    market_reliability: float | None = None
    league_reliability_status: str | None = None
    market_reliability_status: str | None = None
    probability_change: float = 0.0
    drift_score: float = 0.0
    snapshot_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.model_version.strip():
            raise ValueError("observation_id and model_version must not be blank")
        for name, timestamp_value in (
            ("decision_as_of", self.decision_as_of),
            ("feature_as_of", self.feature_as_of),
        ):
            _aware(name, timestamp_value)
        if self.outcome_observed_at is not None:
            _aware("outcome_observed_at", self.outcome_observed_at)
        if self.quote_timestamp is not None:
            _aware("quote_timestamp", self.quote_timestamp)
        if self.closing_quote_timestamp is not None:
            _aware("closing_quote_timestamp", self.closing_quote_timestamp)
        _unit("raw_probability", self.raw_probability)
        if self.outcome is not None and self.outcome not in (0, 1):
            raise ValueError("outcome must be 0, 1 or None")
        if self.outcome is not None and self.outcome_observed_at is None:
            raise ValueError("a settled outcome requires outcome_observed_at")
        if self.fair_market_probability is not None:
            _unit("fair_market_probability", self.fair_market_probability)
        for name, odds_value in (
            ("executable_odds", self.executable_odds),
            ("closing_odds", self.closing_odds),
        ):
            if odds_value is not None and (
                not math.isfinite(odds_value) or odds_value <= 1
            ):
                raise ValueError(f"{name} must be finite decimal odds > 1")
        for probability in self.model_probabilities:
            _unit("model probability", probability)
        if not math.isfinite(self.data_quality_score) or not 0 <= self.data_quality_score <= 100:
            raise ValueError("data_quality_score must be in [0, 100]")
        for name, reliability_value in (
            ("league_reliability", self.league_reliability),
            ("market_reliability", self.market_reliability),
        ):
            if reliability_value is not None and (
                not math.isfinite(reliability_value) or not 0 <= reliability_value <= 100
            ):
                raise ValueError(f"{name} must be in [0, 100]")
        _unit("probability_change", self.probability_change)
        _unit("drift_score", self.drift_score)
        valid_reliability_states = {"qualified", "watch", "restricted", "blacklisted"}
        for name, state in (
            ("league_reliability_status", self.league_reliability_status),
            ("market_reliability_status", self.market_reliability_status),
        ):
            if state is not None and state not in valid_reliability_states:
                raise ValueError(f"{name} is not a valid reliability state")
        if self.snapshot_ref is not None:
            prefix = "feature-snapshot:"
            if not self.snapshot_ref.startswith(prefix):
                raise ValueError("snapshot_ref must start with 'feature-snapshot:'")
            try:
                _uuid.UUID(self.snapshot_ref[len(prefix):])
            except ValueError as exc:
                raise ValueError(
                    f"snapshot_ref suffix must be a valid UUID: {exc}"
                ) from exc


@dataclass(frozen=True)
class WalkForwardConfig:
    version: str
    model_version: str
    calibration_method: CalibrationMethod = CalibrationMethod.PLATT
    minimum_training_size: int = 30
    test_window_size: int = 10
    bootstrap_samples: int = 2_000
    bootstrap_seed: int = 20260906
    allow_research_reliability_exception: bool = True
    value_policy: ValueGatePolicy = ValueGatePolicy()
    conservative_policy: ConservativePolicy = ConservativePolicy()
    observation_manifest: tuple[dict[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.model_version.strip():
            raise ValueError("config and model versions must not be blank")
        if self.minimum_training_size < 2 or self.test_window_size < 1:
            raise ValueError("training size must be >= 2 and test window size >= 1")
        if self.bootstrap_samples < 0:
            raise ValueError("bootstrap_samples must be non-negative")

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["calibration_method"] = self.calibration_method.value
        value_policy = result["value_policy"]
        assert isinstance(value_policy, dict)
        quote_age = value_policy["maximum_quote_age"]
        assert hasattr(quote_age, "total_seconds")
        value_policy["maximum_quote_age_seconds"] = quote_age.total_seconds()
        del value_policy["maximum_quote_age"]
        return result


@dataclass(frozen=True)
class BacktestFold:
    training_as_of: datetime
    training_sample_size: int
    test_start: datetime
    test_end: datetime
    evaluated_rows: int
    selected_rows: int


@dataclass(frozen=True)
class WalkForwardReport:
    config: dict[str, object]
    sample_size: int
    selected_count: int
    start: datetime
    end: datetime
    folds: tuple[BacktestFold, ...]
    leakage_rows_rejected: int
    model_version_rows_rejected: int
    unsettled_or_void_rows: int
    missing_market_rows: int
    missing_closing_odds_rows: int
    raw_calibration: CalibrationReport
    calibrated_calibration: CalibrationReport
    market_calibration: CalibrationReport
    roi: float | None
    roi_confidence_interval: tuple[float, float] | None
    hit_rate: float | None
    average_odds: float | None
    break_even_hit_rate: float | None
    average_clv: float | None
    maximum_drawdown_units: float
    # True only when *every* supplied observation (including rows later rejected
    # for leakage, model mismatch, or missing market data) carries a verified
    # snapshot_ref.  This is deliberately conservative: a run is not certified
    # unless the frozen feature provenance is proven for the full input set, not
    # just the evaluated subset.  Consumers must not weaken this to
    # "all evaluated rows had snapshots" — that would allow unchecked inputs to
    # silently slip through.  The persistence layer performs an independent
    # DB-backed verification before storing this flag (see run_walk_forward.py).
    pit_certified: bool = False


@dataclass(frozen=True)
class _Evaluated:
    observation: BacktestObservation
    calibrated_probability: float
    selected: bool


def walk_forward_backtest(
    observations: Iterable[BacktestObservation], config: WalkForwardConfig
) -> WalkForwardReport:
    supplied = tuple(observations)
    if not supplied:
        raise ValueError("backtest requires observations")
    ids = [item.observation_id for item in supplied]
    if len(ids) != len(set(ids)):
        raise ValueError("observation_id values must be unique")
    pit_certified = all(item.snapshot_ref is not None for item in supplied)

    version_rejected = sum(item.model_version != config.model_version for item in supplied)
    version_rows = [item for item in supplied if item.model_version == config.model_version]
    leakage_rejected = sum(not _point_in_time_valid(item) for item in version_rows)
    point_in_time = [item for item in version_rows if _point_in_time_valid(item)]
    missing_market = sum(not _market_available(item) for item in point_in_time)
    point_in_time = sorted(
        point_in_time,
        key=lambda item: (item.decision_as_of, item.observation_id),
    )
    unsettled_or_void = sum(item.outcome is None for item in point_in_time)
    evaluation_rows = sorted(
        (
            item
            for item in point_in_time
            if item.outcome is not None and _market_available(item)
        ),
        key=lambda item: (item.decision_as_of, item.observation_id),
    )
    if len(evaluation_rows) <= config.minimum_training_size:
        raise ValueError("not enough point-in-time rows for one walk-forward test window")

    evaluated: list[_Evaluated] = []
    folds: list[BacktestFold] = []
    for start_index in range(
        config.minimum_training_size, len(evaluation_rows), config.test_window_size
    ):
        test_rows = evaluation_rows[start_index : start_index + config.test_window_size]
        training_as_of = test_rows[0].decision_as_of
        training_rows = [
            item
            for item in point_in_time
            if item.outcome is not None
            if item.outcome_observed_at is not None
            if item.decision_as_of < training_as_of
            if item.outcome_observed_at <= training_as_of
        ]
        if len(training_rows) < config.minimum_training_size:
            continue
        calibration_fit = fit_calibrator(
            (
                CalibrationObservation(
                    raw_probability=item.raw_probability,
                    outcome=_settled_outcome(item),
                    predicted_at=item.decision_as_of,
                    outcome_observed_at=_settled_at(item),
                )
                for item in training_rows
            ),
            method=config.calibration_method,
            version=f"{config.version}:{training_as_of.isoformat()}",
            trained_as_of=training_as_of,
            minimum_sample_size=config.minimum_training_size,
        )
        calibrator = calibration_fit.calibrator
        training_calibrated = [calibrator.predict(item.raw_probability) for item in training_rows]
        training_monitor = calibration_report(
            training_calibrated, [_settled_outcome(item) for item in training_rows]
        )
        selected_in_fold = 0
        before = len(evaluated)
        for item in test_rows:
            calibrated = calibrator.predict(item.raw_probability)
            conservative = config.conservative_policy.apply(
                calibrated,
                effective_sample_size=len(training_rows),
                model_probabilities=item.model_probabilities or (item.raw_probability,),
                data_quality_score=item.data_quality_score,
                calibration_error=training_monitor.expected_calibration_error,
                drift_score=item.drift_score,
            )
            gate = evaluate_value_gate(
                ValueCandidate(
                    decision_as_of=item.decision_as_of,
                    calibrator_approved=True,
                    calibrated_probability=calibrated,
                    conservative_probability=conservative.conservative_probability,
                    fair_market_probability=item.fair_market_probability,
                    executable_odds=item.executable_odds,
                    quote_timestamp=item.quote_timestamp,
                    data_quality_score=item.data_quality_score,
                    league_reliability=item.league_reliability,
                    market_reliability=item.market_reliability,
                    league_reliability_status=item.league_reliability_status,
                    market_reliability_status=item.market_reliability_status,
                    probability_change=item.probability_change,
                    model_disagreement=_model_disagreement(item.model_probabilities),
                    research_reliability_exception=(
                        config.allow_research_reliability_exception
                    ),
                ),
                config.value_policy,
            )
            selected_in_fold += int(gate.passed)
            evaluated.append(_Evaluated(item, calibrated, gate.passed))
        folds.append(
            BacktestFold(
                training_as_of=training_as_of,
                training_sample_size=len(training_rows),
                test_start=test_rows[0].decision_as_of,
                test_end=test_rows[-1].decision_as_of,
                evaluated_rows=len(evaluated) - before,
                selected_rows=selected_in_fold,
            )
        )
    if not evaluated:
        raise ValueError("no walk-forward rows had sufficient observed training history")

    outcomes = [_settled_outcome(item.observation) for item in evaluated]
    raw = [item.observation.raw_probability for item in evaluated]
    calibrated_values = [item.calibrated_probability for item in evaluated]
    market: list[float] = []
    for evaluated_item in evaluated:
        assert evaluated_item.observation.fair_market_probability is not None
        market.append(evaluated_item.observation.fair_market_probability)
    bets = [evaluated_item for evaluated_item in evaluated if evaluated_item.selected]
    profits: list[float] = []
    odds: list[float] = []
    clv_values: list[float] = []
    for evaluated_item in bets:
        observed = evaluated_item.observation
        assert observed.executable_odds is not None
        odds.append(observed.executable_odds)
        profits.append(
            observed.executable_odds - 1.0 if _settled_outcome(observed) else -1.0
        )
        if _closing_available(observed):
            assert observed.closing_odds is not None
            clv_values.append(closing_line_value(observed.executable_odds, observed.closing_odds))
    missing_closing = sum(not _closing_available(item.observation) for item in bets)
    roi = float(np.mean(profits)) if profits else None
    return WalkForwardReport(
        config=config.as_dict(),
        sample_size=len(evaluated),
        selected_count=len(bets),
        start=evaluated[0].observation.decision_as_of,
        end=evaluated[-1].observation.decision_as_of,
        folds=tuple(folds),
        leakage_rows_rejected=leakage_rejected,
        model_version_rows_rejected=version_rejected,
        unsettled_or_void_rows=unsettled_or_void,
        missing_market_rows=missing_market,
        missing_closing_odds_rows=missing_closing,
        raw_calibration=calibration_report(raw, outcomes, reference_probabilities=market),
        calibrated_calibration=calibration_report(
            calibrated_values, outcomes, reference_probabilities=market
        ),
        market_calibration=calibration_report(market, outcomes),
        roi=roi,
        roi_confidence_interval=_bootstrap_mean_interval(
            profits, config.bootstrap_samples, config.bootstrap_seed
        ),
        hit_rate=(
            float(np.mean([_settled_outcome(item.observation) for item in bets]))
            if bets
            else None
        ),
        average_odds=float(np.mean(odds)) if odds else None,
        break_even_hit_rate=float(np.mean([1.0 / value for value in odds])) if odds else None,
        average_clv=float(np.mean(clv_values)) if clv_values else None,
        maximum_drawdown_units=_maximum_drawdown(profits),
        pit_certified=pit_certified,
    )


def _point_in_time_valid(item: BacktestObservation) -> bool:
    if item.feature_as_of > item.decision_as_of:
        return False
    if item.quote_timestamp is not None and item.quote_timestamp > item.decision_as_of:
        return False
    if (
        item.outcome_observed_at is not None
        and item.outcome_observed_at <= item.decision_as_of
    ):
        return False
    return True


def _market_available(item: BacktestObservation) -> bool:
    return (
        item.fair_market_probability is not None
        and item.executable_odds is not None
        and item.quote_timestamp is not None
    )


def _closing_available(item: BacktestObservation) -> bool:
    return (
        item.closing_odds is not None
        and item.closing_quote_timestamp is not None
        and item.closing_quote_timestamp >= item.decision_as_of
    )


def _settled_outcome(item: BacktestObservation) -> int:
    assert item.outcome is not None
    return item.outcome


def _settled_at(item: BacktestObservation) -> datetime:
    assert item.outcome_observed_at is not None
    return item.outcome_observed_at


def _model_disagreement(probabilities: tuple[float, ...]) -> float:
    if len(probabilities) < 2:
        return 0.0
    return float(np.std(probabilities))


def _bootstrap_mean_interval(
    values: list[float], samples: int, seed: int
) -> tuple[float, float] | None:
    if not values or samples == 0:
        return None
    rng = np.random.default_rng(seed)
    source = np.asarray(values)
    means = np.mean(rng.choice(source, size=(samples, len(source)), replace=True), axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return float(low), float(high)


def _maximum_drawdown(profits: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for profit in profits:
        cumulative += profit
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def _aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _unit(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
