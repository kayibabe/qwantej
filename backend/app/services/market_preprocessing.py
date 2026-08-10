"""
market_preprocessing.py — MarketSnapshot preprocessing helpers.

Extracted from the retired signal_engine.py.  These pure functions take a
list of MarketSnapshot ORM rows and build the structured dicts that the
Bayesian engine expects.  Used by ensemble_service for live-fixture runs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models.odds import MarketSnapshot
from app.core.config import (
    CORRECT_SCORE_MARKET_NAMES,
    GOALS_MARKET_NAMES,
    MATCH_WINNER_MARKET_NAMES,
    DOUBLE_CHANCE_MARKET_NAMES,
    HOME_GOALS_MARKET_NAMES,
    AWAY_GOALS_MARKET_NAMES,
    WIN_TO_NIL_HOME_MARKET_NAMES,
    WIN_TO_NIL_AWAY_MARKET_NAMES,
    WIN_TO_NIL_COMBINED_MARKET_NAMES,
    EXACT_GOALS_MARKET_NAMES,
    FIRST_HALF_GOALS_MARKET_NAMES,
)


def latest_snapshots(snapshots: list[MarketSnapshot]) -> list[MarketSnapshot]:
    """Deduplicate: keep the most-recent snapshot per (bookmaker, market_type, selection_name)."""
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


def build_cs_by_bookie(snapshots: list[MarketSnapshot]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for s in snapshots:
        if s.market_type in CORRECT_SCORE_MARKET_NAMES:
            result.setdefault(s.bookmaker, []).append({"value": s.selection_name, "odd": s.odds})
    return result


def build_goals_ou(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_match_winner(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in MATCH_WINNER_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_double_chance(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in DOUBLE_CHANCE_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_home_totals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in HOME_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_away_totals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in AWAY_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_win_to_nil_home(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in WIN_TO_NIL_HOME_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
        elif s.market_type in WIN_TO_NIL_COMBINED_MARKET_NAMES and s.selection_name == "Home":
            result.setdefault(s.bookmaker, {})["Yes"] = s.odds
    return result


def build_win_to_nil_away(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in WIN_TO_NIL_AWAY_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
        elif s.market_type in WIN_TO_NIL_COMBINED_MARKET_NAMES and s.selection_name == "Away":
            result.setdefault(s.bookmaker, {})["Yes"] = s.odds
    return result


def build_exact_goals(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in EXACT_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result


def build_goals_first_half(snapshots: list[MarketSnapshot]) -> dict[str, dict[str, float]]:
    """Extract first-half goals Over/Under odds: {bookmaker: {selection: odds}}."""
    result: dict[str, dict[str, float]] = {}
    for s in snapshots:
        if s.market_type in FIRST_HALF_GOALS_MARKET_NAMES:
            result.setdefault(s.bookmaker, {})[s.selection_name] = s.odds
    return result
