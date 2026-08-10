"""
telegram.py — Telegram Bot integration for Qwantej signal alerts.

Phase 1 edition: consumes ForecastSnapshot rows (ensemble engine) instead of
the retired Signal model. All public functions the scheduler calls are preserved
with the same signature.

Setup
-----
1. Create a bot via @BotFather → copy the token.
2. Add the bot to each group as admin ("Post Messages" rights).
3. Set in backend/.env:

   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_FREE_CHAT_ID=<chat id>
   TELEGRAM_PRO_CHAT_ID=<chat id>
"""
from __future__ import annotations

import html
import logging
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.fixture import Fixture
from app.models.forecast_snapshot import ForecastSnapshot

logger   = logging.getLogger("Qwantej.telegram")
settings = get_settings()

TELEGRAM_API = "https://api.telegram.org"
_MAX_CHARS   = 4000   # Telegram limit is 4096; leave buffer


# ── Formatting helpers ────────────────────────────────────────────────────────

_MARKET_LABELS: dict[str, str] = {
    "Over 0.5":  "Over 0.5 Goals",
    "Over 1.5":  "Over 1.5 Goals",
    "Over 2.5":  "Over 2.5 Goals",
    "Over 3.5":  "Over 3.5 Goals",
    "Over 4.5":  "Over 4.5 Goals",
    "Under 1.5": "Under 1.5 Goals",
    "Under 2.5": "Under 2.5 Goals",
    "Under 3.5": "Under 3.5 Goals",
    "Under 4.5": "Under 4.5 Goals",
    "Home Over 0.5":  "Home Team Over 0.5 Goals",
    "Home Over 1.5":  "Home Team Over 1.5 Goals",
    "Home Under 0.5": "Home Team Under 0.5 Goals",
    "Home Under 1.5": "Home Team Under 1.5 Goals",
    "Away Over 0.5":  "Away Team Over 0.5 Goals",
    "Away Over 1.5":  "Away Team Over 1.5 Goals",
    "Away Under 0.5": "Away Team Under 0.5 Goals",
    "Away Under 1.5": "Away Team Under 1.5 Goals",
    "BTTS Yes": "Both Teams to Score",
    "BTTS No":  "Both Teams NOT to Score",
    "Home Win": "Home Win",
    "Draw":     "Draw",
    "Away Win": "Away Win",
    "1X (Home or Draw)": "Home Win or Draw",
    "X2 (Draw or Away)": "Draw or Away Win",
    "12 (Home or Away)": "Either Team Wins (No Draw)",
    "Home Win to Nil": "Home Win to Nil",
    "Away Win to Nil": "Away Win to Nil",
    "Exactly 1 Goal":  "Exactly 1 Goal",
    "Exactly 2 Goals": "Exactly 2 Goals",
    "Exactly 3 Goals": "Exactly 3 Goals",
}


def _verbose_market(market: str | None) -> str:
    m = (market or "").strip()
    return _MARKET_LABELS.get(m, m)


def _esc(t: str | None) -> str:
    return html.escape(str(t or ""))


def _pct(prob: float | None) -> str:
    return f"{prob * 100:.0f}%" if prob is not None else "?"


