from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_optional
from app.core.database import get_db
from app.models.bet import TrackedBet
from app.models.user import User
from app.services.acca_builder import build_acca_candidates, build_accumulator

router = APIRouter(prefix="/api/accumulators", tags=["accumulators"])

ACCUMULATOR_TIERS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
_FREE_LEG_LIMIT = 2


def _gate_legs(legs: list[dict], is_pro: bool) -> list[dict]:
    if is_pro:
        return legs
    return [
        {**leg, "locked": i >= _FREE_LEG_LIMIT}
        for i, leg in enumerate(legs)
    ]


@router.get("")
async def get_accumulators(
    date_str: Optional[str] = Query(None, alias="date"),
    target_odds: Optional[float] = Query(None, description="Single tier. If omitted, returns all 6 tiers."),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    target_date = date.fromisoformat(date_str) if date_str else date.today()

    is_pro = (
        current_user is not None
        and current_user.tier in ("pro", "elite")
        and current_user.subscription_status == "active"
    )

    # Prefer the scheduler-tracked ticket (has result_status) over a live rebuild.
    tracked_stmt = (
        select(TrackedBet)
        .where(TrackedBet.source_rule_key == "system_acca")
        .where(TrackedBet.user_id.is_(None))
        .where(TrackedBet.event_date == target_date)
        .order_by(TrackedBet.odds.desc())
        .limit(1)
    )
    tracked = (await db.execute(tracked_stmt)).scalar_one_or_none()

    if tracked:
        notes_raw = tracked.notes or "{}"
        notes = json.loads(notes_raw) if isinstance(notes_raw, str) else notes_raw
        legs = notes.get("legs", [])
        return {
            "date": str(target_date),
            "is_tracked": True,
            "result_status": tracked.result_status,
            "combined_odds": tracked.odds,
            "legs": _gate_legs(legs, is_pro),
            "leg_count": len(legs),
            "expected_win_probability": notes.get("expected_win_probability"),
            "total_qualifying": len(legs),
        }

    # No tracked ticket — build live from current signals.
    candidates = await build_acca_candidates(db, target_date)

    if target_odds is not None:
        acc = build_accumulator(candidates, target_odds)
        acc["legs"] = _gate_legs(acc["legs"], is_pro)
        acc["date"] = str(target_date)
        acc["is_tracked"] = False
        return acc

    tiers: dict[str, dict] = {}
    for t in ACCUMULATOR_TIERS:
        acc = build_accumulator(candidates, t)
        acc["legs"] = _gate_legs(acc["legs"], is_pro)
        tiers[str(t)] = acc

    return {
        "date": str(target_date),
        "is_tracked": False,
        "tiers": tiers,
        "total_qualifying": len(candidates),
    }
