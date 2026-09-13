"""Settlement, accumulator ticket and accumulator-leg ORM models (framework §38, §42).

Conceptual split:
- `Accumulator` / `AccumulatorLeg` — the published ticket record (what was
  selected and at what price).  Append-only: once published a ticket is
  frozen so the settlement can be unambiguous.
- `Settlement` — post-fixture outcome for one prediction or one accumulator
  leg.  Also append-only; a correction creates a new row (with reason code)
  rather than mutating the old one.

Closing odds are stored in `Settlement` (never in `predictions`) so they
cannot leak back into decision-time feature sets (framework §10, §14).
CLV and Brier/log-loss contributions are computed from settled data and
stored here alongside the raw outcome.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from backend.models.fixtures import Fixture


class TicketStatus(enum.StrEnum):
    PENDING = "pending"
    LOCKED = "locked"
    SETTLED = "settled"
    VOID = "void"


class SettlementOutcome(enum.StrEnum):
    WIN = "win"
    LOSS = "loss"
    VOID = "void"
    PUSH = "push"


class Accumulator(UUIDPKMixin, CreatedAtMixin, Base):
    """Published accumulator ticket (append-only; update via triggers)."""

    __tablename__ = "accumulators"
    __table_args__ = (
        CheckConstraint("combined_odds > 1", name="ck_accumulators_odds_gt_1"),
        CheckConstraint(
            "conservative_joint_probability > 0 AND conservative_joint_probability <= 1",
            name="ck_accumulators_joint_p_unit",
        ),
        CheckConstraint(
            "stressed_joint_probability > 0 AND stressed_joint_probability <= 1",
            name="ck_accumulators_stressed_p_unit",
        ),
        CheckConstraint("stake IS NULL OR stake > 0", name="ck_accumulators_stake_pos"),
    )

    product: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    optimiser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    combined_odds: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    conservative_joint_probability: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    stressed_joint_probability: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    objective_score: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False)
    dependence_penalty_applied: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Staking fields — filled by risk engine before locking.
    stake: Mapped[float | None] = mapped_column(Numeric(18, 4))
    risk_policy_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            name="ticket_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=TicketStatus.PENDING,
        index=True,
    )
    # Phase 8 orchestration columns
    input_manifest_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    risk_state: Mapped[str | None] = mapped_column(String(20))
    decision_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paper_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    legs: Mapped[list["AccumulatorLeg"]] = relationship(back_populates="accumulator")


class AccumulatorLeg(UUIDPKMixin, CreatedAtMixin, Base):
    """One selection within a published accumulator ticket."""

    __tablename__ = "accumulator_legs"
    __table_args__ = (
        UniqueConstraint(
            "accumulator_id", "prediction_id", name="uq_acca_leg_accumulator_prediction"
        ),
        UniqueConstraint("prediction_id", name="uq_acca_leg_prediction"),
        CheckConstraint("decimal_odds > 1", name="ck_acca_leg_odds_gt_1"),
        CheckConstraint(
            "conservative_probability > 0 AND conservative_probability <= 1",
            name="ck_acca_leg_prob_unit",
        ),
        CheckConstraint(
            "leg_index >= 0", name="ck_acca_leg_index_nonneg"
        ),
    )

    accumulator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accumulators.id"), nullable=False, index=True
    )
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("predictions.id"), nullable=False, index=True
    )
    leg_index: Mapped[int] = mapped_column(nullable=False)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixtures.id"), nullable=False, index=True
    )
    league_id: Mapped[str] = mapped_column(String(40), nullable=False)
    market_family: Mapped[str] = mapped_column(String(40), nullable=False)
    selection: Mapped[str] = mapped_column(String(80), nullable=False)
    decimal_odds: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    conservative_probability: Mapped[float] = mapped_column(Numeric(9, 8), nullable=False)
    edge: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    qss: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    # The bookmaker whose exact quote was used for this paper ticket.
    # Nullable so historical rows without attribution remain readable.
    bookmaker: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # The exact moment the price was observed; written at leg creation time.
    # Nullable so existing rows without this value remain valid.
    quote_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    accumulator: Mapped["Accumulator"] = relationship(back_populates="legs")
    fixture: Mapped["Fixture"] = relationship()

    # --- Display helpers (read from eagerly-loaded fixture) ---

    @property
    def home_team(self) -> str | None:
        if self.fixture and self.fixture.home_team:
            return self.fixture.home_team.name
        return None

    @property
    def away_team(self) -> str | None:
        if self.fixture and self.fixture.away_team:
            return self.fixture.away_team.name
        return None

    @property
    def kickoff_utc(self) -> datetime | None:
        return self.fixture.kickoff_utc if self.fixture else None

    @property
    def competition_name(self) -> str | None:
        if self.fixture and self.fixture.competition:
            return self.fixture.competition.name
        return None


class Settlement(UUIDPKMixin, CreatedAtMixin, Base):
    """Post-fixture outcome record for a prediction or accumulator ticket.

    Append-only: a correction is a new row with reason_codes indicating it
    supersedes a prior settlement id.  Never delete or UPDATE settlement rows
    (framework §3 "Never delete historical forecasts, settled bets").

    `subject_type` is a discriminator: "prediction" or "accumulator".
    Keeping outcome for both in one table simplifies aggregate queries
    (ROI, Brier score across all settled decisions) while the FK-like
    `subject_id` references the relevant table through application logic.
    """

    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint(
            "subject_type", "subject_id", "settled_at",
            name="uq_settlements_subject_settled_at",
        ),
        CheckConstraint(
            "subject_type IN ('prediction', 'accumulator')",
            name="ck_settlements_subject_type",
        ),
        CheckConstraint(
            "taken_odds IS NULL OR taken_odds > 1",
            name="ck_settlements_taken_odds_gt_1",
        ),
        CheckConstraint(
            "closing_odds IS NULL OR closing_odds > 1",
            name="ck_settlements_closing_odds_gt_1",
        ),
        CheckConstraint(
            "brier_contribution IS NULL OR "
            "(brier_contribution >= 0 AND brier_contribution <= 1)",
            name="ck_settlements_brier_unit",
        ),
        CheckConstraint(
            "stake IS NULL OR stake > 0",
            name="ck_settlements_stake_pos",
        ),
    )

    subject_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    outcome: Mapped[SettlementOutcome] = mapped_column(
        Enum(
            SettlementOutcome,
            name="settlement_outcome",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        index=True,
    )
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    result_source: Mapped[str | None] = mapped_column(String(80))

    # Financial
    stake: Mapped[float | None] = mapped_column(Numeric(18, 4))
    gross_return: Mapped[float | None] = mapped_column(Numeric(18, 4))
    profit_loss: Mapped[float | None] = mapped_column(Numeric(18, 4))

    # Market evaluation
    taken_odds: Mapped[float | None] = mapped_column(Numeric(8, 3))
    closing_odds: Mapped[float | None] = mapped_column(Numeric(8, 3))
    closing_probability: Mapped[float | None] = mapped_column(Numeric(9, 8))
    clv: Mapped[float | None] = mapped_column(Numeric(9, 6))

    # Predictive evaluation
    taken_probability: Mapped[float | None] = mapped_column(Numeric(9, 8))
    brier_contribution: Mapped[float | None] = mapped_column(Numeric(9, 8))
    log_loss_contribution: Mapped[float | None] = mapped_column(Numeric(12, 8))

    # Calibration bin (e.g. "0.60-0.70") for reliability diagram aggregation.
    calibration_bin: Mapped[str | None] = mapped_column(String(20))

    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # UUID of a prior Settlement this row supersedes (corrections only).
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("settlements.id"), index=True
    )
    # The exact OddsQuote row used for CLV — stored for full reproducibility
    # (framework §13).  NULL when no closing quote was available.
    closing_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("odds_quotes.id", name="fk_settlements_closing_quote"), index=True
    )