def _odds(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "?"


_CAT_OFFSET = timedelta(hours=2)
_CAT_LABEL  = "CAT"


def _ko_aware(kickoff_at: Any) -> datetime | None:
    if kickoff_at is None:
        return None
    if getattr(kickoff_at, "tzinfo", None) is None:
        return kickoff_at.replace(tzinfo=timezone.utc)
    return kickoff_at


def _kickoff_str_cat(kickoff_at: Any) -> str:
    ko = _ko_aware(kickoff_at)
    if ko is None:
        return ""
    return (ko + _CAT_OFFSET).strftime("%H:%M ") + _CAT_LABEL


def _kickoff_label_cat(kickoff_at: Any, now_utc: datetime) -> str:
    ko = _ko_aware(kickoff_at)
    if ko is None:
        return ""
    ko_cat  = ko + _CAT_OFFSET
    now_cat = now_utc + _CAT_OFFSET
    day_diff = (ko_cat.date() - now_cat.date()).days
    prefix = "Today " if day_diff == 0 else "Tomorrow " if day_diff == 1 else ko_cat.strftime("%a ")
    return prefix + ko_cat.strftime("%H:%M ") + _CAT_LABEL


def _result_emoji(outcome: str | None) -> str:
    return {"WIN": "✅", "LOSS": "❌", "VOID": "⚪", "PUSH": "⚪"}.get(outcome or "", "⏳")


def _score_str(fix: Fixture) -> str:
    status = (fix.status or "").strip().upper()
    _VOID = frozenset({"CANC", "ABD", "AWD", "WO", "TBD", "PST", "INT", "SUSP"})
    if status in _VOID:
        return status
    if fix.home_score is not None and fix.away_score is not None:
        return f"{fix.home_score}-{fix.away_score}"
    return "?"


# ── Forecast-based ranking and formatting ─────────────────────────────────────

def _system_rank_snap(snap: ForecastSnapshot) -> tuple:
    """Priority tuple for sorting SIGNAL rows (highest first)."""
    prob = snap.calibrated_prob if snap.calibrated_prob is not None else snap.ensemble_prob
    conf_rank = {"High": 3, "Medium": 2, "Low": 1}.get(snap.confidence or "", 0)
    return (
        conf_rank,
        1 if prob >= 0.70 else 0,
        round(prob, 6),
        round(snap.value_edge or 0.0, 6),
    )


def _best_per_fixture(
    rows: list[tuple[ForecastSnapshot, Fixture]],
) -> list[tuple[ForecastSnapshot, Fixture]]:
    """Keep the highest-ranked snapshot per fixture_id."""
    best: dict[int, tuple[ForecastSnapshot, Fixture]] = {}
    for snap, fix in rows:
        fid = snap.fixture_id
        if fid is None:
            continue
        cur = best.get(fid)
        if cur is None or _system_rank_snap(snap) > _system_rank_snap(cur[0]):
            best[fid] = (snap, fix)
    return list(best.values())


def _pick_line(snap: ForecastSnapshot) -> str:
    """Format one pick line for a Telegram message."""
    market_label = _esc(_verbose_market(snap.market))
    conf_icon    = {"High": "🔥", "Medium": "📊", "Low": "📉"}.get(snap.confidence or "", "•")
    prob         = snap.calibrated_prob if snap.calibrated_prob is not None else snap.ensemble_prob
    odds_part    = f" @ {snap.market_odds:.2f}" if snap.market_odds else ""
    edge_part    = f" · edge {snap.value_edge * 100:+.1f}%" if snap.value_edge is not None else ""
    return f"📌 {market_label} · {_pct(prob)}{odds_part}{edge_part} {conf_icon}"


# ── Data access ───────────────────────────────────────────────────────────────

async def _query_forecasts_for_date(
    db: AsyncSession,
    run_date: date,
) -> list[tuple[ForecastSnapshot, Fixture]]:
    """
    Return (ForecastSnapshot, Fixture) pairs for live fixtures on run_date
    that have signal_type='SIGNAL'. Uses the latest snapshot per
    (fixture_id, market) so we don't get duplicates when multiple horizons ran.
    """
    latest_sq = (
        select(
            ForecastSnapshot.fixture_id,
            ForecastSnapshot.market,
            func.max(ForecastSnapshot.snapshot_at).label("max_snap"),
        )
        .where(ForecastSnapshot.fixture_id.isnot(None))
        .group_by(ForecastSnapshot.fixture_id, ForecastSnapshot.market)
        .subquery()
    )

    stmt = (
        select(ForecastSnapshot, Fixture)
        .join(
            latest_sq,
            and_(
                ForecastSnapshot.fixture_id == latest_sq.c.fixture_id,
                ForecastSnapshot.market     == latest_sq.c.market,
                ForecastSnapshot.snapshot_at == latest_sq.c.max_snap,
            ),
        )
        .join(Fixture, Fixture.id == ForecastSnapshot.fixture_id)
        .where(
            Fixture.event_date == run_date,
            ForecastSnapshot.signal_type == "SIGNAL",
        )
    )
    result = await db.execute(stmt)
    return list(result.all())


def _build_acca(
    rows: list[tuple[ForecastSnapshot, Fixture]],
    min_legs: int = 3,
    max_legs: int = 5,
) -> dict | None:
    """
    Build a simple accumulator from the top-ranked picks that have market odds.
    Returns None if fewer than min_legs qualifying picks exist.
    """
    with_odds = [
        (snap, fix) for snap, fix in rows
        if snap.market_odds and snap.market_odds > 1.01
    ]
    if len(with_odds) < min_legs:
        return None

    ranked = sorted(with_odds, key=lambda r: _system_rank_snap(r[0]), reverse=True)[:max_legs]
    combined = 1.0
    for snap, _ in ranked:
        combined *= snap.market_odds  # type: ignore[operator]

    legs = [
        {
            "home_team": fix.home_team,
            "away_team": fix.away_team,
            "market":    snap.market,
            "odd":       snap.market_odds,
        }
        for snap, fix in ranked
    ]
    return {"legs": legs, "combined_odds": f"{combined:.2f}"}


# ── Channel config ────────────────────────────────────────────────────────────

def _configured_Qwantej_channels() -> list[tuple[str, str]]:
    channels: list[tuple[str, str]] = []
    if settings.telegram_free_chat_id:
        channels.append((settings.telegram_free_chat_id, "free"))
    if settings.telegram_pro_chat_id:
        channels.append((settings.telegram_pro_chat_id, "pro"))
    return channels


# ── Transport ─────────────────────────────────────────────────────────────────

async def _send_to(chat_id: str, text: str) -> bool:
    token = settings.telegram_bot_token
    if not token or not chat_id:
        return False
    url     = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning("Telegram HTTP %s for chat %s: %s",
                           exc.response.status_code, chat_id, exc.response.text[:200])
        except Exception as exc:
            logger.warning("Telegram send to %s failed: %s", chat_id, exc)
    return False


def _split_message(text: str, limit: int = _MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        needed = len(para) + (2 if current else 0)
        if current and current_len + needed > limit:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += needed
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text[:limit]]


# ── Push log helpers ──────────────────────────────────────────────────────────

async def _check_push_sent(db: AsyncSession, push_date: date, channel_type: str, push_type: str) -> bool:
    row = await db.execute(
        text(
            "SELECT 1 FROM telegram_push_log "
            "WHERE push_date = :d AND channel_type = :ct AND push_type = :pt LIMIT 1"
        ),
        {"d": push_date.isoformat(), "ct": channel_type, "pt": push_type},
    )
    return row.scalar() is not None


async def _log_push_sent(db: AsyncSession, push_date: date, channel_type: str, push_type: str) -> None:
    await db.execute(
        text(
            "INSERT OR IGNORE INTO telegram_push_log (push_date, channel_type, push_type) "
            "VALUES (:d, :ct, :pt)"
        ),
        {"d": push_date.isoformat(), "ct": channel_type, "pt": push_type},
    )
    await db.commit()


# ── Free-channel teaser config ────────────────────────────────────────────────

FREE_REVEAL_COUNT = 2
_FREE_HIDDEN_MATCH = "▒▒▒▒▒ vs ▒▒▒▒▒"
FREE_UPGRADE_CTA = (
    "\n<i>🔒 Some matches are hidden — upgrade to Pro to see every pick "
    "instantly, in full, with no restrictions.</i>"
)


def _pick_reveal_fixture_ids(rows: list[tuple[ForecastSnapshot, Fixture]], count: int) -> set[int]:
    if count <= 0 or not rows:
        return set()
    pool = [r for r in rows if r[0].confidence != "High"]
    if len(pool) < count:
        pool = list(rows)
    count = min(count, len(pool))
    return {fix.id for _s, fix in random.sample(pool, count)}


# ── Message builders ──────────────────────────────────────────────────────────

def build_signal_digest(
    rows: list[tuple[ForecastSnapshot, Fixture]],
    channel_type: str = "pro",
    now: datetime | None = None,
    reveal_fixture_ids: set[int] | None = None,
    acca: dict | None = None,
) -> str:
    """Tonight & overnight digest (used by morning + evening confirms)."""
    is_free = channel_type == "free"
    reveal_fixture_ids = reveal_fixture_ids or set()
    now   = now or datetime.now(tz=timezone.utc)
    title = "Qwantej Free — Tonight &amp; Overnight" if is_free else "Qwantej Pro — Tonight &amp; Overnight"

    parts = [
        f"🌙 <b>{title}</b>",
        f"<i>Tonight &amp; after-midnight kickoffs · {len(rows)} picks · times in CAT</i>",
    ]

    for i, (snap, fix) in enumerate(rows, 1):
        ko = _kickoff_label_cat(fix.kickoff_at, now)
        league_line = f"{_esc(fix.country)} · {_esc(fix.league)}" if fix.country else _esc(fix.league or "")
        match_name = (
            _FREE_HIDDEN_MATCH
            if is_free and fix.id not in reveal_fixture_ids
            else f"{_esc(fix.home_team)} vs {_esc(fix.away_team)}"
        )
        parts.append(
            f"\n<b>{i}. {match_name}</b>{(' · ' + ko) if ko else ''}\n"
            f"   🏆 {league_line}\n"
            f"   {_pick_line(snap)}"
        )

    _append_acca(parts, acca, is_free)
    if is_free:
        parts.append(FREE_UPGRADE_CTA)
    parts.append(f"\n<a href=\"{settings.app_url}\">{settings.app_url}</a>")
    return "\n".join(parts)


def build_tomorrow_message(
    rows: list[tuple[ForecastSnapshot, Fixture]],
    run_date: date,
    acca: dict | None,
    channel_type: str = "pro",
    reveal_fixture_ids: set[int] | None = None,
) -> str:
    """Tomorrow's full single-match slate + ACCA."""
    is_free = channel_type == "free"
    reveal_fixture_ids = reveal_fixture_ids or set()
    title = "Qwantej Free" if is_free else "Qwantej Pro"
    date_label = run_date.strftime("%a %d %b %Y")
    subtitle = (
        f"Full slate for tomorrow · {len(rows)} pick{'s' if len(rows) != 1 else ''} · place your bets tonight"
        if rows else "AI Acca of the Day · place your bets tonight"
    )
    parts = [
        f"🌅 <b>{title} — Tomorrow, {date_label}</b>",
        f"<i>{subtitle}</i>",
    ]
    for i, (snap, fix) in enumerate(rows, 1):
        ko = _kickoff_str_cat(fix.kickoff_at)
        league_line = f"{_esc(fix.country)} · {_esc(fix.league)}" if fix.country else _esc(fix.league or "")
        match_name = (
            _FREE_HIDDEN_MATCH
            if is_free and fix.id not in reveal_fixture_ids
            else f"{_esc(fix.home_team)} vs {_esc(fix.away_team)}"
        )
        parts.append(
            f"\n<b>{i}. {match_name}</b>{(' · ' + ko) if ko else ''}\n"
            f"   🏆 {league_line}\n"
            f"   {_pick_line(snap)}"
        )

    _append_acca(parts, acca, is_free)
    if is_free:
        parts.append(FREE_UPGRADE_CTA)
    parts.append(f"\n<a href=\"{settings.app_url}\">{settings.app_url}</a>")
    return "\n".join(parts)


def build_results_message(
    rows: list[tuple[ForecastSnapshot, Fixture]],
    run_date: date,
) -> str:
    """Results digest — reads outcome directly from ForecastSnapshot."""
    date_label = run_date.strftime("%a %d %b %Y")
    won  = sum(1 for s, _ in rows if s.outcome == "WIN")
    lost = sum(1 for s, _ in rows if s.outcome == "LOSS")
    void_ = sum(1 for s, _ in rows if s.outcome in ("VOID", "PUSH"))
    total = len(rows)
    hit_rate = round(won / (won + lost) * 100) if (won + lost) > 0 else 0

    parts = [
        "📊 <b>Qwantej — Results</b>",
        f"<i>{date_label} · {total} picks · Hit rate: {hit_rate}%</i>",
    ]

    buckets: dict[str, list[tuple[ForecastSnapshot, Fixture]]] = {"High": [], "Medium": [], "Low": []}
    for snap, fix in rows:
        bucket = snap.confidence if snap.confidence in buckets else "Low"
        buckets[bucket].append((snap, fix))

    _CONF_HEADER = {
        "High":   "🔥 <b>HIGH CONFIDENCE</b>",
        "Medium": "📊 <b>MEDIUM CONFIDENCE</b>",
        "Low":    "📉 <b>LOW CONFIDENCE</b>",
    }
    idx = 1
    for conf in ("High", "Medium", "Low"):
        if not buckets[conf]:
            continue
        parts.append("")
        parts.append(_CONF_HEADER[conf])
        for snap, fix in buckets[conf]:
            score    = _score_str(fix)
            r_emoji  = _result_emoji(snap.outcome)
            ko       = _kickoff_str_cat(fix.kickoff_at)
            league_line = f"{_esc(fix.country)} · {_esc(fix.league)}" if fix.country else _esc(fix.league or "")
            parts.append(
                f"\n{r_emoji} <b>{idx}. {_esc(fix.home_team)} vs {_esc(fix.away_team)}</b> ({score})"
                f"{(' · ' + ko) if ko else ''}\n"
                f"   🏆 {league_line}\n"
                f"   {_pick_line(snap)}"
            )
            idx += 1

    summary_pieces = [f"{won} Won", f"{lost} Lost"]
    if void_:
        summary_pieces.append(f"{void_} Void")
    if (won + lost) > 0:
        summary_pieces.append(f"Hit rate: {hit_rate}%")
    parts.append("")
    parts.append(f"📈 <b>Summary: {' · '.join(summary_pieces)}</b>")
    parts.append(f"\n<a href=\"{settings.app_url}\">{settings.app_url}</a>")
    return "\n".join(parts)


def _append_acca(parts: list[str], acca: dict | None, is_free: bool) -> None:
    """Append the ACCA section to a message parts list (mutates in-place)."""
    legs          = (acca or {}).get("legs") or []
    combined_odds = (acca or {}).get("combined_odds")
    if not legs or not combined_odds:
        return
    parts.append("\n" + "─" * 24)
    parts.append(f"\n🎟️ <b>AI Acca of the Day</b> — combined @ {combined_odds}")
    for i, leg in enumerate(legs, 1):
        match = (
            _FREE_HIDDEN_MATCH if is_free
            else (
                f"{_esc(leg.get('home_team'))} vs {_esc(leg.get('away_team'))}"
                if leg.get("home_team") and leg.get("away_team") else "—"
            )
        )
        odd = leg.get("odd")
        odd_str = f"{float(odd):.2f}" if odd is not None else "?"
        parts.append(f"\n   {i}. <b>{match}</b> — {_esc(leg.get('market'))} @ {odd_str}")


# ── Main push functions ───────────────────────────────────────────────────────

async def push_tomorrow_digest(db: AsyncSession, run_date: date | None = None) -> int:
    """
    Broadcast tomorrow's full signal slate + ACCA to Free and Pro.
    Called at 19:00 UTC after the evening ensemble run. Idempotent via
    telegram_push_log. Returns the number of channels sent to.
    """
    if not settings.telegram_bot_token:
        return 0
    targets = [(cid, ct) for cid, ct in _configured_Qwantej_channels() if ct in ("free", "pro")]
    if not targets:
        return 0

    run_date = run_date or (date.today() + timedelta(days=1))

    rows = await _query_forecasts_for_date(db, run_date)
    deduped = _best_per_fixture(rows)

    if not deduped:
        logger.info("Tomorrow digest: no SIGNAL rows for %s — sending no-picks notification", run_date)
        return await push_no_picks_notification(db, run_date, is_tomorrow=True)

    chronological = sorted(deduped, key=lambda r: _ko_aware(r[1].kickoff_at) or datetime.max.replace(tzinfo=timezone.utc))
    acca          = _build_acca(chronological)
    reveal_ids    = _pick_reveal_fixture_ids(chronological, FREE_REVEAL_COUNT)

    sent = 0
    for chat_id, channel_type in targets:
        if await _check_push_sent(db, run_date, channel_type, "tomorrow"):
            logger.info("Tomorrow digest: already sent for %s/%s — skipping", run_date, channel_type)
            continue
        text_msg = build_tomorrow_message(
            chronological, run_date, acca,
            channel_type=channel_type,
            reveal_fixture_ids=reveal_ids if channel_type == "free" else None,
        )
        ok = False
        for chunk in _split_message(text_msg):
            ok = await _send_to(chat_id, chunk)
        if ok:
            await _log_push_sent(db, run_date, channel_type, "tomorrow")
            sent += 1

    if sent:
        logger.info("Tomorrow digest sent to %d channel(s) — %d picks for %s, acca=%s",
                    sent, len(chronological), run_date, "yes" if acca else "no")
    return sent


async def push_morning_digest(db: AsyncSession, free_reveal_count: int = FREE_REVEAL_COUNT) -> int:
    """
    Broadcast today's signal list at 04:00 UTC (06:00 CAT).
    Confirmation mode if last night's evening digest already ran for today.
    Returns the number of channels sent to.
    """
    if not settings.telegram_bot_token:
        return 0
    targets = _configured_Qwantej_channels()
    if not targets:
        return 0

    today = date.today()
    now   = datetime.now(tz=timezone.utc)

    rows    = await _query_forecasts_for_date(db, today)
    deduped = _best_per_fixture(rows)

    if not deduped:
        logger.info("Morning digest: no SIGNAL rows for %s — sending no-picks notification", today)
        return await push_no_picks_notification(db, today, is_tomorrow=False)

    by_rank    = sorted(deduped, key=lambda r: _system_rank_snap(r[0]), reverse=True)
    acca       = _build_acca(by_rank)
    reveal_ids = _pick_reveal_fixture_ids(by_rank, free_reveal_count)

    # Was last night's evening digest already sent for today?
    evening_sent = any(
        await _check_push_sent(db, today, ct, "tomorrow")
        for _, ct in targets
    )
    push_type = "morning_confirm" if evening_sent else "morning"
    date_label = today.strftime("%a %d %b %Y")

    sent = 0
    for chat_id, channel_type in targets:
        if await _check_push_sent(db, today, channel_type, push_type):
            logger.info("Morning digest: already sent (%s) for %s/%s — skipping", push_type, today, channel_type)
            continue

        if channel_type == "free":
            text_msg = build_signal_digest(by_rank, channel_type="free", now=now,
                                           reveal_fixture_ids=reveal_ids, acca=acca)
        else:
            text_msg = build_signal_digest(by_rank, channel_type=channel_type, now=now, acca=acca)

        if evening_sent:
            title_key = "Qwantej Free" if channel_type == "free" else "Qwantej Pro"
            text_msg = text_msg.replace(
                f"🌙 <b>{title_key} — Tonight &amp; Overnight</b>",
                f"✅ <b>{title_key} — Today's Picks Confirmed · {date_label}</b>",
            ).replace(
                "Tonight &amp; after-midnight kickoffs",
                "Refreshed after morning odds update",
            )
        else:
            text_msg = text_msg.replace("Tonight &amp; Overnight", "Today's Picks")
            text_msg = text_msg.replace("Tonight &amp; after-midnight kickoffs", "Today's signal picks")

        ok = False
        for chunk in _split_message(text_msg):
            ok = await _send_to(chat_id, chunk)
        if ok:
            await _log_push_sent(db, today, channel_type, push_type)
            sent += 1

    mode = "confirmation" if evening_sent else "digest"
    if sent:
        logger.info("Morning %s sent to %d channel(s) — %d picks for %s", mode, sent, len(by_rank), today)
    return sent


async def push_results_report(
    db: AsyncSession,
    run_date: date,
    force: bool = False,
) -> bool:
    """
    Send a results digest for run_date. Fires only when all fixtures are in a
    terminal state. Idempotent via telegram_push_log. Returns True if sent.
    """
    if not settings.telegram_bot_token:
        return False
    channels = _configured_Qwantej_channels()
    if not channels:
        return False

    rows    = await _query_forecasts_for_date(db, run_date)
    deduped = _best_per_fixture(rows)
    if not deduped:
        return False

    _FINAL  = frozenset({"FT", "AET", "PEN"})
    _VOID   = frozenset({"CANC", "ABD", "AWD", "WO", "TBD", "PST", "INT", "SUSP"})
    pending = [fix for _, fix in deduped if (fix.status or "").upper() not in (_FINAL | _VOID)]
    if pending and not force:
        logger.debug("Results report: %d fixture(s) still pending for %s — skipping", len(pending), run_date)
        return False

    ranked = sorted(deduped, key=lambda r: _system_rank_snap(r[0]), reverse=True)
    any_sent = False
    for chat_id, channel_type in channels:
        if not force and await _check_push_sent(db, run_date, channel_type, "results"):
            continue
        msg    = build_results_message(ranked, run_date)
        chunks = _split_message(msg)
        ok     = False
        for chunk in chunks:
            try:
                ok = await _send_to(chat_id, chunk)
            except Exception as exc:
                logger.warning("Results report [%s] send failed: %s", channel_type, exc)
        if ok:
            await _log_push_sent(db, run_date, channel_type, "results")
            any_sent = True

    return any_sent


async def check_and_push_pending_results(db: AsyncSession) -> int:
    """Sweep the last 3 days and push results for any fully settled date."""
    pushed = 0
    today  = date.today()
    for delta in range(3):
        target = today - timedelta(days=delta)
        try:
            sent = await push_results_report(db, target)
            if sent:
                pushed += 1
        except Exception:
            logger.exception("check_and_push_pending_results: error for %s", target)
    return pushed


# ── Kickoff alerts ────────────────────────────────────────────────────────────

_alerted_fixture_ids: set[int] = set()


async def push_kickoff_alerts(db: AsyncSession) -> int:
    """
    Send pre-kickoff alerts for High-confidence signals kicking off in the next
    90 minutes that haven't been alerted yet this session.
    """
    if not settings.telegram_bot_token:
        return 0
    targets = _configured_Qwantej_channels()
    if not targets:
        return 0

    now        = datetime.now(tz=timezone.utc)
    window_end = now + timedelta(minutes=90)
    today      = now.date()

    rows    = await _query_forecasts_for_date(db, today)
    deduped = _best_per_fixture(rows)

    upcoming = [
        (snap, fix) for snap, fix in deduped
        if fix.id not in _alerted_fixture_ids
        and snap.confidence == "High"
        and (ko := _ko_aware(fix.kickoff_at)) is not None
        and now <= ko <= window_end
    ]
    if not upcoming:
        return 0

    upcoming.sort(key=lambda r: _system_rank_snap(r[0]), reverse=True)

    parts = ["⏰ <b>KICKING OFF SOON — Top Picks</b>\n<i>High confidence picks</i>"]
    for snap, fix in upcoming:
        ko_str      = _kickoff_str_cat(fix.kickoff_at)
        league_line = f"{_esc(fix.country)} · {_esc(fix.league)}" if fix.country else _esc(fix.league or "")
        parts.append(
            f"\n🔥 <b>{_esc(fix.home_team)} vs {_esc(fix.away_team)}</b>{(' · ' + ko_str) if ko_str else ''}\n"
            f"   🏆 {league_line}\n"
            f"   {_pick_line(snap)}"
        )
    parts.append(f"\n<a href=\"{settings.app_url}\">{settings.app_url}</a>")
    text = "\n".join(parts)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS - 50] + "\n... (truncated)"

    sent = 0
    for chat_id, channel_type in targets:
        try:
            ok = await _send_to(chat_id, text)
        except Exception as exc:
            logger.warning("Kickoff alert [%s] send failed: %s", channel_type, exc)
            ok = False
        if ok:
            sent += 1

    if sent:
        newly = {fix.id for _, fix in upcoming}
        _alerted_fixture_ids.update(newly)
        logger.info("Kickoff alerts sent to %d channel(s) for %d fixture(s)", sent, len(upcoming))

    return sent


