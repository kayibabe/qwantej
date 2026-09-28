"""Bound ticket reconciliation with a transactional dirty-ticket queue.

One-time bootstrap queues the existing archive without changing it.
Downgrade removes only operational queue state and triggers; historical
tickets, settlements, and audit annotations are never deleted or rewritten.
Deploy the worker after this migration. Roll back the worker before downgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "f8b2d4a6c9e1"
down_revision = "e7a3c5d9f1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_settlement_queue",
        sa.Column("accumulator_id", sa.UUID(), sa.ForeignKey("accumulators.id"),
                  primary_key=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_queue_order", "ticket_settlement_queue",
                    ["queued_at", "accumulator_id"])
    op.execute("""
        CREATE FUNCTION enqueue_ticket_settlement() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'settlements' THEN
                IF NEW.subject_type = 'prediction' THEN
                    INSERT INTO ticket_settlement_queue (accumulator_id)
                    SELECT accumulator_id FROM accumulator_legs WHERE prediction_id = NEW.subject_id
                    ON CONFLICT (accumulator_id) DO UPDATE
                        SET queued_at = ticket_settlement_queue.queued_at;
                END IF;
            ELSIF TG_TABLE_NAME = 'accumulator_legs' THEN
                INSERT INTO ticket_settlement_queue (accumulator_id) VALUES (NEW.accumulator_id)
                ON CONFLICT (accumulator_id) DO UPDATE
                    SET queued_at = ticket_settlement_queue.queued_at;
            ELSIF NEW.status <> 'void' THEN
                INSERT INTO ticket_settlement_queue (accumulator_id) VALUES (NEW.id)
                ON CONFLICT (accumulator_id) DO UPDATE
                    SET queued_at = ticket_settlement_queue.queued_at;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    for name, table in (("ticket", "accumulators"), ("leg", "accumulator_legs"),
                        ("prediction", "settlements")):
        op.execute(f"""
            CREATE TRIGGER trg_ticket_queue_{name} AFTER INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION enqueue_ticket_settlement()
        """)
    op.execute("""
        INSERT INTO ticket_settlement_queue (accumulator_id)
        SELECT id FROM accumulators WHERE status <> 'void'
        ON CONFLICT (accumulator_id) DO NOTHING
    """)


def downgrade() -> None:
    for name, table in (("ticket", "accumulators"), ("leg", "accumulator_legs"),
                        ("prediction", "settlements")):
        op.execute(f"DROP TRIGGER trg_ticket_queue_{name} ON {table}")
    op.execute("DROP FUNCTION enqueue_ticket_settlement()")
    op.drop_index("ix_ticket_queue_order", table_name="ticket_settlement_queue")
    op.drop_table("ticket_settlement_queue")
