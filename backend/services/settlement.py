"""Settlement service: calls the pure engine and persists to the settlements table.

This is the single database-writing entry point for settlement.  The pure
engine (``qwantej.settlement.engine.settle``) computes all metrics; this
service enforces idempotency, resolves outcomes from fixture scorelines, and
writes the ORM row.  ``resolve_outcome`` and ``find_closing_odds`` carry no
side-effects and are tested independently of the write path.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Fixture,
    OddsQuote,
    Prediction,
    Settlement,
)
from backend.models import (
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

    Supported markets and their canonical selection labels (as stored by
    the ingestion layer):

    ``1X2``
        ``home`` / ``draw`` / ``away``

    ``DOUBLE_CHANCE``
        ``1X`` (home-or-draw) / ``X2`` (draw-or-away) / ``12`` (home-or-away)

    ``BTTS``
        ``yes`` / ``no``

    ``TOTALS``
        ``over`` / ``under``; *line* required (e.g. 2.5)
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
        # Canonical ingestion values: "1X", "X2", "12"
        if sel == "1x":
            won = home >= away          # home or draw
        elif sel == "x2":
            won = home <= away          # draw or away
        elif sel == "12":
            won = home != away          # home or away (no draw)
        else:
            raise SettlementError(
                f"Unknown DOUBLE_CHANCE selection: {selection!r}. "
                "Expected '1X', 'X2', or '12'."
            )
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

# Upper bound after kickoff: quotes this late are unlikely to represent
# the real closing line (match is over and in-play markets have closed).
_CLOSING_WINDOW_HOURS = 5


def find_closing_odds(
    session: Session,
    *,
    fixture_id: uuid.UUID,
    market: str,
    selection: str,
    line: float | None,
    after: datetime,
) -> tuple[float | None, str | None, uuid.UUID | None]:
    """Return ``(decimal_odds, bookmaker, quote_id)`` for the last quote in the
    closing window.

    The closing window is ``(after, after + _CLOSING_WINDOW_HOURS]``.  Pass
    ``after=fixture.kickoff_utc`` so that only post-kickoff quotes qualify
    as closing odds; pre-match prices are decision-time data and must not
    leak into settlement fields (framework §13).  Quotes arriving more than
    ``_CLOSING_WINDOW_HOURS`` after kickoff are excluded — the match is
    almost certainly over by then and any remaining quotes represent stale
    in-play markets.

    The ``ORDER BY captured_at DESC, id DESC`` tie-breaker makes selection
    deterministic when two quotes share the same timestamp.

    Returns ``(None, None, None)`` when no qualifying quote exists.
    """
    before = after + timedelta(hours=_CLOSING_WINDOW_HOURS)
    stmt = (
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.market == market,
            OddsQuote.selection == selection,
            OddsQuote.captured_at > after,
            OddsQuote.captured_at <= before,
        )
        .order_by(OddsQuote.captured_at.desc(), OddsQuote.id.desc())
        .limit(1)
    )
    if line is not None:
        stmt = stmt.where(OddsQuote.line == Decimal(str(line)))
    quote = session.scalar(stmt)
    if quote is None:
        return None, None, None
    return float(quote.decimal_odds), quote.bookmaker, quote.id


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
    blocks duplicate originals — corrections can always be appended.

    This check is advisory only: the database partial unique index
    ``uq_settlements_active_subject`` (added in migration b2d4f6a8c1e3)
    provides the race-safe enforcement.  Both guards are needed: the
    application check gives a descriptive error; the DB index prevents
    the silent duplicate that would occur if two workers pass the
    read-then-insert race window simultaneously.
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
    closing_quote_id: uuid.UUID | None = None,
    result_source: str = "api-football",
    reason_codes: list[str] | None = None,
    supersedes_id: uuid.UUID | None = None,
) -> Settlement:
    """Compute settlement metrics for *prediction* and add the row to *session*.

    Idempotency: raises :exc:`SettlementError` when a non-correction settlement
    already exists and *supersedes_id* is not supplied.  A correction row must
    explicitly name the row it supersedes.

    Correction lineage: when *supersedes_id* is given it must refer to an
    existing Settlement whose ``subject_id`` matches *prediction.id*.  This
    prevents a correction from being accidentally attached to the wrong subject.

    Individual predictions are paper-tracked (``stake=None``); financial P/L
    lives on the :class:`~backend.models.settlements.Accumulator` ticket.
    CLV is computed when *closing_odds* is given and the prediction carries
    ``executable_odds``.

    The caller is responsible for committing the session.
    """
    if supersedes_id is None:
        if is_already_settled(session, subject_type="prediction", subject_id=prediction.id):
            raise SettlementError(
                f"Prediction {prediction.id} is already settled; "
                "supply supersedes_id to record a correction"
            )
    else:
        original = session.get(Settlement, supersedes_id)
        if original is None:
            raise SettlementError(f"supersedes_id {supersedes_id} does not exist")
        if original.subject_id != prediction.id:
            raise SettlementError(
                f"supersedes_id {supersedes_id} belongs to prediction "
                f"{original.subject_id}, not {prediction.id}"
            )

    if closing_quote_id is not None:
        quote = session.get(OddsQuote, closing_quote_id)
        if quote is None:
            raise SettlementError(
                f"closing_quote_id {closing_quote_id} does not exist"
            )
        if quote.fixture_id != prediction.fixture_id:
            raise SettlementError(
                f"closing_quote_id {closing_quote_id} belongs to fixture "
                f"{quote.fixture_id}, not {prediction.fixture_id}"
            )
        if quote.market.upper() != prediction.market.upper():
            raise SettlementError(
                f"closing_quote_id {closing_quote_id} is for market "
                f"{quote.market!r}, not {prediction.market!r}"
            )
        if closing_odds is not None and abs(float(quote.decimal_odds) - closing_odds) > 1e-4:
            raise SettlementError(
                f"closing_quote_id {closing_quote_id} has decimal_odds "
                f"{float(quote.decimal_odds):.4f} but closing_odds={closing_odds:.4f}"
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
        closing_quote_id=closing_quote_id,
    )
    session.add(row)
    return row
