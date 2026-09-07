"""Settlement service: calls the pure engine and persists to the settlements table.

This is the single database-writing entry point for settlement.  The pure
engine (`qwantej.settlement.engine.settle`) computes all metrics; this
service enforces idempotency, resolves outcomes from fixture scoreines, and
writes the ORM row.  `resolve_outcome` and `find_closing_odds` carry no
side-effects and are tested independently of the write path.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Fixture,
    OddsQuote,
    Prediction,
    Settlement,
    SettlementOutcome as OrmSettlementOutcome,
)
from qwantej.settlement.engine import settle as _settle_engine
from qwantej.settlement.types import SettlementOutcome as EngineOutcome


class SettlementError(ValueError):
    """Raised when a prediction cannot be settled; nothing is written."""


# ---------------------------------------------------------------------------
# Outcome resolution (pure — no I/O)
# ---------------------------------------------------------------------------

def resolve_outcome(
    fixture: Fixture,
    market: str,
    selection: str,
    *,
    line: float | None = None,
) -> EngineOutcome:
    """Derive settlement outcome from a finished fixture's scoreline.

    Returns VOID when home_goals or away_goals is None (result not yet
    recorded).  Raises SettlementError for unknown markets or selections.

    Supported markets:
      ``1X2``           — selections ``home`` / ``draw`` / ``away``
      ``DOUBLE_CHANCE`` — selections ``home_draw`` (1X) / ``draw_away`` (X2) /
                          ``home_away`` (12)
      ``BTTS``          — selections ``yes`` / ``no``
      ``TOTALS``        — selections ``over`` / ``under``; ``line`` required
    """
    home = fixture.home_goals
    away = fixture.away_goals

    if home is None or away is None:
        return EngineOutcome.VOID

    total = home + away
    market_key = market.upper()
    sel = selection.lower()

    if market_key == "1X2":
        if home > away:
            result = "home"
        elif home == away:
            result = "draw"
        else:
            result = "away"
        return EngineOutcome.WIN if sel == result else EngineOutcome.LOSS

    if market_key == "DOUBLE_CHANCE":
        if sel == "home_draw":
            won = home >= away
        elif sel == "draw_away":
            won = home <= away
        elif sel == "home_away":
            won = home != away
        else:
            raise SettlementError(f"Unknown DOUBLE_CHANCE selection: {selection!r}")
        return EngineOutcome.WIN if won else EngineOutcome.LOSS

    if market_key == "BTTS":
        both = home > 0 and away > 0
        if sel == "yes":
            return EngineOutcome.WIN if both else EngineOutcome.LOSS
        if sel == "no":
            return EngineOutcome.WIN if not both else EngineOutcome.LOSS
        raise SettlementError(f"Unknown BTTS selection: {selection!r}")

    if market_key == "TOTALS":
        if line is None:
            raise SettlementError("line is required for TOTALS market")
        if float(total) == float(line):
            return EngineOutcome.PUSH
        if sel == "over":
            return EngineOutcome.WIN if total > line else EngineOutcome.LOSS
        if sel == "under":
            return EngineOutcome.WIN if total < line else EngineOutcome.LOSS
        raise SettlementError(f"Unknown TOTALS selection: {selection!r}")

    raise SettlementError(f"Unsupported market: {market!r}")


# ---------------------------------------------------------------------------
# Closing-odds lookup
# ---------------------------------------------------------------------------

def find_closing_odds(
    session: Session,
    *,
    fixture_id: uuid.UUID,
    market: str,
    selection: str,
    line: float | None,
    after: datetime,
) -> tuple[float | None, str | None]:
    """Return ``(decimal_odds, bookmaker)`` for the last quote recorded after *after*.

    Pass ``after=fixture.kickoff_utc`` so that only post-kickoff quotes are
    treated as closing odds; pre-match quotes are decision-time data and must
    not leak into the settlement record (framework §13).

    Returns ``(None, None)`` when no qualifying quote exists.
    """
    stmt = (
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.market == market,
            OddsQuote.selection == selection,
            OddsQuote.captured_at > after,
        )
        .order_by(OddsQuote.captured_at.desc())
        .limit(1)
    )
    if line is not None:
        stmt = stmt.where(OddsQuote.line == Decimal(str(line)))
    quote = session.scalar(stmt)
    if quote is None:
        return None, None
    return float(quote.decimal_odds), quote.bookmaker


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------

def is_already_settled(
    session: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
) -> bool:
    """True when a non-correction Settlement row already exists for this subject.

    Correction rows carry a non-NULL ``supersedes_id``; the original
    settlement has ``supersedes_id IS NULL``.  The idempotency guard only
    blocks duplicate originals so corrections can always be appended.
    """
    stmt = (
        select(Settlement.id)
        .where(
            Settlement.subject_type == subject_type,
            Settlement.subject_id == subject_id,
            Settlement.supersedes_id.is_(None),
        )
        .limit(1)
    )
    return session.scalar(stmt) is not None


# ---------------------------------------------------------------------------
# Enum mapping — engine domain type → ORM storage type
# ---------------------------------------------------------------------------

_OUTCOME_MAP: dict[EngineOutcome, OrmSettlementOutcome] = {
    EngineOutcome.WIN: OrmSettlementOutcome.WIN,
    EngineOutcome.LOSS: OrmSettlementOutcome.LOSS,
    EngineOutcome.VOID: OrmSettlementOutcome.VOID,
    EngineOutcome.PUSH: OrmSettlementOutcome.PUSH,
}


# ---------------------------------------------------------------------------
# Primary write path
# ---------------------------------------------------------------------------

def settle_prediction(
    session: Session,
    prediction: Prediction,
    *,
    outcome: EngineOutcome,
    settled_at: datetime,
    closing_odds: float | None = None,
    result_source: str = "api-football",
    reason_codes: list[str] | None = None,
    supersedes_id: uuid.UUID | None = None,
) -> Settlement:
    """Compute settlement metrics for *prediction* and add the row to *session*.

    Idempotency: raises :exc:`SettlementError` when a non-correction settlement
    already exists and *supersedes_id* is not supplied.  A correction row must
    explicitly name the row it supersedes so the audit trail is unambiguous.

    Individual predictions are paper-tracked (``stake=None``); financial P/L
    lives on the :class:`~backend.models.settlements.Accumulator` ticket, not
    the individual leg.  CLV is computed whenever *closing_odds* is supplied
    and *prediction* carries ``executable_odds``.

    The caller is responsible for committing the session.
    """
    if supersedes_id is None and is_already_settled(
        session,
        subject_type="prediction",
        subject_id=prediction.id,
    ):
        raise SettlementError(
            f"Prediction {prediction.id} is already settled; "
            "supply supersedes_id to record a correction"
        )

    taken_p = (
        float(prediction.conservative_probability)
        if prediction.conservative_probability is not None
        else None
    )
    taken_odds = (
        float(prediction.executable_odds)
        if prediction.executable_odds is not None
        else None
    )

    sp = _settle_engine(
        subject_type="prediction",
        subject_id=str(prediction.id),
        outcome=outcome,
        settled_at=settled_at,
        taken_probability=taken_p,
        taken_odds=taken_odds,
        closing_odds=closing_odds,
        stake=None,
        result_source=result_source,
        reason_codes=reason_codes,
    )

    row = Settlement(
        subject_type=sp.subject_type,
        subject_id=prediction.id,
        outcome=_OUTCOME_MAP[sp.outcome],
        settled_at=sp.settled_at,
        result_source=sp.result_source,
        stake=sp.stake,
        gross_return=sp.gross_return,
        profit_loss=sp.profit_loss,
        taken_odds=sp.taken_odds,
        closing_odds=sp.closing_odds,
        closing_probability=sp.closing_probability,
        clv=sp.clv,
        taken_probability=sp.taken_probability,
        brier_contribution=sp.brier_contribution,
        log_loss_contribution=sp.log_loss_contribution,
        calibration_bin=sp.calibration_bin,
        reason_codes=sp.reason_codes,
        supersedes_id=supersedes_id,
    )
    session.add(row)
    return row
