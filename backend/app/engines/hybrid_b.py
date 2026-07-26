"""
hybrid_b.py — Hybrid B Strategy Engine.

Focuses exclusively on two markets:
  1. X2 (Away Win or Draw)
  2. Away O0.5 (Away team scores)

Home O0.5 odds are pulled and logged only — NEVER selected for betting.
BET_HOME_OVER_0_5 = False is a hard constant.

Phase 1 — xG sourcing:
  Use ZINB mu values when available; fall back to Poisson lambda_h / lambda_a.
  # Substitution: poisson_lambda_home → Home xG, poisson_lambda_away → Away xG
  # when true ZINB xG is unavailable (API-Football provides implied xG via CS odds,
  # not a direct ZINB fit).
  home_xga = away_xg: the away team's expected goals ARE the goals conceded by the
  home defence — this is the simplest available defensive proxy and avoids an extra
  data source while preserving the correct economic interpretation.

Phase 2 — Qualifying filters (all must pass; any failure = REJECTED)
Phase 3 — Market selection via Expected Profit (EP)
Phase 4 — Dynamic staking (MWK amounts)
Phase 5 — Recency xG form stake adjustment (advisory)
Phase 6 — Do Not Bet overrides
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import (
    HYBRID_B_MIN_AWAY_XG,
    HYBRID_B_MAX_HOME_AWAY_XG_RATIO,
    HYBRID_B_PERMANENT_BLACKLIST,
    HYBRID_B_CONDITIONAL_BLACKLIST,
    HYBRID_B_STAKE_LEVELS,
    HYBRID_B_HOME_XGA_BONUS_THRESHOLD,
)

BET_HOME_OVER_0_5: bool = False  # hard constant — never bet Home O0.5


@dataclass
class HybridBResult:
    """Result of the Hybrid B engine for a single fixture."""
    selected_market: Optional[str]       # "X2" | "Away O0.5" | None (rejected)
    selected_odds: Optional[float]
    ep_x2: Optional[float]               # Expected Profit for X2 market
    ep_away_o05: Optional[float]         # Expected Profit for Away O0.5 market
    stake_tier: str                      # "HIGH" | "MEDIUM" | "LOW" | "SKIP"
    recommended_stake: float             # MWK: 100000 / 75000 / 50000 / 0
    rejection_reason: Optional[str]
    # xG metadata (stored on Signal row)
    away_xg: float
    home_xg: float
    home_xga: float                      # = away_xg (defensive proxy — see module docstring)
    recency_xg_away: Optional[float]
    away_season_xg: Optional[float]
    bos_stability: str                   # "Stable" | "Unstable" | "Unknown"
    home_o05_odds_logged: Optional[float]


def _stake_tier_for_odds(odds: float) -> str:
    """Map decimal odds to the Hybrid B stake tier."""
    for tier in ("HIGH", "MEDIUM", "LOW"):
        if odds >= HYBRID_B_STAKE_LEVELS[tier]["min_odds"]:
            return tier
    return "SKIP"


def evaluate(
    home_xg: float,
    away_xg: float,
    x2_odds: Optional[float],
    away_o05_odds: Optional[float],
    home_o05_odds: Optional[float],
    league: str,
    bos_stability: str,
    country: str = "",
    home_xga: Optional[float] = None,
    recency_xg_away: Optional[float] = None,
    away_season_xg: Optional[float] = None,
    team_news_alert: bool = False,
    weather_alert: bool = False,
) -> HybridBResult:
    """
    Run Hybrid B phases 2–6 for a single fixture.

    Parameters
    ----------
    home_xg / away_xg   : expected goals — ZINB mu when fitted, else Poisson lambda
    x2_odds             : best available odds for X2 (Draw or Away)
    away_o05_odds       : best available odds for Away Over 0.5
    home_o05_odds       : Home O0.5 odds (logged only — BET_HOME_OVER_0_5 = False)
    league              : competition name (raw, from fixture)
    bos_stability       : "Stable" | "Unstable" | "Unknown" (from BOS engine)
    recency_xg_away     : 5-match rolling average xG for the away team
    away_season_xg      : season-average xG for the away team (Poisson lambda proxy)
    home_xga            : home team's genuine defensive vulnerability — rolling
                          goals-conceded average from form data. None when the
                          home team lacks form history; falls back to the
                          away_xg proxy (documented in module docstring). The
                          Bonus Booster is only meaningful with the genuine
                          value — the proxy always exceeds the 1.4 threshold
                          because Filter 1 requires away_xg ≥ 1.50.
    team_news_alert     : True when away team is confirmed resting key starters
    weather_alert       : True when venue forecast shows heavy rain (≥10mm/hr)
                          or high winds (≥50km/h) at kickoff — Phase 6 Rule 5
    """
    # Genuine goals-conceded form when available; away_xg proxy as last resort.
    home_xga_is_genuine = home_xga is not None
    if home_xga is None:
        home_xga = away_xg
    league_lower = (league or "").lower().strip()
    country_lower = (country or "").lower().strip()

    def _reject(reason: str) -> HybridBResult:
        return HybridBResult(
            selected_market=None, selected_odds=None,
            ep_x2=None, ep_away_o05=None,
            stake_tier="SKIP", recommended_stake=0.0,
            rejection_reason=reason,
            away_xg=away_xg, home_xg=home_xg, home_xga=home_xga,
            recency_xg_away=recency_xg_away, away_season_xg=away_season_xg,
            bos_stability=bos_stability, home_o05_odds_logged=home_o05_odds,
        )

    # ── Phase 2: Qualifying filters ───────────────────────────────────────
    # Filter 1 — Away xG ≥ 1.50
    if away_xg < HYBRID_B_MIN_AWAY_XG:
        return _reject(f"F1:away_xg={away_xg:.2f}<{HYBRID_B_MIN_AWAY_XG}")

    # Filter 2 — Home xG < Away xG × 2.0
    if home_xg >= away_xg * HYBRID_B_MAX_HOME_AWAY_XG_RATIO:
        return _reject(f"F2:home_xg={home_xg:.2f}≥away_xg*{HYBRID_B_MAX_HOME_AWAY_XG_RATIO}")

    # Filter 3 — Permanent blacklist leagues (exact substring match, lower)
    if any(bl in league_lower for bl in HYBRID_B_PERMANENT_BLACKLIST):
        return _reject(f"F3:permanent_blacklist:{league}")

    # Filter 4 — Conditional blacklist: reject when BOS Stability = Unstable.
    # Entries are COUNTRY names (Brazil/Argentina/Latvia) — API-Football league
    # strings ("Primera C", "Serie B") don't contain them, so match against the
    # fixture country as well as the league name.
    if bos_stability == "Unstable":
        if any(cl in league_lower or cl in country_lower for cl in HYBRID_B_CONDITIONAL_BLACKLIST):
            return _reject(f"F4:conditional_blacklist:{country or league},BOS=Unstable")

    # ── Double-Loss Skip Rule ─────────────────────────────────────────────
    # Variance risk does not justify the return on very short-priced, low-scoring fixtures
    if (
        home_xg < 0.50
        and (x2_odds or 0.0) < 1.15
        and (away_o05_odds or 0.0) < 1.20
    ):
        return _reject("DLS:home_xg<0.50&x2<1.15&ao05<1.20")

    # ── Phase 3: Market selection ─────────────────────────────────────────
    x2_tier = _stake_tier_for_odds(x2_odds or 0.0) if x2_odds and x2_odds > 1.0 else "SKIP"
    ao05_tier = _stake_tier_for_odds(away_o05_odds or 0.0) if away_o05_odds and away_o05_odds > 1.0 else "SKIP"

    x2_base = HYBRID_B_STAKE_LEVELS[x2_tier]["base_stake"]
    ao05_base = HYBRID_B_STAKE_LEVELS[ao05_tier]["base_stake"]

    ep_x2: Optional[float] = None
    ep_ao05: Optional[float] = None

    if x2_tier != "SKIP" and x2_odds:
        ep_x2 = round((x2_base * x2_odds) - x2_base, 2)

    if ao05_tier != "SKIP" and away_o05_odds:
        ep_ao05 = round((ao05_base * away_o05_odds) - ao05_base, 2)

    # Decision matrix (EP-first):
    #   1. Pick the market with higher positive EP.
    #   2. When EP is equal, xG direction breaks the tie (away_xg > home_xg → X2).
    #   3. Only one market qualifies → pick it.
    x2_ep_pos = ep_x2 is not None and ep_x2 > 0
    ao05_ep_pos = ep_ao05 is not None and ep_ao05 > 0

    if not x2_ep_pos and not ao05_ep_pos:
        return _reject("P3:no_positive_EP")

    if x2_ep_pos and ao05_ep_pos:
        if (ep_x2 or 0) > (ep_ao05 or 0):
            selected = "X2"
        elif (ep_ao05 or 0) > (ep_x2 or 0):
            selected = "Away O0.5"
        else:
            # Equal EP — xG direction tiebreaker
            selected = "X2" if away_xg >= home_xg else "Away O0.5"
    elif x2_ep_pos:
        selected = "X2"
    elif ao05_ep_pos:
        selected = "Away O0.5"
    else:
        return _reject("P3:no_qualifying_market")

    selected_odds = x2_odds if selected == "X2" else away_o05_odds
    selected_tier = x2_tier if selected == "X2" else ao05_tier

    if not selected_odds or selected_tier == "SKIP":
        return _reject("P3:no_valid_odds_for_selected_market")

    # ── Phase 6 pre-check overrides (before staking) ─────────────────────
    # Override 1: X2 odds == Away O0.5 odds AND both < 1.20 (no edge)
    if (
        x2_odds is not None and away_o05_odds is not None
        and abs(x2_odds - away_o05_odds) < 0.001
        and x2_odds < 1.20
    ):
        return _reject("P6-1:x2==ao05<1.20")

    # Override 2: permanent blacklist guard (redundant with Filter 3, defensive)
    if any(bl in league_lower for bl in HYBRID_B_PERMANENT_BLACKLIST):
        return _reject("P6-2:permanent_blacklist")

    # Override 3: team news alert (away team resting key starters)
    if team_news_alert:
        return _reject("P6-3:team_news_alert")

    # Override 5: weather — heavy rain or high winds at kickoff.
    # The alert flag is resolved by weather_service (Open-Meteo) in the caller;
    # the engine stays pure and just enforces the rule.
    if weather_alert:
        return _reject("P6-5:weather_alert")

    # ── Phase 4: Dynamic staking ──────────────────────────────────────────
    tier_cfg = HYBRID_B_STAKE_LEVELS[selected_tier]
    recommended_stake: float = tier_cfg["base_stake"]

    # Bonus Booster: HIGH tier + home_xga ≥ 1.4 → bonus_stake (K100k).
    # Requires GENUINE goals-conceded data — the away_xg proxy always clears
    # the 1.4 threshold (Filter 1 guarantees away_xg ≥ 1.50), which would
    # grant the bonus to every HIGH-tier pick and defeat its purpose.
    if (
        selected_tier == "HIGH"
        and home_xga_is_genuine
        and home_xga >= HYBRID_B_HOME_XGA_BONUS_THRESHOLD
    ):
        recommended_stake = tier_cfg["bonus_stake"]

    # ── Phase 5: Recency form advisory stake adjustment ───────────────────
    # Cold form (< 0.75× season): reduce stake one tier.
    # Hot form  (> 1.25× season): raise stake one tier (bonus indicator).
    # The two conditions are mutually exclusive by construction.
    _tier_order = ["HIGH", "MEDIUM", "LOW", "SKIP"]
    if (
        recency_xg_away is not None
        and away_season_xg is not None
        and away_season_xg > 0
    ):
        if recency_xg_away < away_season_xg * 0.75:
            # Away team in poor recent form — reduce stake one tier
            idx = _tier_order.index(selected_tier)
            if idx < len(_tier_order) - 1:
                reduced_tier = _tier_order[idx + 1]
                recommended_stake = HYBRID_B_STAKE_LEVELS[reduced_tier]["base_stake"]
                selected_tier = reduced_tier
        elif recency_xg_away > away_season_xg * 1.25:
            # Hot streak — raise stake one tier (capped at HIGH base stake).
            # Deliberately does NOT grant the K100k bonus: the bonus booster
            # requires genuine HIGH-tier odds + home_xga confirmation (Phase 4),
            # not a form-driven tier promotion.
            idx = _tier_order.index(selected_tier)
            if idx > 0:
                raised_tier = _tier_order[idx - 1]
                recommended_stake = HYBRID_B_STAKE_LEVELS[raised_tier]["base_stake"]
                selected_tier = raised_tier

    # ── Phase 6 post-stake overrides ─────────────────────────────────────
    # Override 4: home_xg < 0.30 AND selected market is X2 → force LOW stake
    if home_xg < 0.30 and selected == "X2":
        recommended_stake = HYBRID_B_STAKE_LEVELS["LOW"]["base_stake"]
        selected_tier = "LOW"

    return HybridBResult(
        selected_market=selected,
        selected_odds=selected_odds,
        ep_x2=ep_x2,
        ep_away_o05=ep_ao05,
        stake_tier=selected_tier,
        recommended_stake=recommended_stake,
        rejection_reason=None,
        away_xg=away_xg, home_xg=home_xg, home_xga=home_xga,
        recency_xg_away=recency_xg_away, away_season_xg=away_season_xg,
        bos_stability=bos_stability, home_o05_odds_logged=home_o05_odds,
    )
