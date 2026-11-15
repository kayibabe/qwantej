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

from sqlalchemy import and_, exists, func, or_, select
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


def clv_is_valid(prediction: Prediction, *, kickoff_at: datetime | None = None) -> bool:
    """True only for a genuine post-entry, pre-kickoff closing quote.

    This is the single row-level definition of valid CLV. Pass ``kickoff_at``
    when the fixture is available so a post-kickoff close cannot count; the
    capture path already guarantees that ordering, but consumers should not
    have to trust it.
    """
    if not (
        prediction.closing_decimal_odds
        and prediction.clv_percentage is not None
        and prediction.closing_odds_at
        and prediction.source_odds_at
        and prediction.closing_odds_at > prediction.source_odds_at
    ):
        return False
    if kickoff_at is not None and prediction.closing_odds_at > kickoff_at:
        return False
    return True


def clv_is_invalid(prediction: Prediction, *, kickoff_at: datetime | None = None) -> bool:
    """The exact row-level complement of :func:`clv_is_valid`."""
    return not clv_is_valid(prediction, kickoff_at=kickoff_at)


# Three outcomes, not two. "unmeasured" is not a CLV value: it means the capture
# path never observed a second price before kickoff, so the pick carries no
# closing-line information at all. Recording that as "invalid" lets a host
# outage read later as the market disagreeing with the pick.
CLV_VALID = "valid"
CLV_INVALID = "invalid"
CLV_UNMEASURED = "unmeasured"


def clv_measurement(
    prediction: Prediction,
    *,
    has_post_entry_quote: bool,
    kickoff_at: datetime | None = None,
) -> str:
    """Classify one stored prediction: valid, invalid, or unmeasured."""
    if clv_is_valid(prediction, kickoff_at=kickoff_at):
        return CLV_VALID
    return CLV_INVALID if has_post_entry_quote else CLV_UNMEASURED


def post_entry_quote_condition(prediction: Prediction, match: Match):
    """A stored quote strictly after entry and no later than kickoff."""
    return and_(
        OddsSnapshot.match_id == match.id,
        OddsSnapshot.market == prediction.market,
        OddsSnapshot.selection == prediction.selection,
        OddsSnapshot.captured_at > prediction.source_odds_at,
        OddsSnapshot.captured_at <= match.kickoff_at,
    )


async def has_post_entry_quote(
    db: AsyncSession, prediction: Prediction | None, match: Match | None
) -> bool:
    """Whether any usable quote was captured after entry and before kickoff."""
    if prediction is None or match is None or prediction.source_odds_at is None:
        return False
    found = await db.scalar(
        select(OddsSnapshot.id)
        .where(post_entry_quote_condition(prediction, match))
        .limit(1)
    )
    return found is not None


def valid_clv_condition(match=None):
    """SQL counterpart of :func:`clv_is_valid`.

    ``match`` is the ``Match`` entity when the caller's query already joins
    fixtures; it adds the kickoff bound. Callers should join ``Match`` (an outer
    join is fine) so the two definitions agree.
    """
    condition = and_(
        Prediction.closing_decimal_odds.is_not(None),
        Prediction.clv_percentage.is_not(None),
        Prediction.source_odds_at.is_not(None),
        Prediction.closing_odds_at.is_not(None),
        Prediction.closing_odds_at > Prediction.source_odds_at,
    )
    if match is not None:
        condition = and_(condition, Prediction.closing_odds_at <= match.kickoff_at)
    return condition


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


def invalid_clv_condition():
    """Rows that cannot be a genuine close. Complement of ``valid_clv_condition``.

    Kept as an explicit OR rather than ``NOT valid`` because SQL three-valued
    logic would turn a NULL comparison into NULL, not TRUE, and these rows must
    be cleared.
    """
    return or_(
        Prediction.source_odds_at.is_(None),
        Prediction.closing_odds_at.is_(None),
        Prediction.clv_percentage.is_(None),
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
    condition = Prediction.closing_decimal_odds.is_not(None) & invalid_clv_condition()
    total = await db.scalar(
        select(func.count()).select_from(Prediction).where(condition)
    )
    if not apply:
        return {"invalid_rows": int(total or 0), "cleared": 0, "applied": False}

    cleared = 0
    rows = (await db.execute(select(Prediction).where(condition))).scalars().all()
    for prediction in rows:
        if not clv_is_invalid(prediction):
            # The SQL filter and the row predicate disagree; never clear a
            # row that the canonical definition still calls valid.
            continue
        prediction.closing_decimal_odds = None
        prediction.closing_implied_probability = None
        prediction.closing_odds_at = None
        prediction.closing_bookmaker = None
        prediction.clv_percentage = None
        cleared += 1
    if cleared:
        await db.commit()
    return {"invalid_rows": int(total or 0), "cleared": cleared, "applied": True}
