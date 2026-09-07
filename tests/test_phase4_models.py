"""Persistence tests for the Phase 4 calibrator and monitoring records."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    Base,
    CalibrationMethod,
    CalibrationModel,
    CalibrationSnapshot,
    CalibrationStatus,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _calibrator(now: datetime) -> CalibrationModel:
    return CalibrationModel(
        version="cal-global-v1", method=CalibrationMethod.PLATT,
        status=CalibrationStatus.CHALLENGER, trained_as_of=now,
        training_window_start=now - timedelta(days=90),
        training_window_end=now - timedelta(days=1), sample_size=500,
        minimum_sample_size=30, parameters={"intercept": 0.0, "slope": 1.0},
        diagnostics={"brier_score": 0.2}, artefact_hash="sha256:abc",
        code_commit="abc123",
    )


def test_calibrator_and_monitoring_snapshot_round_trip(session: Session) -> None:
    now = datetime.now(UTC)
    calibrator = _calibrator(now)
    snapshot = CalibrationSnapshot(
        calibration_model=calibrator, evaluated_as_of=now,
        window_start=now - timedelta(days=30), window_end=now - timedelta(days=1),
        sample_size=100, brier_score=0.19, log_loss=0.57,
        expected_calibration_error=0.03, calibration_intercept=0.01,
        calibration_slope=0.98, brier_skill_score=0.04,
        reliability_curve=[{"lower": 0.0, "upper": 0.1, "count": 10}],
    )
    session.add(snapshot)
    session.commit()
    session.expire_all()
    stored = session.query(CalibrationSnapshot).one()
    assert stored.calibration_model.version == "cal-global-v1"
    assert float(stored.brier_score) == pytest.approx(0.19)
    assert stored.reliability_curve[0]["count"] == 10


def test_calibrator_rejects_training_data_after_cutoff(session: Session) -> None:
    now = datetime.now(UTC)
    calibrator = _calibrator(now)
    calibrator.training_window_end = now + timedelta(seconds=1)
    session.add(calibrator)
    with pytest.raises(IntegrityError):
        session.commit()


def test_snapshot_rejects_invalid_ece(session: Session) -> None:
    now = datetime.now(UTC)
    snapshot = CalibrationSnapshot(
        calibration_model=_calibrator(now), evaluated_as_of=now,
        window_start=now - timedelta(days=30), window_end=now - timedelta(days=1),
        sample_size=100, brier_score=0.19, log_loss=0.57,
        expected_calibration_error=1.1, reliability_curve=[],
    )
    session.add(snapshot)
    with pytest.raises(IntegrityError):
        session.commit()
