"""Declarative base and shared mixins for all ORM models.

Framework §11-12: timestamps are stored in UTC, and every point-in-time
record must be able to say when it was true, not just when it was written.
`TimestampMixin` covers row-management timestamps (`created_at`/
`updated_at`); point-in-time *decision* timestamps (`as_of_timestamp`,
`decision_as_of`, `captured_at`, ...) are modelled explicitly per table
because they carry domain meaning, not just bookkeeping.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UUIDPKMixin:
    """Surrogate UUID primary key. Canonical IDs (fixture_id, team_id, ...)
    are UUIDs rather than provider-specific identifiers — see
    docs/DATA_DICTIONARY.md's canonical-entity rule."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """For mutable entities (fixtures, teams, competitions, ...)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CreatedAtMixin:
    """For append-only/immutable point-in-time records (odds quotes, stats
    snapshots, ...). No `updated_at` — these rows are never mutated;
    a correction is a new row, per the point-in-time integrity rule in
    docs/DATA_DICTIONARY.md."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
