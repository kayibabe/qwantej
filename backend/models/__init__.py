"""SQLAlchemy ORM models — the institutional-memory tables from
docs/DATA_DICTIONARY.md. Alembic migrations live in backend/models/migrations/.

Every model module must be imported here so `Base.metadata` is complete —
Alembic autogenerate and `Base.metadata.create_all()` both rely on it.
"""

from backend.models.audit import AuditActor, AuditEvent, AuditEventType
from backend.models.bankroll import (
    BankrollLedgerEntry,
    LedgerEntryType,
    RiskState,
    RiskStateSnapshot,
)
from backend.models.base import Base
from backend.models.calibration import (
    CalibrationMethod,
    CalibrationModel,
    CalibrationSnapshot,
    CalibrationStatus,
)
from backend.models.experiments import (
    Experiment,
    ExperimentKind,
    ExperimentStatus,
    SelectionCandidate,
)
from backend.models.features import FeatureSnapshot
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
from backend.models.reliability import ReliabilitySnapshot, ReliabilityState
from backend.models.settlements import (
    Accumulator,
    AccumulatorLeg,
    Settlement,
    SettlementOutcome,
    TicketStatus,
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
    "FeatureSnapshot",
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
    # Phase 5 — experiment registry and immutable Value Gate decisions
    "Experiment",
    "ExperimentKind",
    "ExperimentStatus",
    "SelectionCandidate",
    # Phase 6 — point-in-time reliability matrix
    "ReliabilitySnapshot",
    "ReliabilityState",
    # Phase 7 — append-only bankroll ledger and immutable risk-state snapshots
    "BankrollLedgerEntry",
    "LedgerEntryType",
    "RiskState",
    "RiskStateSnapshot",
    # Phase 9 — settlement engine, accumulator archive
    "Accumulator",
    "AccumulatorLeg",
    "Settlement",
    "SettlementOutcome",
    "TicketStatus",
]
