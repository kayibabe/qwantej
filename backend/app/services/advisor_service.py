"""
advisor_service.py — Multi-model AI advisory council with provider chain fallback.

Provider priority per advisor (first configured key with available quota wins):
  1. Anthropic Claude  — Qwantej_CLAUDE_KEY      — highest quality, paid
  2. Google Gemini     — GEMINI_API_KEY         — free, no card required (aistudio.google.com)
  3. Cerebras          — CEREBRAS_API_KEY       — free, very fast Llama inference
  4. Groq              — GROQ_API_KEY           — free Llama/Mixtral, daily limits
  5. Mistral           — MISTRAL_API_KEY        — free open-mistral-nemo

Each provider returns None on billing/quota exhaustion so the next is tried
transparently. Rate-limit errors are returned as soft errors (shown in UI).
Configure as many keys as you like — more keys = more resilience.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import anthropic
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, DUAL_HIGH_ODDS_CEILING, OVER_GOALS_SUPPRESSED_LEAGUES, DISABLED_LEAGUES
from app.models.signal import Signal
from app.models.fixture import Fixture
from app.services.performance_intelligence import PerformanceWeights, compute_performance_weights

logger = logging.getLogger(__name__)

GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
MISTRAL_URL  = "https://api.mistral.ai/v1/chat/completions"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_ADVISORY_CACHE_PREFIX = "advisory_cache_"

# Per-advisor source_rule_key used when auto-tracking picks.
_ADVISOR_RULE_KEYS: dict[str, str] = {
    "scout":      "scout_pick",
    "strategist": "strategist_pick",
    "skeptic":    "skeptic_pick",
}
_ALL_ADVISORY_KEYS = list(_ADVISOR_RULE_KEYS.values()) + ["acca_advisory"]

# Phrases that indicate quota/billing exhaustion (trigger provider fallback).
_QUOTA_PHRASES = [
    "quota", "billing", "exceeded", "insufficient_quota",
    "rate limit", "rate_limit", "429", "overloaded",
]

# ── Advisor definitions ────────────────────────────────────────────────────────

_ADVISORS: list[dict] = [
    {
        "name": "acca_builder",
        "role": "Daily accumulator recommendation",
        "emoji": "🎯",
        "models": {
            "claude":   "claude-sonnet-5",
            "gemini":   "gemini-2.0-flash",
            "cerebras": "llama3.3-70b",
            "groq":     "llama-3.3-70b-versatile",
            "mistral":  "open-mistral-nemo",
        },
        "system": (
            "You are a specialist football accumulator analyst. You receive a pool of pre-screened "
            "signals ranked by dual-engine probability agreement. Your role is to build as many "
            "non-overlapping accumulator tickets as possible from the pool. Each ticket: 3–4 legs. "
            "No fixture may appear in more than one ticket. Prioritise High confidence picks with "
            "Both engine agreement. Return JSON with keys: "
            '"tickets" (array of ticket objects, each with keys: "legs" (array of {home_team, away_team, '
            'market, odd, fixture_id}), "combined_odds", "confidence", "rank_label"), '
            '"reasoning" (string). Order tickets by confidence (highest first).'
        ),
        "task": (
            "Build the best accumulator tickets from today's signal pool. "
            "Only use picks with odds ≥ 1.30 and where edge exists. "
            "Return only valid JSON."
        ),
    },
    {
        "name": "scout",
        "role": "The Scout",
        "emoji": "🔍",
        "models": {
            "claude":   "claude-sonnet-5",
            "gemini":   "gemini-2.0-flash",
            "cerebras": "llama3.3-70b",
            "groq":     "llama-3.3-70b-versatile",
            "mistral":  "open-mistral-nemo",
        },
        "system": (
            "You are a football match analyst. You receive a batch of model-generated betting signals "
            "alongside match context: recent form, head-to-head records, goals scored/conceded, and "
            "team stats. Your job is to validate each signal against the ACTUAL match evidence — "
            "confirm when the numbers tell a coherent story, flag when they don't. "
            "Return JSON with keys: "
            '"verdict" ("Strong" | "Mixed" | "Weak"), '
            '"top_picks" (array of {home_team, away_team, market, odd, fixture_id, reason}), '
            '"warnings" (array of strings), "summary" (2–3 sentence overview).'
        ),
        "task": "Analyse today's signals against the match evidence. Return only valid JSON.",
    },
    {
        "name": "strategist",
        "role": "The Strategist",
        "emoji": "📊",
        "models": {
            "claude":   "claude-sonnet-5",
            "gemini":   "gemini-2.0-flash",
            "cerebras": "llama3.3-70b",
            "groq":     "llama-3.3-70b-versatile",
            "mistral":  "open-mistral-nemo",
        },
        "system": (
            "You are a senior football betting portfolio analyst. You receive a batch of signals from "
            "an AI dual-engine system and related match data. Your job is to assess the PORTFOLIO — "
            "not each pick in isolation. Look for: correlated outcomes (e.g. multiple Over 2.5 bets "
            "in same league), concentration risk, league-specific reliability, and overall bankroll "
            "advice. "
            "Return JSON with keys: "
            '"verdict" ("Strong" | "Mixed" | "Weak"), '
            '"top_picks" (array of {home_team, away_team, market, odd, fixture_id, reason}), '
            '"warnings" (array of strings), "summary" (2–3 sentence portfolio overview).'
        ),
        "task": "Assess the portfolio of today's signals. Return only valid JSON.",
    },
    {
        "name": "skeptic",
        "role": "The Skeptic",
        "emoji": "🧐",
        "models": {
            "claude":   "claude-sonnet-5",
            "gemini":   "gemini-2.0-flash",
            "cerebras": "llama3.3-70b",
            "groq":     "llama-3.3-70b-versatile",
            "mistral":  "open-mistral-nemo",
        },
        "system": (
            "You are a contrarian football betting analyst — your job is to find reasons NOT to bet. "
            "You receive the same signals as the other advisors, plus an extra section highlighting "
            "market-vs-model divergences, thin bookmaker coverage, odds drift, and engine contradictions. "
            "Your role: interrogate each signal for weaknesses, identify the two or three picks that "
            "survive scrutiny, and warn strongly against the rest. "
            "Return JSON with keys: "
            '"verdict" ("Strong" | "Mixed" | "Weak"), '
            '"top_picks" (array of {home_team, away_team, market, odd, fixture_id, reason}), '
            '"warnings" (array of strings), "summary" (2–3 sentence contrarian take).'
        ),
        "task": "Interrogate today's signals from a contrarian perspective. Return only valid JSON.",
    },
]

# ── Context builders ───────────────────────────────────────────────────────────

def _build_context(
    rows: list,
    match_infos: dict,
    perf_weights: "PerformanceWeights | None",
) -> str:
    lines = [f"=== TODAY'S SIGNALS ({len(rows)} matches) ===\n"]
    for i, (sig, fix) in enumerate(rows):
        ko = sig.kickoff_at.strftime("%H:%M CAT") if sig.kickoff_at else "TBD"
        league_info = f"{getattr(sig, 'league', 'Unknown League')} | Tier {getattr(fix, 'tier', '?')} | KO: {ko}"
        lines.append(
            f"{i+1}. [{fix.home_team} vs {fix.away_team}] (id:{fix.id}) | {league_info}"
        )
        lines.append(
            f"   Market: {sig.market} | Dual confidence: {sig.dual_confidence} | "
            f"Agreement: {sig.dual_agreement} | Quality: {sig.dual_quality_score:.2f}"
        )
        lines.append(
            f"   Bayesian: {sig.bayesian_prob:.1%} @ {sig.bayesian_best_odd:.2f} "
            f"({sig.bayesian_bookmaker}, {sig.bayesian_bookmaker_count} books)"
        )
        lines.append(
            f"   Poisson: {sig.poisson_prob:.1%} | λH={sig.poisson_lambda_h:.2f} λA={sig.poisson_lambda_a:.2f} "
            f"| Grade: {sig.poisson_grade} | Rule: {sig.poisson_rule_strong}"
        )
        mi = match_infos.get(fix.id, {})
        home_h = mi.get("home_highlights", [])
        away_h = mi.get("away_highlights", [])
        if home_h:
            lines.append(f"   {fix.home_team} form: {', '.join(str(x) for x in home_h[:4])}")
        if away_h:
            lines.append(f"   {fix.away_team} form: {', '.join(str(x) for x in away_h[:4])}")
        h2h = mi.get("h2h", [])
        if h2h:
            scores = [f"{g.get('home_score','?')}-{g.get('away_score','?')}" for g in h2h[:3]]
            lines.append(f"   H2H (last {len(scores)}): {', '.join(scores)}")
        lines.append("")

    if perf_weights:
        lines.append("=== SYSTEM PERFORMANCE (recent context) ===")
        for (confidence, market), samples in perf_weights.by_confidence_market.items():
            if samples:
                wr = sum(1 for s in samples if s.get("win_rate", 0) > 0) / len(samples)
                roi = sum(s.get("roi", 0) for s in samples) / len(samples)
                lines.append(f"  {confidence} × {market}: WR={wr:.1%} ROI={roi:+.1%}")

    return "\n".join(lines)


def _build_skeptic_extras(rows: list) -> str:
    flags = []
    for sig, fix in rows:
        label = f"{fix.home_team} vs {fix.away_team} ({sig.market})"
        if sig.dual_confidence == "High" and sig.bayesian_best_odd < 1.40:
            flags.append(
                f"SHORT ODDS ({sig.bayesian_best_odd:.2f}) — 'High' confidence on a heavy favourite; "
                "any model calibration error could flip this to negative EV"
            )
        drift = getattr(sig, "odds_drift_pct", None)
        if drift and drift > 5:
            flags.append(
                f"ODDS DRIFTED +{drift:.1f}% since open — market is moving AGAINST this signal; "
                "sharp money disagrees"
            )
        if sig.bayesian_bookmaker_count == 1:
            flags.append(
                f"THIN COVERAGE (1 book) [{label}] — signal rests on a single bookmaker's price; "
                "more likely to be noise than a genuine edge"
            )
        gap = sig.bayesian_prob - (1 / sig.bayesian_best_odd) if sig.bayesian_best_odd else 0
        if gap > 0.12:
            flags.append(
                f"MODEL OVERCONFIDENT +{gap:.1%} vs market [{label}] — "
                "our model assigns considerably higher probability than the bookmaker; "
                "verify this isn't a systematic bias"
            )
        elif gap < -0.12:
            flags.append(
                f"MARKET OVERCONFIDENT {gap:.1%} vs model [{label}] — "
                "bookmaker is more bullish than our model; model may be correctly cautious"
            )
        if getattr(sig, "dual_agreement", "") == "Contradiction":
            flags.append(f"ENGINE CONTRADICTION [{label}] — Bayesian and Poisson disagree on direction")

    if not flags:
        return "\n=== SKEPTIC FOCUS: no major red flags detected ===\n"
    return "\n=== SKEPTIC FOCUS: DIVERGENCE & RISK FLAGS ===\n" + "\n".join(f"• {f}" for f in flags) + "\n"


# ── JSON extraction ─────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    logger.warning("Failed to parse LLM JSON response (first 200 chars): %s", text[:200])
    return _err("parse_error", "Advisor returned a malformed response.")


def _err(code: str, summary: str) -> dict[str, Any]:
    return {
        "error": code,
        "verdict": "Mixed",
        "top_picks": [],
        "warnings": [],
        "summary": summary,
    }


def _is_quota_error(message: str) -> bool:
    lower = message.lower()
    return any(phrase in lower for phrase in _QUOTA_PHRASES)


# ── Provider callers ────────────────────────────────────────────────────────────

async def _call_claude(advisor: dict, context: str, api_key: str) -> dict | None:
    model = advisor["models"]["claude"]
    system_prompt = advisor["system"]
    task_prompt = f"{context}\n\n{advisor['task']}"
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key, base_url="https://api.anthropic.com")
        message = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": task_prompt}],
        )
        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            logger.info("Claude returned empty text for %s — falling back", advisor["name"])
            return None
        return _extract_json(text)
    except anthropic.APITimeoutError:
        logger.info("Claude timeout — falling back (advisor=%s)", advisor["name"])
        return None
    except anthropic.AuthenticationError:
        return _err("claude_auth", "Anthropic API key is invalid.")
    except anthropic.RateLimitError:
        return _err("claude_429", "Claude rate limit — retry shortly.")
    except anthropic.APIStatusError as e:
        body = e.body if isinstance(e.body, dict) else {}
        if _is_quota_error(str(body.get("error", ""))) or e.status_code == 429:
            logger.warning("Claude quota (HTTP %s) — falling back (advisor=%s)", e.status_code, advisor["name"])
            return None
        return _err("error", "Claude advisor request failed.")
    except (anthropic.APIError, json.JSONDecodeError, Exception) as e:
        logger.warning("Claude %s error — falling back: %s", type(e).__name__, e)
        return None


async def _call_gemini(advisor: dict, context: str, api_key: str) -> dict | None:
    """Google Gemini via REST — no extra SDK needed beyond httpx.
    Free tier: 15 RPM, 1 million TPD on gemini-2.0-flash.
    Get key: aistudio.google.com/apikey
    """
    model = advisor["models"]["gemini"]
    url = GEMINI_URL.format(model=model)
    payload = {
        "system_instruction": {"parts": [{"text": advisor["system"]}]},
        "contents": [{"role": "user", "parts": [{"text": f"{context}\n\n{advisor['task']}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload, params={"key": api_key})
            if resp.status_code == 429 or _is_quota_error(resp.text.lower()):
                logger.info("Gemini quota — falling back (advisor=%s)", advisor["name"])
                return None
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_json(text)
    except httpx.HTTPStatusError as e:
        logger.warning("Gemini %s — falling back (advisor=%s)", e.response.status_code, advisor["name"])
        return None
    except (json.JSONDecodeError, KeyError, Exception) as e:
        logger.warning("Gemini %s error — falling back: %s", type(e).__name__, e)
        return None


async def _call_openai_compat(
    advisor: dict,
    context: str,
    api_key: str,
    base_url: str,
    provider: str,
) -> dict | None:
    """Generic caller for OpenAI-compatible chat completions (Groq, Cerebras, Mistral)."""
    model = advisor["models"][provider]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": advisor["system"]},
            {"role": "user", "content": f"{context}\n\n{advisor['task']}"},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(base_url, json=payload, headers=headers)
            if resp.status_code == 429 or _is_quota_error(resp.text.lower()):
                logger.info("%s daily quota — falling back (advisor=%s)", provider.title(), advisor["name"])
                return None
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return _extract_json(text)
    except httpx.HTTPStatusError as e:
        logger.warning("%s %s — falling back (advisor=%s)", provider, e.response.status_code, advisor["name"])
        return None
    except (json.JSONDecodeError, KeyError, Exception) as e:
        logger.warning("%s %s error — falling back: %s", provider, type(e).__name__, e)
        return None


async def _call_advisor(
    advisor: dict,
    context: str,
    extra_context: str = "",
) -> tuple[str, dict[str, Any]]:
    """Try each configured provider in order. Returns (model_label, result_dict)."""
    s = get_settings()
    full_context = context + extra_context

    PROVIDER_CHAIN = [
        ("claude",   s.Qwantej_claude_key,   None,         None),
        ("gemini",   s.gemini_api_key,        None,         None),
        ("cerebras", s.cerebras_api_key,      CEREBRAS_URL, "cerebras"),
        ("groq",     s.groq_api_key,          GROQ_URL,     "groq"),
        ("mistral",  s.mistral_api_key,       MISTRAL_URL,  "mistral"),
    ]

    for provider, key, url, compat_name in PROVIDER_CHAIN:
        if not key:
            continue
        logger.debug("Trying %s/%s for %s", provider, advisor["models"][provider], advisor["name"])
        if provider == "claude":
            result = await _call_claude(advisor, full_context, key)
        elif provider == "gemini":
            result = await _call_gemini(advisor, full_context, key)
        else:
            result = await _call_openai_compat(advisor, full_context, key, url, compat_name)

        if result is not None and "error" not in result:
            return (f"{provider}/{advisor['models'][provider]}", result)
        if result is not None and result.get("error") not in (None, "parse_error"):
            return ("none", result)

    return ("none", _err("no_provider", "All configured AI providers are at quota. Add more keys to .env."))


# ── Bet tracking helpers ────────────────────────────────────────────────────────

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _acca_fingerprint(legs: list[dict]) -> str:
    """Stable 12-char hex hash of an acca's legs.

    Uses fixture_id when available (exact, immune to name variation).
    Falls back to sorted home:away:market strings for legs without fixture_id.
    Stored as "Accumulator|<fp>" in selection_name for per-acca dedup.
    """
    parts = []
    for leg in legs:
        fid = leg.get("fixture_id")
        if fid:
            parts.append(str(fid))
        else:
            parts.append(f"{_norm(leg.get('home_team'))}:{_norm(leg.get('away_team'))}:{_norm(leg.get('market'))}")
    parts.sort()
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


async def _is_acca_tracked(
    db: AsyncSession,
    target_date: date,
    uid: int,
    fp: str | None = None,
) -> bool:
    """True when this user already has this specific acca in their tracker."""
    from app.models.bet import TrackedBet
    conditions = [
        TrackedBet.source_rule_key == "acca_advisory",
        TrackedBet.event_date == target_date,
        TrackedBet.user_id == uid,
    ]
    if fp:
        conditions.append(TrackedBet.selection_name == f"Accumulator|{fp}")
    else:
        conditions.append(TrackedBet.selection_name == "Accumulator")
    row = await db.scalar(select(TrackedBet.id).where(*conditions))
    return row is not None


async def _create_acca_bet(
    db: AsyncSession,
    acca: dict,
    target_date: date,
    current_user: Any | None,
) -> bool:
    """Persist the AI acca as a single TrackedBet row for authenticated users."""
    import sqlalchemy.exc
    from app.models.bet import TrackedBet

    legs = acca.get("legs", [])
    if not legs:
        return False

    uid = getattr(current_user, "id", None)
    if uid is None:
        return False

    fp = _acca_fingerprint(legs)
    existing = await db.scalar(
        select(TrackedBet.id).where(
            TrackedBet.source_rule_key == "acca_advisory",
            TrackedBet.event_date == target_date,
            TrackedBet.user_id == uid,
            TrackedBet.selection_name == f"Accumulator|{fp}",
        )
    )
    if existing:
        return False

    leg_labels = ", ".join(
        f"{leg.get('home_team')} vs {leg.get('away_team')} · {leg.get('market')} @ {float(leg.get('odd', 0)):.2f}"
        for leg in legs
    )
    n = len(legs)
    bet = TrackedBet(
        source_rule_key="acca_advisory",
        source_rule_label="AI Acca",
        event_date=target_date,
        user_id=uid,
        selection_name=f"Accumulator|{fp}",
        market_type="Accumulator",
        notes=json.dumps({
            "legs": legs,
            "combined_odds": acca.get("combined_odds"),
            "rank_label": acca.get("rank_label", "AI Acca of the Day"),
            "confidence": acca.get("confidence"),
            "leg_summary": leg_labels,
        }),
        match_name=f"AI Acca · {n} leg{'s' if n != 1 else ''}",
        combined_odds=acca.get("combined_odds"),
    )
    try:
        db.add(bet)
        await db.commit()
        return True
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        return False


async def auto_track_acca_legs(
    db: AsyncSession,
    acca: dict | list,
    target_date: date,
    replace: bool = False,
) -> int:
    """Create system TrackedBet rows for ACCA tickets at K50,000 flat stake.

    Accepts either a single acca dict or a list of ticket dicts. Idempotent by
    fingerprint. replace=True wipes all system_acca rows for the date first.
    Returns count of new ticket rows inserted.
    """
    from app.models.bet import TrackedBet

    tickets = acca if isinstance(acca, list) else [acca]
    if replace:
        await db.execute(
            text("DELETE FROM tracked_bets WHERE event_date = :d AND user_id IS NULL AND source_rule_key = 'system_acca'"),
            {"d": target_date.isoformat()},
        )
        await db.commit()

    existing_fps = set()
    rows = await db.scalars(
        select(TrackedBet.selection_name).where(
            TrackedBet.event_date == target_date,
            TrackedBet.source_rule_key == "system_acca",
            TrackedBet.user_id.is_(None),
        )
    )
    for sn in rows.all():
        if sn and sn.startswith("system_acca|"):
            existing_fps.add(sn.split("|", 1)[1])

    inserted = 0
    for ticket in tickets:
        legs = ticket.get("legs", [])
        if not legs:
            continue
        fp = _acca_fingerprint(legs)
        if fp in existing_fps:
            continue

        combined_odds = ticket.get("combined_odds", 1.0)
        n = len(legs)
        leg_labels = ", ".join(
            f"{leg.get('home_team')} vs {leg.get('away_team')} · {leg.get('market')} @ {float(leg.get('odd', 0)):.2f}"
            for leg in legs
        )
        kickoff_times = sorted(
            (leg.get("kickoff_at") for leg in legs if leg.get("kickoff_at")),
            key=lambda x: x,
        )
        first_kickoff = kickoff_times[0] if kickoff_times else None
        if isinstance(first_kickoff, str):
            try:
                first_kickoff = datetime.fromisoformat(first_kickoff)
            except (ValueError, TypeError):
                first_kickoff = None
        if first_kickoff and first_kickoff.tzinfo is None:
            first_kickoff = first_kickoff.replace(tzinfo=timezone.utc)

        bet = TrackedBet(
            source_rule_key="system_acca",
            source_rule_label="AI Acca",
            event_date=target_date,
            user_id=None,
            selection_name=f"system_acca|{fp}",
            market_type="Accumulator",
            match_name=f"AI Acca · {n} leg{'s' if n != 1 else ''}",
            notes=json.dumps({"legs": legs, "leg_summary": leg_labels, "combined_odds": combined_odds}),
            stake=50000.0,
            combined_odds=combined_odds,
            kickoff_at=first_kickoff,
        )
        try:
            db.add(bet)
            await db.commit()
            inserted += 1
            existing_fps.add(fp)
        except Exception:
            await db.rollback()
            logger.warning("auto_track_acca_legs: commit failed for %s", fp)

    return inserted


async def auto_track_advisor_picks(
    db: AsyncSession,
    advisor_outputs: list[tuple[str, dict]],
    advisor_defs: list[dict],
    rows: list,
    target_date: date,
) -> int:
    """Create zero-stake shadow TrackedBet rows for each advisor's top_picks.

    Idempotent: skips picks already present for this date.
    Returns number of new rows inserted.
    """
    from app.models.bet import TrackedBet

    sig_index: dict[str, Signal] = {}
    for sig, fix in rows:
        key = f"{_norm(fix.home_team)}|{_norm(fix.away_team)}|{_norm(sig.market)}"
        sig_index[key] = sig

    existing = await db.execute(
        select(TrackedBet.fixture_id, TrackedBet.market_type, TrackedBet.source_rule_key).where(
            TrackedBet.event_date == target_date,
            TrackedBet.user_id.is_(None),
            TrackedBet.source_rule_key.in_(_ALL_ADVISORY_KEYS),
        )
    )
    existing_set = {(r.fixture_id, r.market_type, r.source_rule_key) for r in existing.all()}

    inserted = 0
    for (model_label, result), advisor_def in zip(advisor_outputs, advisor_defs):
        rule_key = _ADVISOR_RULE_KEYS.get(advisor_def["name"])
        if not rule_key:
            continue
        for pick in result.get("top_picks", []):
            home = _norm(pick.get("home_team", ""))
            away = _norm(pick.get("away_team", ""))
            market_raw = pick.get("market", "").strip()
            key = f"{home}|{away}|{_norm(market_raw)}"
            sig = sig_index.get(key)
            if sig is None:
                logger.debug("auto_track_advisor_picks: no signal for %s vs %s (%s) — skipping", home, away, market_raw)
                continue

            fix_id = sig.fixture_id
            if (fix_id, market_raw, rule_key) in existing_set:
                continue

            league = getattr(sig, "league", "") or ""
            if league in DISABLED_LEAGUES:
                continue
            if market_raw.lower().startswith("over") and league in OVER_GOALS_SUPPRESSED_LEAGUES:
                continue

            odd = float(pick.get("odd", 0) or 0)
            if market_raw == "Over 1.5" and odd < 1.40:
                logger.debug(
                    "auto_track_advisor_picks: Over 1.5 @ %.2f below 1.40 floor — skip (%s vs %s)",
                    odd, home, away,
                )
                continue
            if market_raw == "Over 1.5" and getattr(sig, "dual_agreement", "") != "Both":
                logger.debug(
                    "auto_track_advisor_picks: Over 1.5 @ %.2f needs Both agreement, got %s — skip (%s vs %s)",
                    odd, sig.dual_agreement, home, away,
                )
                continue

            bet = TrackedBet(
                source_rule_key=rule_key,
                source_rule_label=advisor_def["role"],
                event_date=target_date,
                user_id=None,
                fixture_id=fix_id,
                market_type=market_raw,
                match_name=f"{pick.get('home_team', '')} vs {pick.get('away_team', '')}",
                stake=0.0,
                odd=odd or getattr(sig, "bayesian_best_odd", None),
                notes=json.dumps({
                    "reason": pick.get("reason", ""),
                    "advisor": advisor_def["role"],
                    "model": model_label,
                    "dual_confidence": sig.dual_confidence,
                }),
            )
            db.add(bet)
            existing_set.add((fix_id, market_raw, rule_key))
            inserted += 1

    try:
        await db.commit()
        logger.debug("auto_track_advisor_picks: %d pick rows for %s", inserted, target_date)
    except Exception as e:
        await db.rollback()
        logger.warning("auto_track_advisor_picks: commit failed for %s: %s", target_date, e)
    return inserted


# ── Leg result backfill ────────────────────────────────────────────────────────

async def _attach_leg_results(db: AsyncSession, legs: list[dict], target_date: date) -> None:
    """Mutate each leg in place with result, score, and kickoff_at."""
    from app.services.settlement import FINAL_STATUSES, VOID_STATUSES, _score_condition

    fixture_ids = [leg["fixture_id"] for leg in legs if leg.get("fixture_id")]
    if not fixture_ids:
        return

    fixtures = await db.scalars(select(Fixture).where(Fixture.id.in_(fixture_ids)))
    fix_map = {f.id: f for f in fixtures.all()}

    for leg in legs:
        fid = leg.get("fixture_id")
        fix = fix_map.get(fid) if fid else None
        if fix is None:
            leg.setdefault("result", "pending")
            leg.setdefault("score", None)
            continue

        leg.setdefault("kickoff_at", fix.kickoff_at.isoformat() if fix.kickoff_at else None)
        status = (fix.status or "").upper()
        if status in {s.upper() for s in FINAL_STATUSES}:
            hs, as_ = fix.home_score, fix.away_score
            leg["score"] = f"{hs}-{as_}" if hs is not None and as_ is not None else None
            market = leg.get("market", "")
            try:
                won = await db.scalar(_score_condition(market, fix))
                leg["result"] = "won" if won else "lost"
            except Exception:
                leg["result"] = "pending"
        elif status in {s.upper() for s in VOID_STATUSES}:
            leg["result"] = "void"
            leg["score"] = None
        else:
            leg["result"] = "pending"
            leg["score"] = None


# ── Advisory cache ─────────────────────────────────────────────────────────────

async def _get_advisory_cache(db: AsyncSession, target_date: date) -> dict | None:
    key = f"{_ADVISORY_CACHE_PREFIX}{target_date.isoformat()}"
    try:
        value = await db.scalar(text("SELECT value FROM system_settings WHERE key = :k"), {"k": key})
        if value:
            return json.loads(value)
    except Exception:
        pass
    return None


async def invalidate_advisory_cache(db: AsyncSession, target_date: date) -> None:
    """Drop the cached advisory payload for a date.

    Called by compute_signals_for_date: the cached acca pins leg odds from the
    signal rows it was built on, so once those rows are deleted/recomputed the
    cached payload is definitionally stale.
    """
    key = f"{_ADVISORY_CACHE_PREFIX}{target_date.isoformat()}"
    try:
        await db.execute(text("DELETE FROM system_settings WHERE key = :k"), {"k": key})
        await db.commit()
    except Exception as e:
        logger.warning("Failed to invalidate advisory cache for %s: %s", target_date, e)


async def _set_advisory_cache(db: AsyncSession, target_date: date, data: dict) -> None:
    key = f"{_ADVISORY_CACHE_PREFIX}{target_date.isoformat()}"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        text("""
        INSERT INTO system_settings (key, value, updated_at) VALUES (:k, :v, :t)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
    """),
        {"k": key, "v": json.dumps(data), "t": ts},
    )
    await db.commit()


# ── Main orchestration ─────────────────────────────────────────────────────────

async def get_advisor_insights(
    db: AsyncSession,
    target_date: date,
    fixture_ids: list[int] | None = None,
    current_user: Any | None = None,
    force: bool = False,
) -> dict:
    """Orchestrate the AI advisory council for a given date.

    1. Load up to 12 High/Medium signals for the date.
    2. Fetch match info for up to 8 fixtures.
    3. Build a compact context string.
    4. Fire all four advisors concurrently — each runs its own provider chain.
    5. Return structured insights + metadata.
    """
    s = get_settings()
    uid = getattr(current_user, "id", None)

    # ── Cache check ────────────────────────────────────────────────────────────
    if not force:
        cached = await _get_advisory_cache(db, target_date)
        if cached:
            acca = cached.get("acca_builder", {})
            tickets = acca.get("tickets", [acca] if acca.get("legs") else [])
            for ticket in tickets:
                legs = ticket.get("legs", [])
                if legs:
                    try:
                        fp = _acca_fingerprint(legs)
                        cached["acca_tracked"] = await _is_acca_tracked(db, target_date, uid, fp) if uid else False
                    except Exception as e:
                        logger.warning("_is_acca_tracked (cache hit) failed: %s", e)
                        cached["acca_tracked"] = False
                    try:
                        await _attach_leg_results(db, legs, target_date)
                    except Exception as e:
                        logger.warning("_attach_leg_results (cache hit) failed: %s", e)
                    break
            cached["from_cache"] = True
            return cached

    # ── Provider check ─────────────────────────────────────────────────────────
    if not any([s.Qwantej_claude_key, s.gemini_api_key, s.cerebras_api_key, s.groq_api_key, s.mistral_api_key]):
        return {
            "error": "no_provider",
            "summary": (
                "AI advisors are disabled — no provider keys configured.\n"
                "Add at least one to backend/.env:\n"
                "  Qwantej_CLAUDE_KEY=sk-ant-...      (console.anthropic.com)\n"
                "  GEMINI_API_KEY=AIza...           (aistudio.google.com/apikey — free)\n"
                "  CEREBRAS_API_KEY=csk-...         (inference.cerebras.ai — free)\n"
                "  GROQ_API_KEY=gsk-...             (console.groq.com — free)\n"
                "  MISTRAL_API_KEY=...              (console.mistral.ai — free)"
            ),
        }

    # ── Load signals ───────────────────────────────────────────────────────────
    q = (
        select(Signal, Fixture)
        .join(Fixture, Signal.fixture_id == Fixture.id)
        .where(
            Signal.event_date == target_date,
            Signal.is_candidate.is_(True),
            Signal.dual_confidence.in_(["High", "Medium"]),
            Signal.dual_agreement.in_(["Both", "Bayesian Only", "Poisson Only"]),
        )
        .order_by(Signal.dual_quality_score.desc().nullslast())
        .limit(12)
    )
    if fixture_ids:
        q = q.where(Signal.fixture_id.in_(fixture_ids))

    result = await db.execute(q)
    rows = result.all()

    if not rows:
        return {"error": "no_signals", "summary": f"No qualifying signals found for {target_date}."}

    # ── Match info ─────────────────────────────────────────────────────────────
    from app.services import match_info as mi_svc
    match_infos = {}
    for sig, fix in rows[:8]:
        try:
            match_infos[fix.id] = await mi_svc.get_match_info(db, fix.id)
        except Exception:
            match_infos[fix.id] = {}

    # ── Context ────────────────────────────────────────────────────────────────
    try:
        perf_weights = await compute_performance_weights(db)
    except Exception:
        perf_weights = None
    context = _build_context(list(rows), match_infos, perf_weights)
    skeptic_extras = _build_skeptic_extras(list(rows))

    # ── Fire advisors concurrently ─────────────────────────────────────────────
    tasks = []
    for advisor_def in _ADVISORS:
        extra = skeptic_extras if advisor_def["name"] == "skeptic" else ""
        tasks.append(_call_advisor(advisor_def, context, extra))

    advisor_outputs = await asyncio.gather(*tasks, return_exceptions=False)

    # ── Build response ─────────────────────────────────────────────────────────
    response: dict[str, Any] = {"date": target_date.isoformat(), "from_cache": False}
    has_errors = False

    for (model_label, result_dict), advisor_def in zip(advisor_outputs, _ADVISORS):
        name = advisor_def["name"]
        entry = {**result_dict, "model": model_label, "role": advisor_def["role"], "emoji": advisor_def["emoji"]}
        response[name] = entry
        if "error" in result_dict:
            has_errors = True

    # Attach leg results and acca tracking state
    acca_data = response.get("acca_builder", {})
    tickets = acca_data.get("tickets", [acca_data] if acca_data.get("legs") else [])
    for ticket in tickets:
        legs = ticket.get("legs", [])
        if legs:
            try:
                await _attach_leg_results(db, legs, target_date)
            except Exception:
                pass
            break

    response["acca_tracked"] = False
    if uid and tickets:
        for ticket in tickets:
            legs = ticket.get("legs", [])
            if legs:
                try:
                    fp = _acca_fingerprint(legs)
                    response["acca_tracked"] = await _is_acca_tracked(db, target_date, uid, fp)
                except Exception as e:
                    logger.warning("_is_acca_tracked failed: %s", e)
                break

    # ── Cache and track ────────────────────────────────────────────────────────
    if not has_errors:
        try:
            await _set_advisory_cache(db, target_date, response)
        except Exception as e:
            logger.warning("Failed to write advisory cache: %s", e)

        try:
            await auto_track_advisor_picks(db, list(advisor_outputs), _ADVISORS[1:], list(rows), target_date)
        except Exception as e:
            logger.warning("auto_track_advisor_picks failed for %s — continuing: %s", target_date, e)

        acca_all = response.get("acca_builder", {})
        acca_tickets = acca_all.get("tickets", [acca_all] if acca_all.get("legs") else [])
        if acca_tickets:
            try:
                await auto_track_acca_legs(db, acca_tickets, target_date)
            except Exception as e:
                logger.warning("auto_track_acca_legs failed for %s — continuing: %s", target_date, e)
    else:
        logger.info("Advisory result not cached — advisor/acca errors present; next request retries live")

    return response


# ── Chat helper ────────────────────────────────────────────────────────────────

async def chat_with_advisor(question: str, history: list[dict]) -> str:
    """Single-turn conversational response for the pro chat interface."""
    s = get_settings()
    system = (
        "You are Qwantej's AI football betting assistant. You help pro subscribers understand "
        "today's signals, evaluate picks, and think through betting decisions. Be concise "
        "(2-4 sentences unless detail is genuinely needed), analytical, and honest about "
        "uncertainty. You know the system uses Bayesian + Poisson + Elo ensemble models."
    )
    messages = [*history, {"role": "user", "content": question}]

    # Try providers in order
    PROVIDER_CHAIN = [
        ("claude",   s.Qwantej_claude_key),
        ("gemini",   s.gemini_api_key),
        ("cerebras", s.cerebras_api_key),
        ("groq",     s.groq_api_key),
        ("mistral",  s.mistral_api_key),
    ]
    for provider, key in PROVIDER_CHAIN:
        if not key:
            continue
        try:
            if provider == "claude":
                client = anthropic.AsyncAnthropic(api_key=key)
                resp = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=512,
                    system=system,
                    messages=messages,
                )
                return next((b.text for b in resp.content if b.type == "text"), "")
            elif provider == "gemini":
                url = GEMINI_URL.format(model="gemini-2.0-flash")
                payload = {
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 512},
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.post(url, json=payload, params={"key": key})
                    r.raise_for_status()
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                models_map = {"cerebras": "llama3.3-70b", "groq": "llama-3.1-8b-instant", "mistral": "open-mistral-nemo"}
                urls_map = {"cerebras": CEREBRAS_URL, "groq": GROQ_URL, "mistral": MISTRAL_URL}
                payload = {
                    "model": models_map[provider],
                    "messages": [{"role": "system", "content": system}, *messages],
                    "temperature": 0.4,
                    "max_tokens": 512,
                }
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.post(urls_map[provider], json=payload, headers=headers)
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("chat_with_advisor: %s failed — %s", provider, e)
            continue

    return "All AI providers are currently unavailable. Please try again shortly."
