"""Versioned calibrator registry and immutable monitoring snapshots (Phase 4)."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.predictions import Prediction


class CalibrationMethod(enum.StrEnum):
    PLATT = "platt"
    ISOTONIC = "isotonic"


class CalibrationStatus(enum.StrEnum):
    DEVELOPMENT = "development"
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    RETIRED = "retired"


class CalibrationModel(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "calibration_models"
    __table_args__ = (
        UniqueConstraint("version", name="uq_calibration_models_version"),
        CheckConstraint("sample_size > 0", name="ck_calibration_models_sample_size_positive"),
        CheckConstraint(
            "minimum_sample_size >= 2",
            name="ck_calibration_models_minimum_sample_size",
        ),
        CheckConstraint(
            "sample_size >= minimum_sample_size",
            name="ck_calibration_models_sample_meets_minimum",
        ),
        CheckConstraint(
            "training_window_start <= training_window_end",
            name="ck_calibration_models_training_window_order",
        ),
        CheckConstraint(
            "training_window_end <= trained_as_of",
            name="ck_calibration_models_point_in_time",
        ),
    )

    version: Mapped[str] = mapped_column(String(80), nullable=False)
    method: Mapped[CalibrationMethod] = mapped_column(
        Enum(
            CalibrationMethod,
            name="calibration_method",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[CalibrationStatus] = mapped_column(
        Enum(
            CalibrationStatus,
            name="calibration_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=CalibrationStatus.DEVELOPMENT,
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calibration_models.id"))

    # Nullable dimensions encode the fallback hierarchy; all-null is global.
    market: Mapped[str | None] = mapped_column(String(40), index=True)
    competition: Mapped[str | None] = mapped_column(String(120), index=True)
    model_family: Mapped[str | None] = mapped_column(String(40), index=True)

    trained_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    diagnostics: Mapped[dict | None] = mapped_column(JSON)
    artefact_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parent: Mapped["CalibrationModel | None"] = relationship(remote_side="CalibrationModel.id")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="calibration_model")


def _unit_check(column: str) -> CheckConstraint:
    short_name = {
        "brier_score": "brier",
        "expected_calibration_error": "ece",
    }[column]
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= 0 AND {column} <= 1)",
        name=f"ck_cal_snap_{short_name}_unit",
    )


class CalibrationSnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    """Append-only out-of-sample calibration monitoring observation."""

    __tablename__ = "calibration_snapshots"
    __table_args__ = (
        CheckConstraint("sample_size > 0", name="ck_cal_snap_sample_positive"),
        CheckConstraint(
            "window_start <= window_end", name="ck_cal_snap_window_order"
        ),
        CheckConstraint(
            "window_end <= evaluated_as_of", name="ck_cal_snap_point_in_time"
        ),
        _unit_check("brier_score"),
        _unit_check("expected_calibration_error"),
    )

    calibration_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calibration_models.id"), nullable=False, index=True
    )
    evaluated_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    brier_score: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    log_loss: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    expected_calibration_error: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    calibration_intercept: Mapped[float | None] = mapped_column(Numeric(12, 8))
    calibration_slope: Mapped[float | None] = mapped_column(Numeric(12, 8))
    brier_skill_score: Mapped[float | None] = mapped_column(Numeric(12, 8))
    reliability_curve: Mapped[list] = mapped_column(JSON, nullable=False)

    calibration_model: Mapped[CalibrationModel] = relationship()
