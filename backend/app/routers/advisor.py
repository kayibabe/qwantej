from __future__ import annotations

from datetime import date, timezone
from typing import Optional
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_optional, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.advisor_service import (
    get_advisor_insights,
    chat_with_advisor,
    _create_acca_bet,
    _get_advisory_cache,
    _call_advisor,
    invalidate_advisory_cache,
)

router = APIRouter(prefix="/api/advisor", tags=["advisor"])

# Per-user rate-limit timestamps (in-process; resets on restart — good enough)
_last_force_at: dict[int, float] = {}
_last_chat_at:  dict[int, float] = {}


class _ChatRequest(BaseModel):
    question: str
    history: list[dict] = []


class _ExplainPicksRequest(BaseModel):
    bets: list[dict]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_pro(current_user: Optional[User]) -> User:
    if (
        current_user is None
        or current_user.tier not in ("pro", "elite")
        or current_user.subscription_status != "active"
    ):
        raise HTTPException(status_code=403, detail="AI Advisory requires an active Pro subscription.")
    return current_user


def _parse_date(date_str: Optional[str]) -> date:
    if not date_str:
        from datetime import datetime
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date — expected YYYY-MM-DD.")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def advisor_insights(
    date_str: Optional[str] = Query(None),
    fixture_ids: Optional[str] = Query(None, description="Comma-separated fixture IDs to limit analysis"),
    force: bool = Query(False, description="Bypass cache and re-run AI pipeline"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Run the AI advisory council for a given date.

    Tries each configured provider in order (Claude → Gemini → Cerebras → Groq → Mistral)
    and runs Scout, Strategist, Skeptic concurrently. At least one provider key must be set
    in backend/.env; returns a setup message when none are configured.
    """
    user = _require_pro(current_user)
    target_date = _parse_date(date_str)

    if force:
        uid = user.id
        now = time.monotonic()
        last = _last_force_at.get(uid, 0)
        if now - last < 60:
            raise HTTPException(status_code=429, detail="Refresh is rate-limited — try again in a minute.")
        _last_force_at[uid] = now

    fids: list[int] | None = None
    if fixture_ids:
        try:
            fids = [int(x.strip()) for x in fixture_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="fixture_ids must be comma-separated integers.")

    return await get_advisor_insights(db, target_date, fixture_ids=fids, current_user=user, force=force)


@router.post("/track-acca")
async def track_acca(
    date_str: Optional[str] = Query(None),
    expected_odds: Optional[float] = Query(None, description="Combined odds the user sees — triggers cache refresh if stale"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Add the day's AI acca to the current user's bet tracker (opt-in — viewing
    the advisory never tracks). Idempotent per fingerprint: same legs = same
    row; different legs = new row, even on the same date.
    """
    user = _require_pro(current_user)
    target_date = _parse_date(date_str)

    cached = await _get_advisory_cache(db, target_date)

    # If expected_odds is supplied and cached combined_odds differ by more than
    # 0.10, the cache may be stale — force a fresh run.
    if cached and expected_odds is not None:
        acca_data = cached.get("acca_builder", {})
        tickets = acca_data.get("tickets", [acca_data] if acca_data.get("legs") else [])
        if tickets:
            cached_odds = tickets[0].get("combined_odds")
            if cached_odds and abs(float(cached_odds) - expected_odds) > 0.10:
                await invalidate_advisory_cache(db, target_date)
                cached = None

    if cached is None:
        cached = await get_advisor_insights(db, target_date, current_user=user, force=True)

    acca_data = cached.get("acca_builder", {})
    tickets = acca_data.get("tickets", [acca_data] if acca_data.get("legs") else [])
    if not tickets or not tickets[0].get("legs"):
        raise HTTPException(status_code=404, detail="No accumulator available to track.")

    tracked = await _create_acca_bet(db, tickets[0], target_date, user)
    return {"tracked": tracked, "message": "Acca added to your tracker." if tracked else "Already tracked."}


@router.post("/chat")
async def advisor_chat(
    body: _ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Conversational AI chat for pro subscribers.
    Accepts a question + prior conversation history and returns the assistant reply.
    History items: [{"role": "user"|"assistant", "content": "..."}]
    """
    user = _require_pro(current_user)

    uid = user.id
    now = time.monotonic()
    if now - _last_chat_at.get(uid, 0) < 5:
        raise HTTPException(status_code=429, detail="Slow down — one message at a time.")
    _last_chat_at[uid] = now

    if not body.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    answer = await chat_with_advisor(body.question, body.history)
    return {"answer": answer, "role": "assistant"}


@router.post("/explain-picks")
async def explain_picks(
    body: _ExplainPicksRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Batch-explain all system-tracked picks for a day in a single LLM call.
    Returns {"explanations": {"<bet_id>": "2-sentence analysis", ...}}.
    """
    user = _require_pro(current_user)

    if not body.bets:
        return {"explanations": {}}

    from app.services.advisor_service import _call_advisor, _ADVISORS
    explain_def = {
        "name": "explainer",
        "role": "Pick Explainer",
        "emoji": "💡",
        "models": {
            "claude":   "claude-haiku-4-5-20251001",
            "gemini":   "gemini-2.0-flash",
            "cerebras": "llama3.3-70b",
            "groq":     "llama-3.1-8b-instant",
            "mistral":  "open-mistral-nemo",
        },
        "system": (
            "You are a concise football betting analyst. For each pick, give a 2-sentence explanation "
            "of why the model selected it, referencing the probability and market data. "
            "Return JSON: {\"explanations\": {\"<id>\": \"<explanation>\"}}."
        ),
        "task": (
            "Explain these picks in 2 sentences each.\n"
            + "\n".join(
                f"ID {b.get('id', i)}: {b.get('match_name', '?')} | {b.get('market_type', '?')} "
                f"@ {b.get('odd', '?')} — {b.get('notes', '')}"
                for i, b in enumerate(body.bets[:20])
            )
        ),
    }

    _, result = await _call_advisor(explain_def, "")
    return {"explanations": result.get("explanations", {})}
