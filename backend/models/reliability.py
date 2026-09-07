"""Immutable point-in-time league-market reliability matrix snapshots."""

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

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.fixtures import Competition


class ReliabilityState(enum.StrEnum):
    QUALIFIED = "qualified"
    WATCH = "watch"
    RESTRICTED = "restricted"
    BLACKLISTED = "blacklisted"


class ReliabilitySnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "reliability_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "market_family", "evaluated_as_of", "policy_version",
            name="uq_reliability_snapshot_segment_cutoff_policy",
        ),
        CheckConstraint("window_start <= window_end", name="ck_reliability_window_order"),
        CheckConstraint("window_end <= evaluated_as_of", name="ck_reliability_asof_cutoff"),
        CheckConstraint("observation_count > 0", name="ck_reliability_observations"),
        CheckConstraint(
            "effective_sample_size > 0 AND effective_sample_size <= observation_count",
            name="ck_reliability_effective_sample",
        ),
        CheckConstraint(
            "shrinkage_weight >= 0 AND shrinkage_weight <= 1",
            name="ck_reliability_shrinkage",
        ),
        CheckConstraint(
            "posterior_standard_deviation >= 0",
            name="ck_reliability_uncertainty",
        ),
        CheckConstraint(
            "league_reliability >= 0 AND league_reliability <= 100 "
            "AND market_reliability >= 0 AND market_reliability <= 100 "
            "AND segment_reliability >= 0 AND segment_reliability <= 100 "
            "AND conservative_lower_bound >= 0 AND conservative_lower_bound <= 1",
            name="ck_reliability_scores",
        ),
        CheckConstraint("future_rows_excluded >= 0", name="ck_reliability_future_rows"),
    )

    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id"), nullable=False, index=True
    )
    competition_class: Mapped[str] = mapped_column(String(80), nullable=False)
    market_family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    evaluated_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_sample_size: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    shrinkage_weight: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    league_reliability: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    market_reliability: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    segment_reliability: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    posterior_standard_deviation: Mapped[float] = mapped_column(
        Numeric(9, 8), nullable=False
    )
    conservative_lower_bound: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    status: Mapped[ReliabilityState] = mapped_column(
        Enum(
            ReliabilityState,
            name="reliability_state",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    grade: Mapped[str] = mapped_column(String(12), nullable=False)
    components: Mapped[dict] = mapped_column(JSON, nullable=False)
    diagnostics: Mapped[dict] = mapped_column(JSON, nullable=False)
    future_rows_excluded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_snapshot_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)

    competition: Mapped["Competition"] = relationship()
