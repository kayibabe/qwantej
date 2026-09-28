"""Mutable work queue, separate from the immutable ticket/settlement archive."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, event, func, inspect
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class TicketSettlementQueue(Base):
    __tablename__ = "ticket_settlement_queue"
    __table_args__ = (Index("ix_ticket_queue_order", "queued_at", "accumulator_id"),)

    accumulator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accumulators.id"), primary_key=True
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


@event.listens_for(Base.metadata, "after_create")
def _sqlite_queue_triggers(metadata, connection, **kwargs):
    """SQLite test equivalent of the PostgreSQL migration's transactional triggers."""
    if connection.dialect.name != "sqlite":
        return
    inspector = inspect(connection)
    if not all(inspector.has_table(t) for t in (
        "ticket_settlement_queue", "accumulators", "accumulator_legs", "settlements"
    )):
        return
    for name, table, select_sql in (
        ("ticket", "accumulators", "SELECT NEW.id WHERE NEW.status <> 'void'"),
        ("leg", "accumulator_legs", "SELECT NEW.accumulator_id WHERE TRUE"),
        ("prediction", "settlements", """
            SELECT accumulator_id FROM accumulator_legs
            WHERE prediction_id = NEW.subject_id AND NEW.subject_type = 'prediction'
        """),
    ):
        connection.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS trg_ticket_queue_{name}
            AFTER INSERT ON {table} BEGIN
                INSERT INTO ticket_settlement_queue (accumulator_id) {select_sql}
                ON CONFLICT(accumulator_id) DO UPDATE SET queued_at = queued_at;
            END
        """)
