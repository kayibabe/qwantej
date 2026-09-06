"""Fail-closed prediction publication (framework §12-13, Appendix C).

A forecast that is generated but never archived did not happen — it cannot be
scored and it breaks the calibration feedback loop (DEVELOPMENT.md §4). But the
inverse risk is just as real: publishing an *incomplete* record, one that cannot
be reproduced because its minimum decision fields or its frozen lineage are
missing. This service refuses to publish unless the complete minimum record and
a verifiable, existing lineage are present — it fails closed and writes nothing
rather than archiving a record that cannot be replayed or scored later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import (
    CalibrationModel,
    ModelRegistry,
    ModelRun,
    Prediction,
    ReliabilitySnapshot,
)


class PredictionPublicationError(ValueError):
    """Raised when a prediction cannot be published; nothing is written."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("cannot publish prediction: " + "; ".join(problems))


# The price block is all-or-nothing: a value assessment is coherent only with
# every field present, so a partial price is rejected rather than half-stored.
_PRICE_FIELDS = (
    "bookmaker",
    "executable_odds",
    "quote_timestamp",
    "fair_market_probability",
    "edge_pp",
    "expected_value",
)


@dataclass(frozen=True)
class PredictionLineage:
    """The frozen reproducibility spine every published prediction must carry."""

    model_version_id: uuid.UUID
    model_run_id: uuid.UUID
    calibration_model_id: uuid.UUID
    feature_version: str
    calibration_version: str
    code_commit: str
    input_snapshot_ref: str
    input_snapshot_hash: str
    reliability_snapshot_id: uuid.UUID | None = None
    risk_policy_version: str | None = None


@dataclass(frozen=True)
class MinimumPredictionRecord:
    """Decision-time minimum record (Appendix C, excluding post-fixture data)."""

    fixture_id: uuid.UUID
    prediction_timestamp: datetime
    decision_as_of: datetime
    market: str
    selection: str
    model_probabilities: dict
    ensemble_probability: float
    calibrated_probability: float
    conservative_probability: float
    dqs: float
    line: float | None = None
    uncertainty_measure: float | None = None
    lrs: float | None = None
    mrs: float | None = None
    qss: float | None = None
    dynamic_states: dict | None = None
    reason_codes: list | None = None
    # Optional coherent price block.
    bookmaker: str | None = None
    executable_odds: float | None = None
    quote_timestamp: datetime | None = None
    fair_market_probability: float | None = None
    edge_pp: float | None = None
    expected_value: float | None = None


def publish_prediction(
    session: Session,
    *,
    record: MinimumPredictionRecord,
    lineage: PredictionLineage,
) -> Prediction:
    """Validate and archive an immutable prediction, or fail closed."""

    problems = _record_problems(record)
    problems += _lineage_field_problems(lineage)
    # Only hit the database for existence checks once the fields are coherent.
    if not problems:
        problems += _lineage_existence_problems(session, record, lineage)
    if problems:
        raise PredictionPublicationError(problems)

    prediction = Prediction(
        fixture_id=record.fixture_id,
        prediction_timestamp=record.prediction_timestamp,
        decision_as_of=record.decision_as_of,
        market=record.market,
        selection=record.selection,
        line=record.line,
        model_probabilities=record.model_probabilities,
        ensemble_probability=record.ensemble_probability,
        calibrated_probability=record.calibrated_probability,
        conservative_probability=record.conservative_probability,
        bookmaker=record.bookmaker,
        executable_odds=record.executable_odds,
        quote_timestamp=record.quote_timestamp,
        fair_market_probability=record.fair_market_probability,
        edge_pp=record.edge_pp,
        expected_value=record.expected_value,
        uncertainty_measure=record.uncertainty_measure,
        dqs=record.dqs,
        qss=record.qss,
        lrs=record.lrs,
        mrs=record.mrs,
        dynamic_states=record.dynamic_states,
        model_version_id=lineage.model_version_id,
        model_run_id=lineage.model_run_id,
        calibration_model_id=lineage.calibration_model_id,
        reliability_snapshot_id=lineage.reliability_snapshot_id,
        feature_version=lineage.feature_version,
        calibration_version=lineage.calibration_version,
        risk_policy_version=lineage.risk_policy_version,
        code_commit=lineage.code_commit,
        input_snapshot_ref=lineage.input_snapshot_ref,
        input_snapshot_hash=lineage.input_snapshot_hash,
        reason_codes=record.reason_codes,
    )
    session.add(prediction)
    session.flush()
    return prediction


