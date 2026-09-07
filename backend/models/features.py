"""Immutable point-in-time model-ready feature snapshots (framework section 13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.fixtures import Fixture


class FeatureSnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    """A frozen feature vector and the exact source observations behind it."""

    __tablename__ = "feature_snapshots"
    __table_args__ = (
        CheckConstraint("feature_version <> ''", name="ck_feature_snapshot_version_nonblank"),
        CheckConstraint(
            "imputation_policy_version <> ''",
            name="ck_feature_snapshot_imputation_policy_nonblank",
        ),
        CheckConstraint("code_commit <> ''", name="ck_feature_snapshot_commit_nonblank"),
        CheckConstraint(
            "length(source_data_hash) = 71 AND source_data_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_source_hash",
        ),
        CheckConstraint(
            "length(feature_hash) = 71 AND feature_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_feature_hash",
        ),
        CheckConstraint(
            "length(snapshot_hash) = 71 AND snapshot_hash LIKE 'sha256:%'",
            name="ck_feature_snapshot_hash",
        ),
        UniqueConstraint(
            "fixture_id",
            "feature_version",
            "as_of_timestamp",
            "snapshot_hash",
            name="uq_feature_snapshot_identity",
        ),
    )

    fixture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixtures.id"), nullable=False, index=True
    )
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    features: Mapped[dict] = mapped_column(JSON, nullable=False)

    # UUID strings are stored in deterministic order. Source rows are themselves
    # append-only, so these references remain replayable without copying raw data.
    stats_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    odds_quote_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    imputation_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)

    source_data_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    code_commit: Mapped[str] = mapped_column(String(64), nullable=False)

    fixture: Mapped[Fixture] = relationship()

    @property
    def snapshot_ref(self) -> str:
        """Stable reference used by model runs and prediction lineage."""

        return f"feature-snapshot:{self.id}"
