"""GET /audit — paginated, filterable audit event log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.models.audit import AuditEvent, AuditEventType
from backend.schemas.audit import AuditEventOut, AuditEventPage

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[RequireApiKey])

_MAX_LIMIT = 200


@router.get("", response_model=AuditEventPage)
def list_audit_events(
    db: DbDep,
    event_type: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Return a page of audit events, most-recent first.

    Optional filters:
    - ``event_type`` — one of ``model_promoted``, ``model_retired``,
      ``policy_change``, ``config_change``, ``override``, ``data_revision``,
      ``job_failure``, ``governance``, ``other``
    - ``entity_type`` — e.g. ``model_registry``, ``prediction``
    - ``entity_id`` — UUID of the specific entity
    - ``since`` / ``until`` — restrict by ``occurred_at`` (ISO-8601)
    """
    stmt = select(AuditEvent)

    if event_type is not None:
        try:
            stmt = stmt.where(AuditEvent.event_type == AuditEventType(event_type))
        except ValueError:
            valid = [t.value for t in AuditEventType]
            raise HTTPException(
                status_code=422,
                detail=f"event_type must be one of {valid}",
            ) from None

    if entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if since is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= until)

    total: int = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return AuditEventPage(
        items=[AuditEventOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
