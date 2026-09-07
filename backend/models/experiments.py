"""Phase 5 experiment registry and immutable Value Gate decisions."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
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


class ExperimentStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExperimentKind(enum.StrEnum):
    WALK_FORWARD_BACKTEST = "walk_forward_backtest"


class Experiment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_experiments_name_version"),
        CheckConstraint(
            "training_window_start <= training_window_end",
            name="ck_experiments_training_window_order",
        ),
        CheckConstraint(
            "test_window_start <= test_window_end",
            name="ck_experiments_test_window_order",
        ),
        CheckConstraint(
            "training_window_end <= test_window_start",
            name="ck_experiments_walk_forward_order",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_experiments_finish_order",
        ),
        CheckConstraint("sample_size IS NULL OR sample_size >= 0", name="ck_experiments_sample"),
        CheckConstraint(
            "leakage_rows_rejected >= 0", name="ck_experiments_leakage_rows"
        ),
        CheckConstraint(
            "status = 'running' OR finished_at IS NOT NULL",
            name="ck_experiments_completed_finished",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR "
            "(sample_size IS NOT NULL AND metrics IS NOT NULL AND result_hash IS NOT NULL)",
            name="ck_experiments_succeeded_result",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[ExperimentKind] = mapped_column(
        Enum(
            ExperimentKind,
            name="experiment_kind",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(
            ExperimentStatus,
            name="experiment_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ExperimentStatus.RUNNING,
        nullable=False,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    calibration_version: Mapped[str] = mapped_column(String(80), nullable=False)
    value_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    conservative_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    data_snapshot_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    baseline: Mapped[str] = mapped_column(String(80), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    leakage_rows_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(128))


class SelectionCandidate(UUIDPKMixin, CreatedAtMixin, Base):
    """Append-only explanation of one Value Gate evaluation."""

    __tablename__ = "selection_candidates"
    __table_args__ = (
        CheckConstraint("edge IS NULL OR (edge >= -1 AND edge <= 1)", name="ck_candidates_edge"),
    )

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("predictions.id"), nullable=False, index=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    edge: Mapped[float | None] = mapped_column(Numeric(9, 8))
    expected_value: Mapped[float | None] = mapped_column(Numeric(12, 8))
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    gate_inputs: Mapped[dict] = mapped_column(JSON, nullable=False)

    prediction: Mapped["Prediction"] = relationship()
