"""Read-only, evidence-first attribution of accumulator legs.

The query deliberately returns one row per ``(prediction_id, accumulator_id)``.
That preserves the distinction between a unique forecast and each ticket
occurrence that reused it, while keeping all decision-time and post-settlement
fields available for audit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Accumulator,
    AccumulatorLeg,
    Competition,
    Fixture,
    ModelRegistry,
    Prediction,
    ReliabilitySnapshot,
    Season,
    Settlement,
)
from backend.services.settlement_queries import reopened_settlement_ids
from qwantej.performance.accumulator_results import (
    derive_ticket_result,
    flat_unit_profit,
    ticket_settlement_odds,
)

EvidenceStatus = str


@dataclass(frozen=True)
class LegAttribution:
    prediction_id: uuid.UUID
    accumulator_id: uuid.UUID
    product: str
    market: str
    selection: str
    league: str | None
    fixture_id: uuid.UUID
    leg_index: int
    leg_outcome: str | None
    ticket_outcome: str
    first_losing_leg: int | None
    stored_odds: float
    quote_age_seconds: float | None
    bookmaker: str | None
    quote_id: uuid.UUID | None
    quote_timestamp: datetime | None
    closing_odds: float | None
    clv: float | None
    model_version: str | None
    calibration_version: str | None
    feature_version: str | None
    policy_version: str | None
    optimiser_version: str | None
    lrs: float | None
    mrs: float | None
    reliability_state: str | None
    paper_profit_units: float | None
    evidence_status: EvidenceStatus


def query_leg_attribution(
    session: Session,
    *,
    accumulator_id: uuid.UUID | None = None,
    since: datetime | None = None,
    limit: int = 1000,
) -> list[LegAttribution]:
    """Return durable leg-level attribution without mutating the archive."""

    superseded = select(Settlement.supersedes_id).where(Settlement.supersedes_id.is_not(None))
    stmt = (
        select(
            AccumulatorLeg,
            Accumulator,
            Prediction,
            Settlement,
            Competition.name,
            ModelRegistry.version,
            ReliabilitySnapshot,
        )
        .join(Accumulator, Accumulator.id == AccumulatorLeg.accumulator_id)
        .join(Prediction, Prediction.id == AccumulatorLeg.prediction_id)
        .join(Fixture, Fixture.id == AccumulatorLeg.fixture_id)
        .join(Season, Season.id == Fixture.season_id)
        .join(Competition, Competition.id == Season.competition_id)
        .outerjoin(ModelRegistry, ModelRegistry.id == Prediction.model_version_id)
        .outerjoin(
            ReliabilitySnapshot,
            ReliabilitySnapshot.id == Prediction.reliability_snapshot_id,
        )
        .outerjoin(
            Settlement,
            (Settlement.subject_type == "prediction")
            & (Settlement.subject_id == Prediction.id)
            & Settlement.id.not_in(superseded)
            & Settlement.id.not_in(reopened_settlement_ids()),
        )
        .order_by(Accumulator.published_at, Accumulator.id, AccumulatorLeg.leg_index)
    )
    if accumulator_id is not None:
        stmt = stmt.where(Accumulator.id == accumulator_id)
    if since is not None:
        stmt = stmt.where(Accumulator.published_at >= since)

    rows = session.execute(stmt).all()
    grouped: dict[uuid.UUID, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.Accumulator.id, []).append(row)

    result: list[LegAttribution] = []
    for ticket_rows in grouped.values():
        outcomes = [
            row.Settlement.outcome.value if row.Settlement is not None else None
            for row in ticket_rows
        ]
        ticket = ticket_rows[0].Accumulator
        ticket_result = derive_ticket_result(outcomes, ticket_voided=ticket.status.value == "void")
        first_loss = next(
            (
                row.AccumulatorLeg.leg_index
                for row in ticket_rows
                if row.Settlement is not None and row.Settlement.outcome.value == "loss"
            ),
            None,
        )
        odds = [
            (
                row.Settlement.outcome.value if row.Settlement is not None else None,
                float(row.AccumulatorLeg.decimal_odds),
            )
            for row in ticket_rows
        ]
        ticket_odds = ticket_settlement_odds(odds, ticket_result)
        paper_profit = flat_unit_profit(ticket_result, ticket_odds)
        for row in ticket_rows:
            leg = row.AccumulatorLeg
            prediction = row.Prediction
            settlement = row.Settlement
            missing = any(
                value is None or value == ""
                for value in (
                    leg.quote_id,
                    prediction.executable_odds,
                    prediction.quote_timestamp,
                    prediction.fair_market_probability,
                    prediction.model_run_id,
                    prediction.calibration_model_id,
                    prediction.feature_version,
                    prediction.calibration_version,
                    prediction.input_snapshot_ref,
                    prediction.input_snapshot_hash,
                )
            )
            if prediction.research_mode:
                status = "RESEARCH_ONLY"
            elif missing or (
                settlement is not None and settlement.closing_quote_id is None
            ):
                status = "UNAVAILABLE_PROVENANCE"
            elif settlement is None:
                status = "INSUFFICIENT_SAMPLE"
            elif ticket.paper_only:
                status = "PAPER_ONLY"
            else:
                status = "QUALIFIED"
            quote_age = None
            if leg.quote_captured_at is not None:
                captured = _utc(leg.quote_captured_at)
                published = _utc(ticket.published_at)
                quote_age = (published - captured).total_seconds()
            result.append(
                LegAttribution(
                    prediction_id=prediction.id,
                    accumulator_id=ticket.id,
                    product=ticket.product,
                    market=prediction.market,
                    selection=prediction.selection,
                    league=row.name,
                    fixture_id=leg.fixture_id,
                    leg_index=leg.leg_index,
                    leg_outcome=settlement.outcome.value if settlement is not None else None,
                    ticket_outcome=ticket_result,
                    first_losing_leg=first_loss,
                    stored_odds=float(leg.decimal_odds),
                    quote_age_seconds=quote_age,
                    bookmaker=leg.bookmaker,
                    quote_id=leg.quote_id,
                    quote_timestamp=leg.quote_captured_at,
                    closing_odds=(
                        float(settlement.closing_odds)
                        if settlement and settlement.closing_odds is not None
                        else None
                    ),
                    clv=(
                        float(settlement.clv) if settlement and settlement.clv is not None else None
                    ),
                    model_version=row.version,
                    calibration_version=prediction.calibration_version,
                    feature_version=prediction.feature_version,
                    policy_version=ticket.policy_version,
                    optimiser_version=ticket.optimiser_version,
                    lrs=float(prediction.lrs) if prediction.lrs is not None else None,
                    mrs=float(prediction.mrs) if prediction.mrs is not None else None,
                    reliability_state=(
                        row.ReliabilitySnapshot.status.value
                        if row.ReliabilitySnapshot is not None
                        else None
                    ),
                    paper_profit_units=paper_profit,
                    evidence_status=status,
                )
            )
    return result[:limit]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