def _record_problems(record: MinimumPredictionRecord) -> list[str]:
    problems: list[str] = []
    for name, timestamp in (
        ("prediction_timestamp", record.prediction_timestamp),
        ("decision_as_of", record.decision_as_of),
    ):
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            problems.append(f"{name} must be timezone-aware")
    for name, text_value in (("market", record.market), ("selection", record.selection)):
        if not text_value or not text_value.strip():
            problems.append(f"{name} is required")
    if not record.model_probabilities:
        problems.append("model_probabilities must be a non-empty map")
    for name, probability in (
        ("ensemble_probability", record.ensemble_probability),
        ("calibrated_probability", record.calibrated_probability),
        ("conservative_probability", record.conservative_probability),
    ):
        if probability is None:
            problems.append(f"{name} is required")
        elif not 0.0 <= probability <= 1.0:
            problems.append(f"{name} must be in [0, 1]")
    if record.dqs is None or not 0.0 <= record.dqs <= 100.0:
        problems.append("dqs is required and must be in [0, 100]")

    present_price = [f for f in _PRICE_FIELDS if getattr(record, f) is not None]
    if present_price and len(present_price) != len(_PRICE_FIELDS):
        missing = [f for f in _PRICE_FIELDS if getattr(record, f) is None]
        problems.append(
            "price block is incomplete; missing " + ", ".join(missing)
        )
    if record.quote_timestamp is not None:
        if record.quote_timestamp.tzinfo is None:
            problems.append("quote_timestamp must be timezone-aware")
        elif record.quote_timestamp > record.decision_as_of:
            problems.append("quote_timestamp cannot be after decision_as_of")
    # lrs/mrs must be backed by the reliability snapshot that produced them —
    # that existence check lives in _lineage_existence_problems.
    return problems


def _lineage_field_problems(lineage: PredictionLineage) -> list[str]:
    problems: list[str] = []
    for name, value in (
        ("feature_version", lineage.feature_version),
        ("calibration_version", lineage.calibration_version),
        ("code_commit", lineage.code_commit),
        ("input_snapshot_ref", lineage.input_snapshot_ref),
        ("input_snapshot_hash", lineage.input_snapshot_hash),
    ):
        if not value or not value.strip():
            problems.append(f"lineage.{name} is required")
    return problems


def _lineage_existence_problems(
    session: Session,
    record: MinimumPredictionRecord,
    lineage: PredictionLineage,
) -> list[str]:
    problems: list[str] = []
    model = session.get(ModelRegistry, lineage.model_version_id)
    if model is None:
        problems.append("lineage.model_version_id does not exist")
    run = session.get(ModelRun, lineage.model_run_id)
    if run is None:
        problems.append("lineage.model_run_id does not exist")
    elif run.model_id != lineage.model_version_id:
        problems.append("lineage.model_run_id belongs to a different model")
    if session.get(CalibrationModel, lineage.calibration_model_id) is None:
        problems.append("lineage.calibration_model_id does not exist")
    if lineage.reliability_snapshot_id is not None:
        if session.get(ReliabilitySnapshot, lineage.reliability_snapshot_id) is None:
            problems.append("lineage.reliability_snapshot_id does not exist")
    elif record.lrs is not None or record.mrs is not None:
        problems.append(
            "lrs/mrs require a reliability_snapshot_id identifying their source"
        )
    return problems
