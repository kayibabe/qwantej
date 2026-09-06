"""Provider registry and canonical-entity mapping (framework §11).

Provider-specific identifiers must never leak into modelling code — every
provider's fixture/team/competition/season is mapped into our canonical
UUIDs here, with an explicit confidence and provenance.
"""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDPKMixin


class EntityType(enum.StrEnum):
    FIXTURE = "fixture"
    TEAM = "team"
    COMPETITION = "competition"
    SEASON = "season"


class Provider(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    mappings: Mapped[list["SourceMapping"]] = relationship(back_populates="provider")


class SourceMapping(UUIDPKMixin, TimestampMixin, Base):
    """Maps one provider's external identifier for an entity onto our
    canonical UUID for that entity, with a mapping confidence in [0, 1].
    `canonical_id` is intentionally not a foreign key to any single table
    (it is polymorphic across EntityType) — application code is
    responsible for dereferencing it against the right table."""

    __tablename__ = "source_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "entity_type", "external_id", name="uq_source_mapping"
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False, index=True
    )
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType,
            name="entity_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    provider: Mapped[Provider] = relationship(back_populates="mappings")
