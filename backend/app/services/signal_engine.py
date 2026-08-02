"""
signal_engine.py — Orchestrates Bayesian + Poisson engines and writes to signals table.

For each fixture on a date:
1. Load market_snapshots from DB, reconstruct engine inputs
2. Run BayesianEngine → BayesianFixtureResult
3. Run PoissonEngine → PoissonFixtureResult
4. For each active market: fuse via DualEngine → DualSignal
5. Upsert into signals table
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    CORRECT_SCORE_MARKET_NAMES,
    GOALS_MARKET_NAMES, MATCH_WINNER_MARKET_NAMES,
    DOUBLE_CHANCE_MARKET_NAMES, POISSON_RULES, get_settings,
    UNDER_GOALS_SUPPRESSED_LEAGUES,
    BOTH_MEDIUM_DISABLED_LEAGUES,
    HOME_GOALS_MARKET_NAMES, AWAY_GOALS_MARKET_NAMES,
    WIN_TO_NIL_HOME_MARKET_NAMES, WIN_TO_NIL_AWAY_MARKET_NAMES,
    WIN_TO_NIL_COMBINED_MARKET_NAMES,
    EXACT_GOALS_MARKET_NAMES,
    FIRST_HALF_GOALS_MARKET_NAMES,
    DISABLED_MARKETS,
    DISABLED_LEAGUES,
    OVER_GOALS_SUPPRESSED_LEAGUES,
    MARKET_MAX_ODDS,
    MARKET_MIN_ODDS,
    POISSON_ONLY_MAX_ODDS,
    POISSON_ONLY_KELLY_CAP,
    MAX_DAILY_EXPOSURE,
    YOUTH_LEAGUE_KEYWORDS,
    get_league_tier,
)
from app.engines import bayesian as bay_engine
from app.services.form_service import get_team_form_lambdas
from app.engines import poisson as poi_engine
from app.engines import dual_engine
from app.engines import bos as bos_engine
from app.engines import hybrid_b as hybrid_b_engine
from app.engines import zinb_goals as zinb_goals_engine
from app.services import weather_service
from app.services import lineup_service
from app.models import Fixture, MarketSnapshot, Signal
from app.services.performance_intelligence import compute_performance_weights, PerformanceWeights
from app.core.config import (
    BOS_SI_THRESHOLD, BOS_O00_MAX, BOS_CMA_MAX,
    HYBRID_B_STAKE_LEVELS,
)

settings = get_settings()

# Map market name -> Poisson rule key (used in dual fusion).
# Keys must match Signal.market values exactly (what the DB stores).
MARKET_TO_POISSON_KEY: dict[str, str] = {
    "Under 2.5":    "cs00u25",   # CS cascade rule — enables dual-model agreement for Under 2.5
    "Over 1.5":     "over15",    # dedicated evaluator (rule_strong capable); cs00o15 cascade hardcodes rule_strong=False
    "Over 2.5":     "over25",
    "Home Over 0.5":  "home_o05",
    "Away Over 0.5":  "away_o05",
    "Over 0.5 1H":    "over05fh",
    # Double Chance — Poisson bivariate probability from blended λ_h / λ_a
    "1X (Home or Draw)": "dc_1x",
    "X2 (Draw or Away)": "dc_x2",
    "12 (Home or Away)": "dc_12",
}

# Maps each mixed-signal description to the specific markets it implicates.
# Used to scope contradiction flags per-market rather than fixture-wide,
# so a clean BTTS signal is not contaminated by an Over/Under conflict on the same fixture.
_MIXED_SIGNAL_MARKETS: dict[str, set[str]] = {
    "O2.5 signal + U2.5 CS":     {"Over 2.5", "Under 2.5"},
    "O2.5 signal + U3.5 Mid":    {"Over 2.5", "Under 3.5"},
}


def _league_matches_suppression(league_lower: str, keys: set) -> bool:
    """
    Check whether a league name matches any key in the suppression set.

    Short keys (< 6 chars, e.g. "mls") use word-boundary regex to prevent
    false positives like "mls" matching "Alliansen MLS Youth".
    Longer keys use plain substring matching for speed.
    """
    for k in keys:
        if len(k) < 6:
            pattern = r'\b' + re.escape(k) + r'\b'
            if re.search(pattern, league_lower):
                return True
        else:
            if k in league_lower:
                return True
    return False


def _latest_snapshots(snapshots: list[MarketSnapshot]) -> list[MarketSnapshot]:
    latest: dict[tuple[str, str, str], MarketSnapshot] = {}
    for snap in snapshots:
        key = (snap.bookmaker, snap.market_type, snap.selection_name)
        current = latest.get(key)
        if current is None:
            latest[key] = snap
            continue
        current_ts = current.pulled_at or datetime.min
        snap_ts = snap.pulled_at or datetime.min
        if snap_ts > current_ts or (snap_ts == current_ts and (snap.id or 0) > (current.id or 0)):
            latest[key] = snap
    return list(latest.values())


def _compute_opening_odds_scoped(snapshots: list[MarketSnapshot]) -> dict[tuple[str, str, str], float]:
    earliest: dict[tuple[str, str, str], tuple] = {}
    for snap in snapshots:
        if snap.pulled_at is None or snap.odds is None:
            continue
        key = (snap.bookmaker, snap.market_type, snap.selection_name)
        if key not in earliest or snap.pulled_at < earliest[key][0]:
            earliest[key] = (snap.pulled_at, snap.odds)
    return {key: value[1] for key, value in earliest.items()}


def _compute_opening_odds(snapshots: list[MarketSnapshot]) -> dict[tuple[str, str], float]:
    """
    Return the odds from the earliest snapshot for each (bookmaker, selection_name) pair.
    Used to compute drift: current_best_odd vs opening_best_odd for that bookmaker/market combo.
    """
    earliest: dict[tuple[str, str], tuple] = {}  # key → (pulled_at, odds)
    for s in snapshots:
        if s.pulled_at is None or s.odds is None:
            continue
        key = (s.bookmaker, s.selection_name)
        if key not in earliest or s.pulled_at < earliest[key][0]:
            earliest[key] = (s.pulled_at, s.odds)
    return {k: v[1] for k, v in earliest.items()}


def _build_cs_by_bookie(snapshots: list[MarketSnapshot]) -> dict[str, list[dict]]:
    """Group CS snapshots by bookmaker -> [{value: "1:0", odd: 6.50}, ...]"""
    result: dict[str, list[dict]] = {}
    for s in snapshots:
        if s.market_type in CORRECT_SCORE_MARKET_NAMES:
            result.setdefault(s.bookmaker, []).append({"value": s.selection_name, "odd": s.odds})
    return result


def _build_goals_ou(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    """Goals O/U: {bookmaker: {label: odds}}"""
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _build_match_winner(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in MATCH_WINNER_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _build_double_chance(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in DOUBLE_CHANCE_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _build_home_totals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in HOME_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _build_away_totals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in AWAY_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _best_goals_ou_odds(
    goals_ou: dict[str, dict[str, float]],
    selection: str,
) -> tuple[float | None, str | None]:
    """Return (best_odds, bookmaker) for a Goals O/U selection (e.g. 'Over 1.5')."""
    best_odds: float | None = None
    best_bk: str | None = None
    for bk, markets in goals_ou.items():
        o = markets.get(selection)
        if o and o > (best_odds or 0):
            best_odds = o
            best_bk = bk
    return best_odds, best_bk


def _build_win_to_nil_home(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in WIN_TO_NIL_HOME_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
        elif s.market_type in WIN_TO_NIL_COMBINED_MARKET_NAMES and s.selection_name == "Home":
            # Combined "Win To Nil" market (selections Home/Away) — normalise to
            # the Yes/No shape the Bayesian lookup maps expect.
            result.setdefault(s.bookmaker, {})["Yes"] = s.odds
    return result


def _build_win_to_nil_away(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in WIN_TO_NIL_AWAY_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
        elif s.market_type in WIN_TO_NIL_COMBINED_MARKET_NAMES and s.selection_name == "Away":
            result.setdefault(s.bookmaker, {})["Yes"] = s.odds
    return result



def _best_dc_x2_odds(snapshots: list[MarketSnapshot]) -> Optional[float]:
    """Extract the best available Double Chance X2 (Draw or Away) odds from snapshots.
    API-Football uses selection_name='Draw/Away' for the X2 double-chance market."""
    best: Optional[float] = None
    for s in snapshots:
        if s.market_type in DOUBLE_CHANCE_MARKET_NAMES and s.selection_name == "Draw/Away":
            if s.odds and s.odds > 1.0 and (best is None or s.odds > best):
                best = s.odds
    return best


def _best_away_o05_odds(snapshots: list[MarketSnapshot]) -> Optional[float]:
    """Extract the best available Away Over 0.5 odds from snapshots."""
    best: Optional[float] = None
    for s in snapshots:
        if s.market_type in AWAY_GOALS_MARKET_NAMES and s.selection_name == "Over 0.5":
            if s.odds and s.odds > 1.0 and (best is None or s.odds > best):
                best = s.odds
    return best


def _best_home_o05_odds(snapshots: list[MarketSnapshot]) -> Optional[float]:
    """Extract the best available Home Over 0.5 odds from snapshots (logged only, never bet)."""
    best: Optional[float] = None
    for s in snapshots:
        if s.market_type in HOME_GOALS_MARKET_NAMES and s.selection_name == "Over 0.5":
            if s.odds and s.odds > 1.0 and (best is None or s.odds > best):
                best = s.odds
    return best


def _build_exact_goals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in EXACT_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def _build_poisson_odds(snapshots: list[MarketSnapshot]) -> tuple[dict, dict]:
    """
    Build CS odds dict {s00, s10, s01, ...} and signal_odds {over1_5, over2_5, under2_5, home_o05, away_o05}
    for the Poisson engine.
    """
    cs_map: dict[str, float] = {}

    for s in snapshots:
        if s.market_type in CORRECT_SCORE_MARKET_NAMES:
            key = s.selection_name
            if key not in cs_map or s.odds > cs_map[key]:
                cs_map[key] = s.odds

    def _cs(home: int, away: int) -> Optional[float]:
        for k in [f"{home}:{away}", f"{home}-{away}", f"{home} - {away}"]:
            if k in cs_map:
                return cs_map[k]
        return None

    odds = {
        "s00": _cs(0, 0), "s10": _cs(1, 0), "s01": _cs(0, 1),
        "s11": _cs(1, 1), "s20": _cs(2, 0), "s02": _cs(0, 2),
        "s21": _cs(2, 1), "s12": _cs(1, 2), "s22": _cs(2, 2),
        "s31": _cs(3, 1), "s13": _cs(1, 3),
    }

    signal_odds: dict[str, float] = {}
    for s in snapshots:
        sel = s.selection_name.strip()
        mt = s.market_type
        if mt in GOALS_MARKET_NAMES:
            key_map = {
                "Over 1.5": "over1_5", "Over 2.5": "over2_5",
                "Under 2.5": "under2_5",
            }
            k = key_map.get(sel)
            if k and (k not in signal_odds or s.odds > signal_odds[k]):
                signal_odds[k] = s.odds
        elif mt in HOME_GOALS_MARKET_NAMES:
            if sel == "Over 0.5":
                if "home_o05" not in signal_odds or s.odds > signal_odds["home_o05"]:
                    signal_odds["home_o05"] = s.odds
        elif mt in AWAY_GOALS_MARKET_NAMES:
            if sel == "Over 0.5":
                if "away_o05" not in signal_odds or s.odds > signal_odds["away_o05"]:
                    signal_odds["away_o05"] = s.odds
        elif mt in FIRST_HALF_GOALS_MARKET_NAMES:
            if sel == "Over 0.5":
                if "over05fh" not in signal_odds or s.odds > signal_odds["over05fh"]:
                    signal_odds["over05fh"] = s.odds

    return odds, signal_odds


_CONFIDENCE_DOWNGRADE = {"High": "Medium", "Medium": "Low", "Low": "None"}


def _team_total_context_penalty(
    market: str,
    league_tier: Optional[int],
    form_lambdas: Optional[dict],
    best_odd: Optional[float],
    bookmaker_count: Optional[int],
) -> tuple[float, bool]:
    """
    Penalize fragile team-total-over signals before they reach the tracker.

    Focus areas:
    - weak scoring side being asked to score
    - strong mismatch against the selected side
    - long price for a low-bar team-total-over
    - thin bookmaker coverage
    - Tier 3 volatility on team-scoring markets
    """
    if market not in {"Home Over 0.5", "Home Over 1.5", "Away Over 0.5", "Away Over 1.5"}:
        return 1.0, False
    if not form_lambdas:
        return 1.0, False

    lambda_h = float(form_lambdas.get("lambda_h") or 0.0)
    lambda_a = float(form_lambdas.get("lambda_a") or 0.0)
    games_h = int(form_lambdas.get("games_h") or 0)
    games_a = int(form_lambdas.get("games_a") or 0)
    if games_h <= 0 or games_a <= 0:
        return 1.0, False

    is_home_market = market.startswith("Home ")
    is_high_bar = market.endswith("1.5")
    selected_lambda = lambda_h if is_home_market else lambda_a
    opponent_lambda = lambda_a if is_home_market else lambda_h
    mismatch_gap = opponent_lambda - selected_lambda

    penalty = 1.0
    severe = False

    if league_tier == 3:
        penalty *= 0.94

    if is_high_bar:
        if selected_lambda < 1.35:
            penalty *= 0.90
            severe = True
        if mismatch_gap > 0.50:
            penalty *= 0.94
        if best_odd is not None and best_odd >= 2.65:
            penalty *= 0.94
    else:
        if selected_lambda < 0.95:
            penalty *= 0.92
            severe = True
        if mismatch_gap > 0.45:
            penalty *= 0.93
        if best_odd is not None and best_odd >= 2.20:
            penalty *= 0.93

    if bookmaker_count is not None and bookmaker_count < 3:
        penalty *= 0.96

    if mismatch_gap > 0.75 and selected_lambda < (1.20 if is_high_bar else 0.90):
        severe = True

    return round(max(0.78, penalty), 3), severe


def _is_end_of_northern_season(d: date) -> bool:
    """
    True during the Northern Hemisphere end-of-season risk window (May 10 – June 30).
    Most European leagues finish in this period; Tier 3 matches become dead rubbers
    with teams already promoted/relegated, leading to 0-0 and defensive results.
    """
    return (d.month == 5 and d.day >= 10) or d.month == 6


_OVER_GOALS_MARKETS: frozenset = frozenset({
    "Over 1.5", "Over 2.5",
    "Home Over 0.5",
})


async def _get_underperforming_leagues(
    db: AsyncSession,
    min_bets: int = 5,
    min_roi_pct: float = -20.0,
) -> frozenset[str]:
    """
    Returns a frozenset of lowercased league names to suppress, combining:
      1. tracked_bets ROI: leagues with >= min_bets settled bets and ROI < min_roi_pct
      2. Active LearningProposal(change_type="league_suppression") rows written by the
         league watch guard when a watched league crosses its suppression threshold.

    Called once per signal batch so the suppression list is always current.
    """
    from sqlalchemy import text
    from app.models.learning_proposal import LearningProposal

    result = await db.execute(text("""
        SELECT league,
               COUNT(*)        AS n,
               SUM(profit_loss) AS total_pl,
               SUM(stake)       AS total_stake
        FROM tracked_bets
        WHERE result_status IN ('Won', 'Lost')
          AND stake > 0
          AND league IS NOT NULL
        GROUP BY league
        HAVING COUNT(*) >= :min_bets
    """), {"min_bets": min_bets})

    from app.core.config import TIER_1_LEAGUES
    bad: set[str] = set()
    for row in result.all():
        league, _n, total_pl, total_stake = row
        league_lower = (league or "").lower().strip()
        # Never auto-suppress Tier 1 leagues — they may share names across countries
        # (e.g. "Premier League" = England + Ethiopia) and are too important to block.
        # Use substring check (same as get_league_tier()) — DB names like "UEFA Europa
        # Conference League" contain the keyword "conference league" but are not equal to it.
        if any(k in league_lower for k in TIER_1_LEAGUES):
            continue
        roi = (total_pl / total_stake) * 100 if total_stake else -100.0
        if roi < min_roi_pct:
            bad.add(league_lower)

    # Also include watch-guard-triggered suppressions.
    # These are substring keywords, not exact names — any league whose name contains
    # the keyword is suppressed (same matching logic used by the watch guard).
    try:
        lp_result = await db.execute(
            select(LearningProposal.target)
            .where(LearningProposal.change_type == "league_suppression")
            .where(LearningProposal.is_active == True)  # noqa: E712
        )
        for (target,) in lp_result.all():
            if target:
                bad.add(target.lower().strip())
    except Exception:
        pass  # table may not exist on first run — fail silently

    return frozenset(bad)


async def get_learned_market_ceilings(db: AsyncSession) -> dict[str, float]:
    """
    Return active market_odds_ceiling proposals as {market: ceiling_odds}.
    Keyed by exact market name (e.g. "Home Over 0.5"). These are written by
    Pipeline A (loss_analysis_agent) after backtesting against settled bets.
    Empty dict when no active proposals exist.
    """
    from app.models.learning_proposal import LearningProposal
    result = await db.execute(
        select(LearningProposal.target, LearningProposal.proposed_value)
        .where(LearningProposal.change_type == "market_odds_ceiling")
        .where(LearningProposal.is_active == True)  # noqa: E712
        .where(LearningProposal.proposed_value.isnot(None))
    )
    return {row.target: float(row.proposed_value) for row in result.all()}


async def cs_generation_allowed(db: AsyncSession) -> bool:
    """
    Runtime guard for Correct Score signal generation.

    Returns True only when ALL of the following hold:
      1. CS_ENABLED is True (master kill switch)
      2. Settled CS-market TrackedBet count >= CS_MIN_SETTLED_BETS
      3. Latest calibration snapshot Brier skill for CS >= CS_MIN_BRIER_SKILL
         (or no CS-specific snapshot exists yet, in which case criterion 2 must pass)

    Call this before generating any CS picks. Even when CS_ENABLED is toggled on,
    insufficient bet history or poor calibration will block generation.
    """
    from app.core.config import CS_ENABLED, CS_MIN_SETTLED_BETS, CS_MIN_BRIER_SKILL, CS_MARKET_PREFIX
    from sqlalchemy import text as _text
    if not CS_ENABLED:
        return False
    try:
        row = (await db.execute(_text("""
            SELECT COUNT(*) FROM tracked_bets
            WHERE result_status IN ('Won','Lost')
              AND market_type LIKE :prefix
        """), {"prefix": CS_MARKET_PREFIX + "%"})).scalar() or 0
        if row < CS_MIN_SETTLED_BETS:
            return False
    except Exception:
        return False
    # Check latest calibration snapshot: CS market Brier skill must meet the floor.
    # If no CS-specific snapshot entry exists yet (early data), this check passes
    # so the settled-bets gate remains the only hard gate until calibration data builds.
    try:
        snap_row = (await db.execute(_text("""
            SELECT market_summary FROM calibration_snapshots
            ORDER BY created_at DESC LIMIT 1
        """))).scalar()
        if snap_row:
            import json as _json
            markets = _json.loads(snap_row) if isinstance(snap_row, str) else (snap_row or [])
            cs_skills = [
                float(m.get("brier_skill", 0.0))
                for m in markets
                if str(m.get("market", "")).startswith(CS_MARKET_PREFIX)
            ]
            if cs_skills and max(cs_skills) < CS_MIN_BRIER_SKILL:
                return False
    except Exception:
        pass  # calibration table not yet populated — don't block on it
    return True


async def compute_signals_for_date(db: AsyncSession, run_date: date) -> int:
    """
    Run both engines for all fixtures on run_date. Upserts into signals table.
    Returns count of signals written.

    Adaptive confidence: if historical data shows a (market, league_tier) combination
    has a performance_factor below 0.72 for 25+ settled bets, confidence is downgraded
    by one tier (High→Medium, Medium→Low). This prevents consistently-poor
    market+league combinations from ranking as high-confidence picks.

    Transaction strategy: all per-date signals are deleted in one short commit BEFORE
    the fixture loop, so the loop runs with no open write transaction. This prevents
    the 5-minute write lock that was blocking user track-picks and settlement writes
    (which hit SQLite's busy_timeout=15 s and then propagated as 30 s frontend timeouts).
    """
    fixture_result = await db.execute(
        select(Fixture).where(Fixture.event_date == run_date)
    )
    fixtures: list[Fixture] = list(fixture_result.scalars().all())

    # Load performance weights once for this date's signal batch.
    # Used to apply adaptive confidence downgrade when a (market, tier) slice
    # has proven consistently unreliable in settled history.
    try:
        perf_weights: Optional[PerformanceWeights] = await compute_performance_weights(db)
    except Exception:
        perf_weights = None

    # Leagues with 5+ settled bets and ROI < 20% are suppressed entirely —
    # no signals generated for any fixture from these leagues until performance recovers.
    try:
        underperforming_leagues: frozenset[str] = await _get_underperforming_leagues(db, min_roi_pct=-20.0)
    except Exception:
        underperforming_leagues = frozenset()

    # Merge dynamic ROI-suppressed leagues with hard-coded blocklist
    all_suppressed_leagues = underperforming_leagues | DISABLED_LEAGUES

    # Initialise advanced models (ZINB, Glicko-2, BOS rate tables).
    # Fitted lazily from historical fixture data; gracefully no-ops if data
    # or scipy are unavailable.
    from app.services.advanced_models_service import get_or_load as _adv_get
    from datetime import date as _date
    try:
        adv = await _adv_get(db, _date.today())
    except Exception as _adv_err:
        import logging as _l
        _l.getLogger(__name__).warning("AdvancedModelsService.load() failed: %s", _adv_err)
        from app.services.advanced_models_service import AdvancedModelsService
        adv = AdvancedModelsService(db)

    # Pre-delete signals only for non-final fixtures — mirror the ingestion
    # cached_ids rule: finished fixtures (FT/AET/PEN) keep their pre-match
    # snapshots and signals so a late manual recompute never wipes good data.
    _FINAL_STATUSES = {"FT", "AET", "PEN"}
    upcoming_fixtures = [f for f in fixtures if (f.status or "").upper().strip() not in _FINAL_STATUSES]
    finished_fixtures = [f for f in fixtures if (f.status or "").upper().strip() in _FINAL_STATUSES]

    if upcoming_fixtures:
        upcoming_ids = [f.id for f in upcoming_fixtures]
        await db.execute(delete(Signal).where(Signal.fixture_id.in_(upcoming_ids)))
        await db.commit()

# Finished fixtures with existing signals are kept as-is; skip recomputing them.
    finished_with_signal: set[int] = set()
    if finished_fixtures:
        finished_ids = [f.id for f in finished_fixtures]
        sig_result = await db.execute(
            select(Signal.fixture_id).where(Signal.fixture_id.in_(finished_ids)).distinct()
        )
        finished_with_signal = {row[0] for row in sig_result.all()}

    # Only compute signals for upcoming fixtures + finished fixtures that lost
    # their signals (edge case: finished before any signal was ever computed).
    fixtures = [
        f for f in fixtures
        if f.id not in finished_with_signal
    ]

    # Collect all new Signal objects across all fixtures before writing to DB.
    # This allows portfolio-level stake normalization (improvement #1) to run
    # after all per-signal Kelly stakes are computed, before the batch commit.
    pending_signals: list[Signal] = []

    count = 0
    _fixture_idx = 0
    for fixture in fixtures:
        _fixture_idx += 1
        # Yield to the event loop every 10 fixtures so HTTP requests can be
        # processed without waiting for the entire computation batch.
        if _fixture_idx % 10 == 0:
            await asyncio.sleep(0)
        # Skip fixtures from suppressed leagues (poor ROI or hard-disabled).
        # Uses _league_matches_suppression (substring for long keys, word-boundary
        # regex for short keys) so that e.g. "Friendlies Clubs" is caught by
        # "friendlies" and any Regionalliga variant by "regionalliga".
        _league_lower_check = (fixture.league or "").lower().strip()
        if all_suppressed_leagues and _league_matches_suppression(_league_lower_check, all_suppressed_leagues):
            continue

        # Skip youth / reserve fixtures — structurally unpredictable scoring.
        _league_lower = (fixture.league or "").lower()
        if any(kw in _league_lower for kw in YOUTH_LEAGUE_KEYWORDS):
            continue

        snap_result = await db.execute(
            select(MarketSnapshot).where(MarketSnapshot.fixture_id == fixture.id)
        )
        snapshots_raw: list[MarketSnapshot] = list(snap_result.scalars().all())
        if not snapshots_raw:
            continue
        snapshots = _latest_snapshots(snapshots_raw)

        cs_by_bookie = _build_cs_by_bookie(snapshots)
        goals_ou = _build_goals_ou(snapshots)
        match_winner = _build_match_winner(snapshots)
        double_chance = _build_double_chance(snapshots)
        home_totals = _build_home_totals(snapshots)
        away_totals = _build_away_totals(snapshots)
        wtn_home = _build_win_to_nil_home(snapshots)
        wtn_away = _build_win_to_nil_away(snapshots)
        exact_goals = _build_exact_goals(snapshots)
        poi_odds, poi_signal_odds = _build_poisson_odds(snapshots)
        opening_odds_map = _compute_opening_odds_scoped(snapshots_raw)

        bay_result = bay_engine.analyse_fixture(
            fixture_id=fixture.id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            league=fixture.league or "",
            country=fixture.country or "",
            cs_by_bookie=cs_by_bookie,
            goals_ou=goals_ou,
            btts={},
            match_winner=match_winner,
            double_chance=double_chance,
            home_totals=home_totals,
            away_totals=away_totals,
            win_to_nil_home=wtn_home,
            win_to_nil_away=wtn_away,
            exact_goals=exact_goals,
            all_markets=True,
        )

        # ── Fix #1: rolling 6-game form lambda ───────────────────────────────
        # Query last N completed matches for each team and blend those goal
        # averages into the Poisson lambda.  Falls back to CS-only when there
        # is insufficient historical data (< form_min_games per team).
        form_lambdas = await get_team_form_lambdas(
            db=db,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            before_date=fixture.event_date or run_date,
        )

        poi_result = poi_engine.analyse_fixture(
            fixture_id=fixture.id,
            odds=poi_odds,
            signal_odds=poi_signal_odds,
            form_lambdas=form_lambdas or None,
        )

        # ── Advanced model enrichment ────────────────────────────────────────
        # Computed per-fixture; results are attached to matching Signal rows below.

        # ZINB: enriched expected goals from Zero-Inflated Negative Binomial model.
        # Falls back to form_lambdas when ZINB is not fitted for this league.
        _fl_h = (form_lambdas or {}).get("lambda_h") or 1.35
        _fl_a = (form_lambdas or {}).get("lambda_a") or 1.10
        _zinb_lh, _zinb_la = adv.zinb_predict(
            league=fixture.league or "",
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            fallback_lh=_fl_h,
            fallback_la=_fl_a,
            country=fixture.country or "",
        )

        # BOS 2.0: Match Stability Index.
        # Uses 0-0 CS odds, match odds balance, historical ATG, and HT rates.
        _bos_result = None
        try:
            _bos_o00 = poi_odds.get("s00") or 0.0
            if _bos_o00 > 1.0:
                _ht_data = adv.ht_rates(fixture.home_team, fixture.away_team)
                # Extract match winner odds (favourite / underdog)
                _mw_odds = [v for bm in match_winner.values() for v in bm.values()]
                _mw_sorted = sorted(set(_mw_odds)) if _mw_odds else []
                _f_odds = _mw_sorted[0] if len(_mw_sorted) >= 2 else 1.70
                _u_odds = _mw_sorted[-1] if len(_mw_sorted) >= 2 else 2.50
                _bos_result = bos_engine.compute_si(
                    o_00=_bos_o00,
                    f_odds=_f_odds,
                    u_odds=_u_odds,
                    atg_home=_ht_data["atg_home"],
                    atg_away=_ht_data["atg_away"],
                    ht_00_home=_ht_data["ht_00_home"],
                    ht_00_away=_ht_data["ht_00_away"],
                    ht_10_home=_ht_data["ht_10_home"],
                    ht_10_away=_ht_data["ht_10_away"],
                    cma_max=BOS_CMA_MAX,
                    threshold=BOS_SI_THRESHOLD,
                    o00_max=BOS_O00_MAX,
                )
        except Exception:
            pass

        # Glicko-2: rating differential + rating freshness for quality scoring.
        _glicko_rdiff = adv.glicko_r_diff(fixture.home_team, fixture.away_team)
        _glicko_age   = adv.glicko_rating_age_days(fixture.home_team, fixture.away_team)

        # ── Hybrid B Engine — replace old market-loop ────────────────────────
        # xG sourcing: prefer ZINB (fitted on league history); fall back to
        # Poisson lambda (derived from CS odds). This substitution is documented
        # in hybrid_b.py — Poisson lambda_h/lambda_a are the best available xG
        # proxies when a ZINB fit is not yet available for the fixture's league.
        _hb_home_xg: float = (_zinb_lh if _zinb_lh and _zinb_lh > 0.1 else None) or _fl_h
        _hb_away_xg: float = (_zinb_la if _zinb_la and _zinb_la > 0.1 else None) or _fl_a

        # Season-average xG = ZINB fit (league-history season baseline).
        # Recency xG = form_lambdas rolling average (last N games).
        # These MUST come from different sources — form_lambdas is the recency
        # signal, so using it for both sides would make the Phase 5 recency
        # comparison a tautology that never fires. zinb_predict returns the
        # form-lambda fallback when unfitted (indistinguishable by value), so we
        # gate on zinb_is_fitted; unfitted → None → engine skips the recency check.
        _hb_away_season_xg = _zinb_la if adv.zinb_is_fitted(fixture.league or "", country=fixture.country or "") else None
        _hb_recency_xg_away = (form_lambdas or {}).get("lambda_a") if form_lambdas else None

        # BOS stability mapping
        if _bos_result is None:
            _hb_bos = "Unknown"
        elif _bos_result.passed:
            _hb_bos = "Stable"
        else:
            _hb_bos = "Unstable"

        # X2, Away O0.5, and Home O0.5 (logged) odds from snapshots
        _hb_x2_odds = _best_dc_x2_odds(snapshots)
        _hb_ao05_odds = _best_away_o05_odds(snapshots)
        _hb_ho05_odds = _best_home_o05_odds(snapshots)

        _hb_result = hybrid_b_engine.evaluate(
            home_xg=_hb_home_xg,
            away_xg=_hb_away_xg,
            x2_odds=_hb_x2_odds,
            away_o05_odds=_hb_ao05_odds,
            home_o05_odds=_hb_ho05_odds,
            league=fixture.league or "",
            bos_stability=_hb_bos,
            country=fixture.country or "",
            # Genuine home defensive vulnerability: rolling goals-conceded
            # average for the home team. None → engine falls back to the
            # away_xg proxy and withholds the Bonus Booster.
            home_xga=(form_lambdas or {}).get("conceded_h") if form_lambdas else None,
            recency_xg_away=_hb_recency_xg_away,
            away_season_xg=_hb_away_season_xg,
        )

        # ── ZINB Goals Market engine (independent of Hybrid B) ───────────────
        # Evaluates Over 1.5 / Over 2.5 / Under 2.5 / Under 3.5 using the same
        # home_xg / away_xg that Hybrid B uses (ZINB-fitted or form-lambda).
        _zinb_goals_result = zinb_goals_engine.evaluate(_hb_home_xg, _hb_away_xg)

        # Apply league suppression to ZINB goals at generation time.
        if _zinb_goals_result is not None:
            _zg_league_lower = (fixture.league or "").lower().strip()
            _zg_is_over = _zinb_goals_result.market in {"Over 1.5", "Over 2.5"}
            if _zg_is_over and _league_matches_suppression(_zg_league_lower, OVER_GOALS_SUPPRESSED_LEAGUES):
                _zinb_goals_result = None
            elif not _zg_is_over and _league_matches_suppression(_zg_league_lower, UNDER_GOALS_SUPPRESSED_LEAGUES):
                _zinb_goals_result = None

        # Glicko gate for Hybrid B X2 (does not apply to ZINB goals).
        _hb_qualified = _hb_result.selected_market is not None
        if (
            _hb_qualified
            and _hb_result.selected_market == "X2"
            and _glicko_rdiff is not None
            and _glicko_rdiff > 40
        ):
            _hb_qualified = False

        # Skip expensive API calls if neither engine produced a candidate.
        if not _hb_qualified and _zinb_goals_result is None:
            continue

        # ── Phase 6 Rule 3: team news alert (shared gate) ────────────────────
        # Queries API-Football /injuries; triggers when away team has ≥ 5
        # injured/suspended players confirmed. Fail-open: errors → False.
        if await lineup_service.get_team_news_alert(fixture.id, fixture.away_team):
            continue

        # ── Phase 6 Rule 5: weather override (shared gate) ───────────────────
        # Fail-open: lookup errors never block a signal.
        if await weather_service.get_weather_alert(
            getattr(fixture, "venue_city", None), fixture.country, fixture.kickoff_at
        ):
            continue

        # ── Write Hybrid B signal ─────────────────────────────────────────────
        if _hb_qualified:
            # Map Hybrid B market short-name to canonical Signal.market value
            _hb_market_full = (
                "X2 (Draw or Away)" if _hb_result.selected_market == "X2"
                else "Away Over 0.5"
            )

            # dual_confidence / agreement kept for backward-compat with analytics/tracker
            _hb_confidence = {
                "HIGH":   "High",
                "MEDIUM": "Medium",
                "LOW":    "Low",
            }.get(_hb_result.stake_tier, "None")

            # Suppress Hybrid B Medium picks in leagues with confirmed structural losses.
            _hb_league_lower = (fixture.league or "").lower().strip()
            if _hb_confidence != "Medium" or _hb_league_lower not in BOTH_MEDIUM_DISABLED_LEAGUES:
                _hb_ep = _hb_result.ep_x2 if _hb_result.selected_market == "X2" else _hb_result.ep_away_o05

                sig = Signal(
                    fixture_id=fixture.id,
                    market=_hb_market_full,
                    # Poisson lambda values (xG proxies) preserved for analytics/tracker
                    poisson_lambda_h=_fl_h,
                    poisson_lambda_a=_fl_a,
                    poisson_lambda_total=_fl_h + _fl_a,
                    poisson_prob=None,
                    poisson_rule_key="hybrid_b",
                    poisson_rule_pass=True,
                    poisson_rule_strong=_hb_result.stake_tier == "HIGH",
                    poisson_grade="A" if _hb_result.stake_tier == "HIGH" else "B" if _hb_result.stake_tier == "MEDIUM" else "C",
                    bayesian_best_odd=_hb_result.selected_odds,
                    dual_confidence=_hb_confidence,
                    dual_agreement="Both",
                    dual_quality_score=round((_hb_ep or 0) / 100_000.0, 6),
                    dual_recommended_stake_pct=round(_hb_result.recommended_stake / 1_000_000.0, 6),
                    contradiction=False,
                    bos_si=_bos_result.si if _bos_result else None,
                    bos_passed=_bos_result.passed if _bos_result else None,
                    zinb_lambda_h=round(_zinb_lh, 4) if _zinb_lh else None,
                    zinb_lambda_a=round(_zinb_la, 4) if _zinb_la else None,
                    glicko_r_diff=_glicko_rdiff,
                    glicko_rating_age_days=_glicko_age,
                    home_xg=round(_hb_home_xg, 4),
                    away_xg=round(_hb_away_xg, 4),
                    home_xga=round(_hb_result.home_xga, 4),
                    recency_xg_away=round(_hb_recency_xg_away, 4) if _hb_recency_xg_away else None,
                    bos_stability=_hb_bos,
                    selected_market=_hb_result.selected_market,
                    ep_x2=_hb_result.ep_x2,
                    ep_away_o05=_hb_result.ep_away_o05,
                    recommended_stake=_hb_result.recommended_stake,
                    stake_tier=_hb_result.stake_tier,
                    home_o05_odds_logged=_hb_ho05_odds,
                )
                pending_signals.append(sig)
                count += 1

        # ── Write ZINB Goals Market signal ────────────────────────────────────
        if _zinb_goals_result is not None:
            # Look up best bookmaker odds for the selected goals line.
            _zg_odds, _zg_bk = _best_goals_ou_odds(goals_ou, _zinb_goals_result.market)
            _zg_stake = (
                HYBRID_B_STAKE_LEVELS["HIGH"]["base_stake"]
                if _zinb_goals_result.confidence == "EXCELLENT"
                else HYBRID_B_STAKE_LEVELS["MEDIUM"]["base_stake"]
            )
            _zg_confidence = "High" if _zinb_goals_result.confidence == "EXCELLENT" else "Medium"

            zinb_sig = Signal(
                fixture_id=fixture.id,
                market=_zinb_goals_result.market,
                poisson_lambda_h=round(_hb_home_xg, 4),
                poisson_lambda_a=round(_hb_away_xg, 4),
                poisson_lambda_total=round(_zinb_goals_result.total_lambda, 4),
                poisson_prob=None,
                poisson_rule_key=_zinb_goals_result.rule_key,
                poisson_rule_pass=True,
                poisson_rule_strong=_zinb_goals_result.confidence == "EXCELLENT",
                poisson_grade="A" if _zinb_goals_result.confidence == "EXCELLENT" else "B",
                bayesian_best_odd=_zg_odds,
                bayesian_bookmaker=_zg_bk,
                dual_confidence=_zg_confidence,
                dual_agreement="Poisson Only",
                dual_quality_score=round(_zg_stake / 1_000_000.0, 6),
                dual_recommended_stake_pct=round(_zg_stake / 1_000_000.0, 6),
                contradiction=False,
                bos_si=_bos_result.si if _bos_result else None,
                bos_passed=_bos_result.passed if _bos_result else None,
                zinb_lambda_h=round(_zinb_lh, 4) if _zinb_lh else None,
                zinb_lambda_a=round(_zinb_la, 4) if _zinb_la else None,
                glicko_r_diff=_glicko_rdiff,
                glicko_rating_age_days=_glicko_age,
                home_xg=round(_hb_home_xg, 4),
                away_xg=round(_hb_away_xg, 4),
                bos_stability=_hb_bos,
                recommended_stake=_zg_stake,
                stake_tier="HIGH" if _zinb_goals_result.confidence == "EXCELLENT" else "MEDIUM",
            )
            pending_signals.append(zinb_sig)
            count += 1

    # ── Portfolio stake normalization ─────────────────────────────────────────
    # Cap total daily recommended exposure at MAX_DAILY_EXPOSURE (15 % of bankroll).
    # Scale all stakes proportionally so the strongest signals keep the largest
    # share while the aggregate stays within safe bankroll limits.
    stakeable = [s for s in pending_signals if (s.dual_recommended_stake_pct or 0) > 0]
    if stakeable:
        total_stake = sum(s.dual_recommended_stake_pct for s in stakeable)
        if total_stake > MAX_DAILY_EXPOSURE:
            scale = MAX_DAILY_EXPOSURE / total_stake
            for s in stakeable:
                s.dual_recommended_stake_pct = round(s.dual_recommended_stake_pct * scale, 4)

    # Write signals in small batches so the write lock is released between
    # commits, letting other requests (bets, health checks) slip through.
    _WRITE_BATCH = 50
    for i in range(0, len(pending_signals), _WRITE_BATCH):
        for sig in pending_signals[i : i + _WRITE_BATCH]:
            db.add(sig)
        await db.commit()
        await asyncio.sleep(0)   # yield between batches

    return count + len(finished_with_signal)
