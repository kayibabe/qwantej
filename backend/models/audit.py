"""Audit event log (framework §12, §24, §51; docs/DATA_DICTIONARY.md).

Append-only record of material system and human actions — model promotions
and retirements, policy/config changes, manual overrides, job failures,
fixture reconciliations and other governance events. Immutable by design: an
audit trail you can edit is not an audit trail, so rows use `CreatedAtMixin`
and are never mutated.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin


class AuditActor(enum.StrEnum):
    SYSTEM = "system"  # automated jobs, schedulers, agents
    HUMAN = "human"  # a person taking a governed action


class AuditEventType(enum.StrEnum):
    """Broad category for querying. `action` carries the specific verb and
    `OTHER` is the escape hatch so an unforeseen event never goes unlogged."""

    MODEL_PROMOTED = "model_promoted"
    MODEL_RETIRED = "model_retired"
    POLICY_CHANGE = "policy_change"
    CONFIG_CHANGE = "config_change"
    OVERRIDE = "override"  # manual override of an automated decision
    DATA_REVISION = "data_revision"  # e.g. fixture reconciliation (DATA_DICTIONARY §canonical)
    JOB_FAILURE = "job_failure"
    GOVERNANCE = "governance"
    OTHER = "other"


class AuditEvent(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"

    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            name="audit_event_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    actor: Mapped[AuditActor] = mapped_column(
        Enum(
            AuditActor,
            name="audit_actor",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    actor_ref: Mapped[str | None] = mapped_column(String(120))  # username / job / agent id
    action: Mapped[str] = mapped_column(String(120), nullable=False)  # verb, e.g. "promote_model"
    summary: Mapped[str | None] = mapped_column(String(500))

    # Polymorphic target — not an FK (mirrors source_mappings.canonical_id),
    # since an audit event may reference a row in any table.
    entity_type: Mapped[str | None] = mapped_column(String(60), index=True)  # "model_registry", ...
    entity_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    payload: Mapped[dict | None] = mapped_column(JSON)  # before/after, reason codes, context

    # When the action actually happened — may precede the row-write `created_at`.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
