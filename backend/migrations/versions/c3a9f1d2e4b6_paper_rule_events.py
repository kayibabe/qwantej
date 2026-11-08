"""Append-only frozen paper-rule experiment ledger."""
from alembic import op
import sqlalchemy as sa

revision = 'c3a9f1d2e4b6'
down_revision = '0200_auth_tokens'
branch_labels = None
depends_on = None


def upgrade():
    from app.models.paper_rule import PaperRuleEvent
    PaperRuleEvent.__table__.create(op.get_bind(), checkfirst=True)
    op.execute('''CREATE OR REPLACE FUNCTION protect_paper_rule_events() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'paper_rule_events is append-only'; END; $$''')
    op.execute('DROP TRIGGER IF EXISTS paper_rule_insert_only ON paper_rule_events')
    op.execute('''CREATE TRIGGER paper_rule_insert_only BEFORE UPDATE OR DELETE ON paper_rule_events
        FOR EACH ROW EXECUTE FUNCTION protect_paper_rule_events()''')
    op.execute('''CREATE OR REPLACE FUNCTION guard_paper_rule_capture() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.kind = 'decision' AND (NEW.payload->>'qualified')::boolean
           AND (NEW.payload->>'kickoff_at')::timestamptz <= clock_timestamp() THEN
          RAISE EXCEPTION 'Cannot capture qualified paper-rule pick after kickoff';
        END IF;
        RETURN NEW; END; $$''')
    op.execute('DROP TRIGGER IF EXISTS paper_rule_pre_kickoff ON paper_rule_events')
    op.execute('''CREATE TRIGGER paper_rule_pre_kickoff BEFORE INSERT ON paper_rule_events
        FOR EACH ROW EXECUTE FUNCTION guard_paper_rule_capture()''')


def downgrade():
    op.drop_table('paper_rule_events')
    op.execute('DROP FUNCTION IF EXISTS protect_paper_rule_events()')
    op.execute('DROP FUNCTION IF EXISTS guard_paper_rule_capture()')
