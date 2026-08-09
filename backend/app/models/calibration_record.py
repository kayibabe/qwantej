from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalibrationRecord(Base):
    """
    Persisted isotonic regression calibrator for one market.

    Fit by calibration_service.run_calibration() on settled ForecastSnapshot rows.
    Applied at prediction time in ensemble_service.py to produce calibrated_prob.

    Serialisation: calibration_knots_json = {"x": [...], "y": [...]} from
    scipy.optimize.isotonic_regression. Reconstruct via numpy.interp at predict time.
    Only one row per (market, model_version) should have is_active=True at a time.
    """
    __tablename__ = "calibration_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    market: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1.0.0")

    n_samples: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_brier: Mapped[float] = mapped_column(Float, nullable=False)
    calibrated_brier: Mapped[float] = mapped_column(Float, nullable=False)
    # raw_brier - calibrated_brier; positive = calibration reduced error
    brier_improvement: Mapped[float] = mapped_column(Float, nullable=False)

    # JSON: {"x": [sorted ensemble_probs], "y": [isotonic-fitted outcomes]}
    calibration_knots_json: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
