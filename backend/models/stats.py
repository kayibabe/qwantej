"""Point-in-time team/fixture statistics (framework §9, §11-12).

Phase 1 stores stat payloads as JSON rather than one column per metric —
the data-family list in the framework (results, xG, form, home/away
splits, shots, strength, squad availability, schedule, environment) is
wide and will keep growing. `feature_snapshots` (added when Phase 3's
feature engineering lands) is where a *stable, versioned* feature schema
belongs; this table is the raw point-in-time record underneath it.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.fixtures import Fixture, Team


class StatsSubjectType(enum.StrEnum):
    TEAM = "team"
    FIXTURE = "fixture"


class StatsSnapshot(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "stats_snapshots"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'team' AND team_id IS NOT NULL AND fixture_id IS NULL) OR "
            "(subject_type = 'fixture' AND fixture_id IS NOT NULL AND team_id IS NULL)",
            name="ck_stats_snapshot_subject",
        ),
    )

    subject_type: Mapped[StatsSubjectType] = mapped_column(
        Enum(
            StatsSubjectType,
            name="stats_subject_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), index=True)
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixtures.id"), index=True)

    # The moment these stats were true/knowable — not when the row was
    # written. This is the field point-in-time backtests key off.
    as_of_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)

    team: Mapped["Team | None"] = relationship()
    fixture: Mapped["Fixture | None"] = relationship()
