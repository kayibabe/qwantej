"""Build the daily accumulator from already-published Daily Pick tickets.

The source products are ``daily_safe`` (the Conservative ticket) and
``daily_balanced``.  This service never searches forecasts or odds.  It only
copies the persisted source legs into one derived, paper-only ticket after
both source tickets for the local product day exist.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import prod
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.models import Accumulator, AccumulatorLeg, TicketStatus

log = logging.getLogger(__name__)

SOURCE_PRODUCTS = ("daily_safe", "daily_balanced")
CONSERVATIVE_PRODUCT = "daily_safe"
MERGED_TICKET_PREFIX = "Accu-"
MERGED_OPTIMISER_VERSION = "daily-merge-conservative-priority-v1"
MERGED_POLICY_VERSION = "daily-merge-conservative-priority-v1"
PRODUCT_DAY_ZONE = ZoneInfo("Africa/Blantyre")
_ADVISORY_LOCK_KEY = 0x41_43_43_41_4D  # "ACCAM"


@dataclass
class DailyAccumulatorRun:
    name: str
    created: Accumulator | None = None
    existing: Accumulator | None = None
    waiting_for_sources: bool = False
    reason: str | None = None


def ensure_daily_accumulator(
    session: Session,
    *,
    now: datetime,
    build_hour_utc: int = 7,
) -> DailyAccumulatorRun:
    """Create today's derived accumulator once both source tickets exist.

    ``daily_safe`` is the Conservative source and wins whenever both source
    tickets contain the same fixture, including when their selections differ.
    The function is safe to call from every scheduler cycle.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not 0 <= build_hour_utc <= 23:
        raise ValueError("build_hour_utc must be in [0, 23]")

    product_day = now.astimezone(PRODUCT_DAY_ZONE).date()
    name = f"{MERGED_TICKET_PREFIX}{product_day.isoformat()}"
    if session.get_bind().dialect.name == "postgresql":
        # The product column is intentionally not globally unique because
        # historical product rows may legitimately repeat. Serialize this
        # derived ticket's check-and-create path instead.
        session.execute(select(func.pg_advisory_xact_lock(_ADVISORY_LOCK_KEY)))
    existing = session.scalar(select(Accumulator).where(Accumulator.product == name))
    if existing is not None:
        return DailyAccumulatorRun(name=name, existing=existing)

    local_start = datetime.combine(product_day, datetime.min.time(), tzinfo=PRODUCT_DAY_ZONE)
    utc_start = local_start.astimezone(UTC)
    utc_end = (local_start + timedelta(days=1)).astimezone(UTC)
    if now.astimezone(UTC) < utc_start + timedelta(hours=build_hour_utc):
        return DailyAccumulatorRun(name=name, reason="before_build_hour")

    source_rows = list(
        session.scalars(
            select(Accumulator)
            .where(
                Accumulator.product.in_(SOURCE_PRODUCTS),
                Accumulator.published_at >= utc_start,
                Accumulator.published_at < utc_end,
            )
            .options(selectinload(Accumulator.legs))
            .order_by(Accumulator.published_at.desc(), Accumulator.id.desc())
        )
    )
    sources: dict[str, Accumulator] = {}
    for row in source_rows:
        sources.setdefault(row.product, row)
    if not all(product in sources for product in SOURCE_PRODUCTS):
        return DailyAccumulatorRun(
            name=name,
            waiting_for_sources=True,
            reason="waiting_for_conservative_and_balanced",
        )

    # Conservative is inserted first, so setdefault implements the explicit
    # conflict rule for the same fixture.
    selected: dict[object, tuple[AccumulatorLeg, Accumulator]] = {}
    for product in (CONSERVATIVE_PRODUCT, "daily_balanced"):
        source = sources[product]
        for leg in sorted(source.legs, key=lambda item: item.leg_index):
            selected.setdefault(leg.fixture_id, (leg, source))
    if not selected:
        return DailyAccumulatorRun(name=name, reason="source_tickets_have_no_legs")

    chosen = list(selected.values())
    combined_odds = prod(float(leg.decimal_odds) for leg, _ in chosen)
    joint_probability = prod(float(leg.conservative_probability) for leg, _ in chosen)
    manifest_payload = [
        {
            "fixture_id": str(leg.fixture_id),
            "prediction_id": str(leg.prediction_id),
            "source_accumulator_id": str(source.id),
            "selection": leg.selection,
        }
        for leg, source in chosen
    ]
    manifest = hashlib.sha256(
        json.dumps(manifest_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    merged = Accumulator(
        product=name,
        optimiser_version=MERGED_OPTIMISER_VERSION,
        policy_version=MERGED_POLICY_VERSION,
        combined_odds=combined_odds,
        conservative_joint_probability=joint_probability,
        stressed_joint_probability=joint_probability * 0.95,
        objective_score=joint_probability * combined_odds,
        dependence_penalty_applied=0.0,
        published_at=now,
        stake=None,
        risk_policy_version=None,
        status=TicketStatus.PENDING,
        input_manifest_hash=manifest,
        risk_state=None,
        decision_cutoff=now,
        paper_only=True,
    )
    session.add(merged)
    session.flush()
    for index, (source_leg, source) in enumerate(chosen):
        session.add(
            AccumulatorLeg(
                accumulator_id=merged.id,
                prediction_id=source_leg.prediction_id,
                source_accumulator_id=source.id,
                leg_index=index,
                fixture_id=source_leg.fixture_id,
                league_id=source_leg.league_id,
                market_family=source_leg.market_family,
                selection=source_leg.selection,
                decimal_odds=source_leg.decimal_odds,
                conservative_probability=source_leg.conservative_probability,
                edge=source_leg.edge,
                qss=source_leg.qss,
                bookmaker=source_leg.bookmaker,
                quote_captured_at=source_leg.quote_captured_at,
            )
        )
    session.flush()
    log.info(
        "daily_accumulator: created %s from Conservative=%s Balanced=%s legs=%d",
        name, sources[CONSERVATIVE_PRODUCT].id, sources["daily_balanced"].id, len(chosen),
    )
    return DailyAccumulatorRun(name=name, created=merged)
