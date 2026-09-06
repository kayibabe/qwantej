"""Model registry and run log (framework §12, §42-44, §51; docs/MODEL_GOVERNANCE.md).

No model may drive a live prediction without a `model_registry` row: it is
the champion/challenger control point and the reproducibility anchor that
`predictions.model_version_id` points back to (framework §13). `model_runs`
records each concrete execution — training, backtest, inference or
evaluation — of a registered model, with the data snapshot, parameters and
output metrics needed to reproduce or audit it.

These are mutable lifecycle entities (a model moves development ->
challenger -> champion -> retired; a run moves running -> succeeded/failed),
so they use `TimestampMixin`, unlike the append-only point-in-time tables.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPKMixin


class ModelFamily(enum.StrEnum):
    """The complementary model families from framework §14. Extend as new
    families are added — a new value here is a code change, not a migration
    (the Postgres ENUM gains a value via a dedicated migration when needed)."""

    POISSON = "poisson"
    DIXON_COLES = "dixon_coles"
    ZINB = "zinb"
    ELO = "elo"
    BAYESIAN_HIERARCHICAL = "bayesian_hierarchical"
    MARKET = "market"
    ENSEMBLE = "ensemble"


class ModelStatus(enum.StrEnum):
    """Champion-challenger lifecycle (docs/MODEL_GOVERNANCE.md)."""

    DEVELOPMENT = "development"  # not yet eligible to run against live data
    CHALLENGER = "challenger"  # runs in shadow mode; cannot control live tickets
    CHAMPION = "champion"  # current approved production model/policy
    RETIRED = "retired"  # superseded; artefacts remain deployable for rollback


class ModelRegistry(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_registry_name_version"),
    )

    family: Mapped[ModelFamily] = mapped_column(
        Enum(
            ModelFamily,
            name="model_family",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)  # e.g. "poisson-baseline"
    version: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "1.2.0"
    status: Mapped[ModelStatus] = mapped_column(
        Enum(
            ModelStatus,
            name="model_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ModelStatus.DEVELOPMENT,
        nullable=False,
        index=True,
    )

    # Training data window this version was fitted on (point-in-time bounds).
    training_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    code_commit: Mapped[str | None] = mapped_column(String(64))  # git SHA that produced it
    artefact_hash: Mapped[str | None] = mapped_column(String(128))  # hash of serialised artefact
    artefact_uri: Mapped[str | None] = mapped_column(String(255))  # MLflow/file location

    hyperparameters: Mapped[dict | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(String(500))

    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    runs: Mapped[list["ModelRun"]] = relationship(back_populates="model")


class ModelRunKind(enum.StrEnum):
    TRAINING = "training"
    BACKTEST = "backtest"
    INFERENCE = "inference"
    EVALUATION = "evaluation"


class ModelRunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ModelRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "model_runs"

    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_registry.id"), nullable=False, index=True
    )
    kind: Mapped[ModelRunKind] = mapped_column(
        Enum(
            ModelRunKind,
            name="model_run_kind",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[ModelRunStatus] = mapped_column(
        Enum(
            ModelRunStatus,
            name="model_run_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ModelRunStatus.RUNNING,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Point-in-time anchor: the data cutoff this run trained/scored against.
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    data_snapshot_ref: Mapped[str | None] = mapped_column(String(128))  # id/hash of data snapshot

    code_commit: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)  # brier, log-loss, ROI, CLV, ...
    log_uri: Mapped[str | None] = mapped_column(String(255))

    model: Mapped[ModelRegistry] = relationship(back_populates="runs")
