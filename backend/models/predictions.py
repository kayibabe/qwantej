"""Immutable prediction archive (framework §12-13, Appendix C; docs/DATA_DICTIONARY.md).

A published prediction is an append-only, point-in-time record: it must
reproduce *exactly* what Qwantej believed at `decision_as_of`, even after
models, features or calibrators change (framework §13). Rows are therefore
never updated — a correction is a *new* prediction, so this table uses
`CreatedAtMixin` (no `updated_at`).

Two deliberate boundaries against Appendix C's full record:

1. Post-fixture information (result, settlement status, stake/return/PL,
   closing odds, CLV, Brier/log-loss contributions) is **not** stored here.
   It lives in the separate, later `settlements` table so it can never leak
   back into the decision-time record. Appendix C is the union view across
   `predictions` + `settlements`, not a single physical table.

2. Per-model probabilities live in `model_probabilities` (a JSON map of
   model family -> probability) rather than one column per family. The set
   of model families is the whole point of the ensemble and will keep
   growing; a fixed column per family would force a migration each time one
   is added. This mirrors the reasoning in `stats_snapshots.payload`. The
   three *decision-critical* layers every downstream gate reads — ensemble,
   calibrated and conservative — remain explicit, indexed columns.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.calibration import CalibrationModel
    from backend.models.fixtures import Fixture
    from backend.models.registry import ModelRegistry, ModelRun
    from backend.models.reliability import ReliabilitySnapshot


def _probability_check(column: str) -> CheckConstraint:
    """A probability column is either NULL or within [0, 1]."""
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= 0 AND {column} <= 1)",
        name=f"ck_predictions_{column}_unit_interval",
    )


class Prediction(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "predictions"
    __table_args__ = (
        _probability_check("ensemble_probability"),
        _probability_check("calibrated_probability"),
        _probability_check("conservative_probability"),
        _probability_check("fair_market_probability"),
        ForeignKeyConstraint(
            ["model_run_id", "model_version_id"],
            ["model_runs.id", "model_runs.model_id"],
            name="fk_predictions_model_run_model",
        ),
    )

    # --- Identity & point-in-time (framework §13) ---
    # competition/season/team ids are intentionally *not* duplicated here:
    # they are reachable via the fixture and never change for a given
    # fixture, so the FK keeps the record self-contained without redundancy.
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixtures.id"), nullable=False, index=True
    )
    prediction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Only data with source timestamps <= decision_as_of may enter features.
    decision_as_of: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # --- Market / selection ---
    market: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # "1X2", "OU", ...
    selection: Mapped[str] = mapped_column(String(40), nullable=False)  # "home", "over", "X2", ...
    line: Mapped[float | None] = mapped_column(Numeric(6, 2))  # e.g. 2.5 for O/U 2.5

    # --- Probability layers ---
    # Per-model raw probabilities, e.g. {"poisson": 0.51, "dixon_coles": 0.49}.
    model_probabilities: Mapped[dict | None] = mapped_column(JSON)
    ensemble_probability: Mapped[float | None] = mapped_column(Numeric(7, 6))
    calibrated_probability: Mapped[float | None] = mapped_column(Numeric(7, 6))
    # P_cons — the conservative probability decisions are actually made on.
    conservative_probability: Mapped[float | None] = mapped_column(Numeric(7, 6))

    # --- Price & value (framework §21-22, Appendix B) ---
    bookmaker: Mapped[str | None] = mapped_column(String(80))
    executable_odds: Mapped[float | None] = mapped_column(Numeric(8, 3))
    quote_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fair_market_probability: Mapped[float | None] = mapped_column(Numeric(7, 6))
    edge_pp: Mapped[float | None] = mapped_column(Numeric(7, 4))  # percentage points; ± ok
    expected_value: Mapped[float | None] = mapped_column(Numeric(8, 5))  # may be negative
    uncertainty_measure: Mapped[float | None] = mapped_column(Numeric(7, 6))

    # --- Quality / reliability scores (0-100) & dynamic states ---
    dqs: Mapped[float | None] = mapped_column(Numeric(5, 2))
    qss: Mapped[float | None] = mapped_column(Numeric(5, 2))
    lrs: Mapped[float | None] = mapped_column(Numeric(5, 2))
    mrs: Mapped[float | None] = mapped_column(Numeric(5, 2))
    dynamic_states: Mapped[dict | None] = mapped_column(JSON)

    # --- Version spine (framework §13; see qwantej.audit.reproducibility) ---
    # Version identifiers answer "which model/policy versions" (attribution).
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_registry.id"), index=True
    )
    feature_version: Mapped[str | None] = mapped_column(String(40))
    calibration_version: Mapped[str | None] = mapped_column(String(40))
    risk_policy_version: Mapped[str | None] = mapped_column(String(40))
    optimiser_version: Mapped[str | None] = mapped_column(String(40))
    code_commit: Mapped[str | None] = mapped_column(String(64))

    # --- Execution / input lineage (framework §13, §235: replay readiness) ---
    # The run identifies the execution; the reference locates canonical inputs
    # and the hash verifies their content. Phase 5 performs the actual replay.
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    input_snapshot_ref: Mapped[str | None] = mapped_column(String(255))
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(128))

    calibration_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calibration_models.id"), index=True
    )
    reliability_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reliability_snapshots.id"), index=True
    )
    # Retrospective rows are explicitly excluded from live reliability
    # evidence. The migration default preserves the production path for old
    # and newly-created forecasts unless a research caller opts in.
    research_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Linkage & diagnostics ---
    # Polymorphic linkage to a future accumulators row (that table lands with
    # the accumulator engine); no FK yet, mirroring source_mappings.canonical_id.
    accumulator_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    # Appendix C "audit/reason codes"; taxonomy in Appendix D / DATA_DICTIONARY.md.
    reason_codes: Mapped[list | None] = mapped_column(JSON)

    fixture: Mapped["Fixture"] = relationship()
    model_version: Mapped["ModelRegistry | None"] = relationship(
        foreign_keys=[model_version_id], overlaps="model_run"
    )
    model_run: Mapped["ModelRun | None"] = relationship(
        foreign_keys=[model_run_id, model_version_id], overlaps="model_version"
    )
    calibration_model: Mapped["CalibrationModel | None"] = relationship(
        back_populates="predictions"
    )
    reliability_snapshot: Mapped["ReliabilitySnapshot | None"] = relationship()
