"""Append-only prospective sweet-spot experiment ledger."""
from alembic import op
import sqlalchemy as sa

revision = 'b208d5e9f3a2'
down_revision = 'a197c4e8d2f1'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.sweet_spot import SweetSpotEvent
    SweetSpotEvent.__table__.create(op.get_bind(), checkfirst=True)
    op.execute('''CREATE OR REPLACE FUNCTION protect_sweet_spot_events() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'sweet_spot_events is append-only'; END; $$''')
    op.execute('DROP TRIGGER IF EXISTS sweet_spot_insert_only ON sweet_spot_events')
    op.execute('''CREATE TRIGGER sweet_spot_insert_only BEFORE UPDATE OR DELETE ON sweet_spot_events
        FOR EACH ROW EXECUTE FUNCTION protect_sweet_spot_events()''')
    op.execute('''CREATE OR REPLACE FUNCTION guard_sweet_spot_capture() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.kind = 'decision' AND (NEW.payload->>'qualified')::boolean
           AND (NEW.payload->>'kickoff_at')::timestamptz <= clock_timestamp() THEN
          RAISE EXCEPTION 'Cannot capture qualified paper pick after kickoff';
        END IF;
        RETURN NEW; END; $$''')
    op.execute('DROP TRIGGER IF EXISTS sweet_spot_pre_kickoff ON sweet_spot_events')
    op.execute('''CREATE TRIGGER sweet_spot_pre_kickoff BEFORE INSERT ON sweet_spot_events
        FOR EACH ROW EXECUTE FUNCTION guard_sweet_spot_capture()''')


def downgrade():
    op.drop_table('sweet_spot_events')
    op.execute('DROP FUNCTION IF EXISTS protect_sweet_spot_events()')
    op.execute('DROP FUNCTION IF EXISTS guard_sweet_spot_capture()')
