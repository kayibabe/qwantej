"""Shared reporting exclusions for append-only ticket reopening annotations."""

from sqlalchemy import select

from backend.models import AuditEvent

TICKET_REOPENED = "ticket_reopened"


def reopened_settlement_ids():
    """Settlements withdrawn by an audited reopen; retained as historical rows."""
    return select(AuditEvent.entity_id).where(
        AuditEvent.entity_type == "settlement",
        AuditEvent.action == TICKET_REOPENED,
        AuditEvent.entity_id.is_not(None),
    )
