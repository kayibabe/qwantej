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

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.models import (
    CalibrationModel,
    CalibrationStatus,
    FeatureSnapshot,
    Fixture,
    ModelRegistry,
    ModelRun,
    ModelRunKind,
    ModelRunStatus,
    ModelStatus,
    Prediction,
    ReliabilitySnapshot,
)
from backend.services.features import verify_feature_snapshot


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
    risk_policy_version: str = "risk-v1"
    optimiser_version: str = "pre-optimiser-v1"


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
        optimiser_version=lineage.optimiser_version,
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
    else:
        for model_name, probability in record.model_probabilities.items():
            if not isinstance(model_name, str) or not model_name.strip():
                problems.append("model_probabilities keys must be non-blank strings")
            if not isinstance(probability, (int, float)) or not math.isfinite(probability):
                problems.append(f"model_probabilities[{model_name!r}] must be finite")
            elif not 0.0 <= probability <= 1.0:
                problems.append(f"model_probabilities[{model_name!r}] must be in [0, 1]")
    for name, probability in (
        ("ensemble_probability", record.ensemble_probability),
        ("calibrated_probability", record.calibrated_probability),
        ("conservative_probability", record.conservative_probability),
    ):
        if probability is None:
            problems.append(f"{name} is required")
        elif not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            problems.append(f"{name} must be in [0, 1]")
    if record.dqs is None or not math.isfinite(record.dqs) or not 0.0 <= record.dqs <= 100.0:
        problems.append("dqs is required and must be in [0, 100]")
    for name, score in (("qss", record.qss), ("lrs", record.lrs), ("mrs", record.mrs)):
        if score is not None and (not math.isfinite(score) or not 0.0 <= score <= 100.0):
            problems.append(f"{name} must be in [0, 100]")
    if record.uncertainty_measure is not None and (
        not math.isfinite(record.uncertainty_measure)
        or not 0.0 <= record.uncertainty_measure <= 1.0
    ):
        problems.append("uncertainty_measure must be in [0, 1]")
    if (
        record.prediction_timestamp.tzinfo is not None
        and record.decision_as_of.tzinfo is not None
        and record.prediction_timestamp < record.decision_as_of
    ):
        problems.append("prediction_timestamp cannot precede decision_as_of")

    present_price = [f for f in _PRICE_FIELDS if getattr(record, f) is not None]
    if present_price and len(present_price) != len(_PRICE_FIELDS):
        missing = [f for f in _PRICE_FIELDS if getattr(record, f) is None]
        problems.append(
            "price block is incomplete; missing " + ", ".join(missing)
        )
    elif (
        len(present_price) == len(_PRICE_FIELDS)
        and record.conservative_probability is not None
        and math.isfinite(record.conservative_probability)
    ):
        assert record.executable_odds is not None
        assert record.fair_market_probability is not None
        assert record.edge_pp is not None
        assert record.expected_value is not None
        if not math.isfinite(record.executable_odds) or record.executable_odds <= 1.0:
            problems.append("executable_odds must be finite decimal odds greater than 1")
        if (
            not math.isfinite(record.fair_market_probability)
            or not 0.0 <= record.fair_market_probability <= 1.0
        ):
            problems.append("fair_market_probability must be in [0, 1]")
        expected_edge_pp = (
            record.conservative_probability - record.fair_market_probability
        ) * 100.0
        expected_ev = record.conservative_probability * record.executable_odds - 1.0
        if not math.isfinite(record.edge_pp) or not math.isclose(
            record.edge_pp, expected_edge_pp, rel_tol=0.0, abs_tol=1e-8
        ):
            problems.append("edge_pp does not match conservative and market probabilities")
        if not math.isfinite(record.expected_value) or not math.isclose(
            record.expected_value, expected_ev, rel_tol=0.0, abs_tol=1e-8
        ):
            problems.append("expected_value does not match probability and executable odds")
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
        ("risk_policy_version", lineage.risk_policy_version),
        ("optimiser_version", lineage.optimiser_version),
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
    feature_snapshot = _get_feature_snapshot(session, lineage.input_snapshot_ref)
    if feature_snapshot is None:
        problems.append("lineage.input_snapshot_ref is not a feature snapshot")
    else:
        if feature_snapshot.fixture_id != record.fixture_id:
            problems.append("lineage feature snapshot belongs to another fixture")
        if feature_snapshot.feature_version != lineage.feature_version:
            problems.append("lineage.feature_version does not match its snapshot")
        if _as_utc(feature_snapshot.as_of_timestamp) > record.decision_as_of:
            problems.append("lineage feature snapshot is not valid at decision_as_of")
        if feature_snapshot.snapshot_hash != lineage.input_snapshot_hash:
            problems.append("lineage.input_snapshot_hash does not match its snapshot")
        elif not verify_feature_snapshot(session, feature_snapshot):
            problems.append("lineage feature snapshot failed content verification")
    model = session.get(ModelRegistry, lineage.model_version_id)
    if model is None:
        problems.append("lineage.model_version_id does not exist")
    else:
        if model.status is not ModelStatus.CHAMPION:
            problems.append("lineage.model_version_id is not the champion model")
        if model.code_commit != lineage.code_commit:
            problems.append("lineage.code_commit does not match the model version")
    run = session.get(ModelRun, lineage.model_run_id)
    if run is None:
        problems.append("lineage.model_run_id does not exist")
    elif run.model_id != lineage.model_version_id:
        problems.append("lineage.model_run_id belongs to a different model")
    else:
        if run.kind is not ModelRunKind.INFERENCE:
            problems.append("lineage.model_run_id is not an inference run")
        if run.status is not ModelRunStatus.SUCCEEDED:
            problems.append("lineage.model_run_id has not succeeded")
        if run.data_as_of is None or _as_utc(run.data_as_of) > record.decision_as_of:
            problems.append("lineage model run is not valid at decision_as_of")
        elif feature_snapshot is not None and _as_utc(run.data_as_of) != _as_utc(
            feature_snapshot.as_of_timestamp
        ):
            problems.append("lineage model run cutoff does not match the feature snapshot")
        if run.data_snapshot_ref != lineage.input_snapshot_ref:
            problems.append("lineage input snapshot does not match the model run")
        if run.code_commit != lineage.code_commit:
            problems.append("lineage.code_commit does not match the model run")
    calibrator = session.get(CalibrationModel, lineage.calibration_model_id)
    if calibrator is None:
        problems.append("lineage.calibration_model_id does not exist")
    else:
        if calibrator.status is not CalibrationStatus.CHAMPION:
            problems.append("lineage.calibration_model_id is not champion")
        if calibrator.version != lineage.calibration_version:
            problems.append("lineage.calibration_version does not match its artifact")
        if _as_utc(calibrator.trained_as_of) > record.decision_as_of:
            problems.append("lineage calibrator is not valid at decision_as_of")
    fixture = session.get(Fixture, record.fixture_id)
    if fixture is None:
        problems.append("fixture_id does not exist")
    else:
        kickoff_utc = _as_utc(fixture.kickoff_utc)
        if record.decision_as_of >= kickoff_utc:
            problems.append("decision_as_of must be before fixture kickoff")
        if record.prediction_timestamp >= kickoff_utc:
            problems.append("prediction_timestamp must be before fixture kickoff")
    if lineage.reliability_snapshot_id is not None:
        reliability = session.get(ReliabilitySnapshot, lineage.reliability_snapshot_id)
        if reliability is None:
            problems.append("lineage.reliability_snapshot_id does not exist")
        else:
            if _as_utc(reliability.evaluated_as_of) > record.decision_as_of:
                problems.append("lineage reliability is not valid at decision_as_of")
            if record.lrs is not None and not math.isclose(
                record.lrs, float(reliability.league_reliability), abs_tol=1e-6
            ):
                problems.append("lrs does not match its reliability snapshot")
            if record.mrs is not None and not math.isclose(
                record.mrs, float(reliability.market_reliability), abs_tol=1e-6
            ):
                problems.append("mrs does not match its reliability snapshot")
    elif record.lrs is not None or record.mrs is not None:
        problems.append(
            "lrs/mrs require a reliability_snapshot_id identifying their source"
        )
    return problems


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive round trips to the UTC DB convention."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _get_feature_snapshot(session: Session, reference: str) -> FeatureSnapshot | None:
    prefix = "feature-snapshot:"
    if not reference.startswith(prefix):
        return None
    try:
        snapshot_id = uuid.UUID(reference.removeprefix(prefix))
    except ValueError:
        return None
    return session.get(FeatureSnapshot, snapshot_id)
