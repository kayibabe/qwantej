"""Closing-line-value capture.

A closing quote is only meaningful if it is strictly later than the recorded
entry quote and no later than kickoff. Anything else is not a close: it is the
same fetch, an earlier capture, or a post-kickoff value. Historical rows that
violate that invariant are cleared by :func:`invalidate_stale_clv` rather than
reported as zero CLV.

The captured value is the best price across bookmakers at the last snapshot per
book, which matches how the entry price is chosen (best tracked quote at
entry). The bookmaker and timestamp are stored so consumers can judge how stale
the close is.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, OddsSnapshot, Prediction

# Fields that together make a stored CLV value trustworthy.
CLOSING_FIELDS = (
    "closing_decimal_odds",
    "closing_implied_probability",
    "closing_odds_at",
    "closing_bookmaker",
    "clv_percentage",
)


def clv_is_valid(prediction: Prediction) -> bool:
    """True only for a genuine post-entry, pre-kickoff closing quote."""
    return bool(
        prediction.closing_decimal_odds
        and prediction.closing_odds_at
        and prediction.source_odds_at
        and prediction.closing_odds_at > prediction.source_odds_at
    )


async def capture_closing_odds(db: AsyncSession, *, limit: int = 500) -> dict:
    now = datetime.now(timezone.utc)
    later_quote_exists = exists(
        select(OddsSnapshot.id).where(
            OddsSnapshot.match_id == Match.id,
            OddsSnapshot.market == Prediction.market,
            OddsSnapshot.selection == Prediction.selection,
            OddsSnapshot.captured_at > Prediction.source_odds_at,
            OddsSnapshot.captured_at <= Match.kickoff_at,
        )
    )
    result = await db.execute(
        select(Prediction, Match)
        .join(Match, Prediction.match_id == Match.id)
        .where(
            Match.kickoff_at <= now,
            Prediction.source_decimal_odds.is_not(None),
            Prediction.source_odds_at.is_not(None),
            later_quote_exists,
            or_(
                Prediction.clv_percentage.is_(None),
                Prediction.closing_decimal_odds.is_(None),
                Prediction.closing_odds_at.is_(None),
                Prediction.closing_odds_at <= Prediction.source_odds_at,
                Prediction.closing_odds_at > Match.kickoff_at,
            ),
        )
        .limit(limit)
    )
    rows = result.all()
    captured = 0
    for prediction, match in rows:
        snap_result = await db.execute(
            select(OddsSnapshot).where(
                OddsSnapshot.match_id == match.id,
                OddsSnapshot.market == prediction.market,
                OddsSnapshot.selection == prediction.selection,
                OddsSnapshot.captured_at <= match.kickoff_at,
                OddsSnapshot.captured_at > prediction.source_odds_at,
            )
        )
        snapshots = snap_result.scalars().all()
        if not snapshots:
            # The window may have changed between the existence check and load.
            continue

        # Last quote per bookmaker as of kickoff, then the best (highest) price
        # across bookmakers — the same "best odds" methodology used to pick the
        # entry price, so the comparison is apples-to-apples.
        latest_per_bookmaker: dict[str, OddsSnapshot] = {}
        for snap in snapshots:
            existing = latest_per_bookmaker.get(snap.bookmaker)
            if existing is None or snap.captured_at > existing.captured_at:
                latest_per_bookmaker[snap.bookmaker] = snap
        closing = max(latest_per_bookmaker.values(), key=lambda s: s.decimal_odds)

        if closing.captured_at <= prediction.source_odds_at:
            continue
        entry = prediction.source_decimal_odds
        if not entry or entry <= 1.0 or not closing.decimal_odds or closing.decimal_odds <= 1.0:
            continue

        prediction.closing_decimal_odds = closing.decimal_odds
        prediction.closing_implied_probability = closing.implied_probability
        prediction.closing_odds_at = closing.captured_at
        prediction.closing_bookmaker = closing.bookmaker
        prediction.clv_percentage = round(entry / closing.decimal_odds - 1.0, 6)
        captured += 1

    if captured:
        await db.commit()
    return {
        "candidates": len(rows),
        "captured": captured,
    }


def _invalid_clv_filter():
    return or_(
        Prediction.source_odds_at.is_(None),
        Prediction.closing_odds_at.is_(None),
        Prediction.closing_odds_at <= Prediction.source_odds_at,
    )


async def invalidate_stale_clv(db: AsyncSession, *, apply: bool = False) -> dict:
    """Clear CLV values that cannot be a genuine closing line.

    A row is invalid when it has closing odds but no entry timestamp, no closing
    timestamp, or a closing timestamp at or before the entry timestamp. The
    historical backlog was written before the strict ordering guard existed and
    reports 65.6% of rows as "closing == source", which is not CLV at all.

    ``apply=False`` is a dry run: it only counts. ``apply=True`` nulls the
    closing fields so no consumer can read a fabricated zero CLV.
    """
    condition = Prediction.closing_decimal_odds.is_not(None) & _invalid_clv_filter()
    total = await db.scalar(
        select(func.count()).select_from(Prediction).where(condition)
    )
    if not apply:
        return {"invalid_rows": int(total or 0), "cleared": 0, "applied": False}

    cleared = 0
    rows = (await db.execute(select(Prediction).where(condition))).scalars().all()
    for prediction in rows:
        prediction.closing_decimal_odds = None
        prediction.closing_implied_probability = None
        prediction.closing_odds_at = None
        prediction.closing_bookmaker = None
        prediction.clv_percentage = None
        cleared += 1
    if cleared:
        await db.commit()
    return {"invalid_rows": int(total or 0), "cleared": cleared, "applied": True}