# ── Value band alert (stub — Hybrid B concept, no-op in Phase 1) ─────────────

async def push_value_band_alert(
    db: AsyncSession,
    run_date: date | None = None,
    *,
    force: bool = False,
) -> int:
    """No-op stub kept for scheduler compatibility. Was Hybrid B specific."""
    return 0


# ── No-picks notification ─────────────────────────────────────────────────────

async def push_no_picks_notification(
    db: AsyncSession,
    target_date: date,
    *,
    is_tomorrow: bool = False,
) -> int:
    if not settings.telegram_bot_token:
        return 0
    targets = _configured_Qwantej_channels()
    if not targets:
        return 0

    date_label = target_date.strftime("%a %d %b %Y")
    if is_tomorrow:
        title  = f"Tomorrow · {date_label}"
        detail = "Light fixture calendar for tomorrow — no ensemble signals qualified. The model only signals when the edge is clear."
    else:
        title  = f"Today · {date_label}"
        detail = "No qualifying signals today — skipping beats losing."

    msg = f"📭 <b>Qwantej — No Picks: {title}</b>\n<i>{_esc(detail)}</i>"

    sent = 0
    for chat_id, channel_type in targets:
        if await _check_push_sent(db, target_date, channel_type, "no_picks"):
            continue
        ok = await _send_to(chat_id, msg)
        if ok:
            await _log_push_sent(db, target_date, channel_type, "no_picks")
            sent += 1

    if sent:
        logger.info("No-picks notification sent to %d channel(s) for %s", sent, target_date)
    return sent


# ── Ingestion alert ───────────────────────────────────────────────────────────

async def push_ingestion_alert(
    db: AsyncSession,
    run_date: date,
    status: str,
    error_message: str | None = None,
) -> None:
    if not settings.telegram_bot_token or not settings.telegram_pro_chat_id:
        return
    try:
        date_str  = run_date.isoformat()
        msg_parts = [
            f"⚠️ <b>Ingestion alert — {_esc(date_str)}</b>",
            f"Status: <code>{_esc(status)}</code>",
        ]
        if error_message:
            msg_parts.append(f"Error: {_esc(error_message[:300])}")
        await _send_to(settings.telegram_pro_chat_id, "\n".join(msg_parts))
        logger.info("Ingestion alert sent for %s (status=%s)", date_str, status)
    except Exception as exc:
        logger.warning("push_ingestion_alert failed (non-fatal): %s", exc)
