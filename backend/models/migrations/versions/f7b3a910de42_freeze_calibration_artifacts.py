"""freeze versioned calibration artifact definitions

Revision ID: f7b3a910de42
Revises: c84f2d19a6b1
Create Date: 2026-09-06 13:35:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f7b3a910de42"
down_revision: str | Sequence[str] | None = "c84f2d19a6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GUARD_UPDATE_FN = """
CREATE OR REPLACE FUNCTION qwantej_guard_calibration_model_update() RETURNS trigger AS $$
BEGIN
    IF OLD.version IS DISTINCT FROM NEW.version
       OR OLD.method IS DISTINCT FROM NEW.method
       OR OLD.parent_id IS DISTINCT FROM NEW.parent_id
       OR OLD.market IS DISTINCT FROM NEW.market
       OR OLD.competition IS DISTINCT FROM NEW.competition
       OR OLD.model_family IS DISTINCT FROM NEW.model_family
       OR OLD.trained_as_of IS DISTINCT FROM NEW.trained_as_of
       OR OLD.training_window_start IS DISTINCT FROM NEW.training_window_start
       OR OLD.training_window_end IS DISTINCT FROM NEW.training_window_end
       OR OLD.sample_size IS DISTINCT FROM NEW.sample_size
       OR OLD.minimum_sample_size IS DISTINCT FROM NEW.minimum_sample_size
       OR OLD.parameters::text IS DISTINCT FROM NEW.parameters::text
       OR OLD.diagnostics::text IS DISTINCT FROM NEW.diagnostics::text
       OR OLD.artefact_hash IS DISTINCT FROM NEW.artefact_hash
       OR OLD.code_commit IS DISTINCT FROM NEW.code_commit THEN
        RAISE EXCEPTION
            'calibration model % is versioned; artifact fields are immutable', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_GUARD_UPDATE_FN)
    op.execute(
        "CREATE TRIGGER trg_calibration_models_guard_update "
        "BEFORE UPDATE ON calibration_models "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_guard_calibration_model_update();"
    )
    op.execute(
        "CREATE TRIGGER trg_calibration_models_no_delete "
        "BEFORE DELETE ON calibration_models "
        "FOR EACH ROW EXECUTE FUNCTION qwantej_forbid_mutation();"
    )
    op.execute(
        "CREATE TRIGGER trg_calibration_models_no_truncate "
        "BEFORE TRUNCATE ON calibration_models "
        "FOR EACH STATEMENT EXECUTE FUNCTION qwantej_forbid_mutation();"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_calibration_models_no_truncate ON calibration_models;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_calibration_models_no_delete ON calibration_models;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_calibration_models_guard_update ON calibration_models;"
    )
    op.execute("DROP FUNCTION IF EXISTS qwantej_guard_calibration_model_update();")
