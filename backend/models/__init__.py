"""SQLAlchemy ORM models — the institutional-memory tables from
docs/DATA_DICTIONARY.md. Alembic migrations live in backend/models/migrations/.

Every model module must be imported here so `Base.metadata` is complete —
Alembic autogenerate and `Base.metadata.create_all()` both rely on it.
"""

from backend.models.audit import AuditActor, AuditEvent, AuditEventType
from backend.models.base import Base
from backend.models.calibration import (
    CalibrationMethod,
    CalibrationModel,
    CalibrationSnapshot,
    CalibrationStatus,
)
from backend.models.fixtures import Competition, Fixture, FixtureStatus, Season, Team
from backend.models.odds import OddsQuote
from backend.models.predictions import Prediction
from backend.models.providers import EntityType, Provider, SourceMapping
from backend.models.registry import (
    ModelFamily,
    ModelRegistry,
    ModelRun,
    ModelRunKind,
    ModelRunStatus,
    ModelStatus,
)
from backend.models.stats import StatsSnapshot, StatsSubjectType

__all__ = [
    "Base",
    "Competition",
    "Season",
    "Team",
    "Fixture",
    "FixtureStatus",
    "Provider",
    "SourceMapping",
    "EntityType",
    "OddsQuote",
    "StatsSnapshot",
    "StatsSubjectType",
    # Phase 2 — model registry, prediction archive, audit trail
    "ModelRegistry",
    "ModelFamily",
    "ModelStatus",
    "ModelRun",
    "ModelRunKind",
    "ModelRunStatus",
    "Prediction",
    "AuditEvent",
    "AuditActor",
    "AuditEventType",
    # Phase 4 — calibration registry and monitoring archive
    "CalibrationModel",
    "CalibrationMethod",
    "CalibrationStatus",
    "CalibrationSnapshot",
]
