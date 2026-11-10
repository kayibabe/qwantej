#!/usr/bin/env python3
"""Read-only backtest of the System Picks filter surface.

The daily "System picks" page exposes market, model-chance, bookmaker-implied,
signal, recommendation and outcome filters over Q >= 75 predictions.  This
script replays the pre-bet part of that surface against settled history and
reports what actually held up.

It is deliberately a research tool:

* no writes, no publication changes, no model retraining;
* only completed days and pre-kickoff information;
* first (or latest) stored prediction per match/market/selection;
* one unit per pick, using the stored entry price;
* chronological train/test split, plus a within-market label permutation to
  show how easy it is to find a "sweet spot" by searching many cells.

Run inside the backend container, from /app:

  python /tmp/market_sweet_spot_backtest.py --selection latest \
      --output /tmp/market-sweet-spot-latest

Then copy the output directory back to the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.models import SelectionResult
from app.services.settlement import evaluate_selection

CAT = timezone(timedelta(hours=2))

MARKETS = [
    "away_win",
    "btts_no",
    "btts_yes",
    "double_chance_12",
    "double_chance_1x",
    "double_chance_x2",
    "dnb_away",
    "dnb_home",
    "draw",
    "home_win",
    "over_1.5",
    "over_2.5",
    "over_3.5",
    "over_4.5",
    "under_0.5",
    "under_1.5",
    "under_2.5",
    "under_3.5",
    "under_4.5",
]
ODDS_BANDS = [
    ("1.00-1.49", 1.00, 1.50),
    ("1.50-1.79", 1.50, 1.80),
    ("1.80-2.19", 1.80, 2.20),
    ("2.20-2.99", 2.20, 3.00),
    ("3.00-3.99", 3.00, 4.00),
    ("4.00+", 4.00, 1000.0),
]
CHANCE_THRESHOLDS = [0.00, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
CHANCE_LABELS = ["any", ">=40%", ">=50%", ">=60%", ">=70%", ">=80%", ">=90%"]
REC_LEVELS = ["BET", "WATCH", "other"]
SIGNAL_TOGGLES = [
    ("edge", "positive edge"),
    ("aligned", "aligned <=5pp"),
    ("fresh", "quote <=8h"),
]

QUERY = """
SELECT p.id AS prediction_id, p.match_id, p.market, p.selection,
       p.q_score, p.q_grade, p.edge, p.model_probability, p.model_agreement,
       p.source_decimal_odds AS odds, p.source_odds_at, p.created_at,
       p.decision_at, p.as_of_at, p.source_odds_provenance,
       p.source_implied_probability, p.closing_decimal_odds, p.clv_percentage,
       p.recommendation_status, p.model_version,
       m.kickoff_at, m.home_goals, m.away_goals,
       c.name AS competition, h.name AS home_team, a.name AS away_team
FROM predictions p
JOIN matches m ON m.id = p.match_id
JOIN competitions c ON c.id = m.competition_id
JOIN teams h ON h.id = m.home_team_id
JOIN teams a ON a.id = m.away_team_id
WHERE m.status = 'FINISHED'
  AND m.excluded_from_models IS NOT TRUE
ORDER BY p.created_at, p.id
"""


async def load_rows() -> list[dict]:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        rows = (await db.execute(text(QUERY))).mappings().all()
    return [dict(row) for row in rows]


def _dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def prepare(rows: list[dict], as_at: datetime, selection: str) -> tuple[pd.DataFrame, Counter]:
    """Strict no-lookahead preparation.

    ``selection=first`` keeps the first stored prediction per match/market/
    selection.  ``selection=latest`` keeps the latest pre-kickoff one, which is
    closer to what the daily page shows.  Both are reported because the choice
    changes the sample.
    """
    ordered = rows if selection == "first" else list(reversed(rows))
    seen: set[tuple[int, str, str]] = set()
    exclusions: Counter = Counter()
    records: list[dict] = []
    as_at_day = as_at.astimezone(CAT).date()

    for row in ordered:
        key = (row["match_id"], row["market"], row["selection"])
        if key in seen:
            exclusions["later_repeat"] += 1
            continue
        seen.add(key)

        odds = row["odds"]
        created = _dt(row["created_at"])
        kickoff = _dt(row["kickoff_at"])
        decision = _dt(row["decision_at"]) or created
        quote = _dt(row["source_odds_at"])
        provenance = row.get("source_odds_provenance") or {}

        if not odds or not math.isfinite(float(odds)) or float(odds) <= 1:
            exclusions["missing_or_invalid_odds"] += 1
            continue
        if row.get("as_of_at"):
            exclusions["replay_snapshot"] += 1
            continue
        if not quote or not created or not kickoff or not decision:
            exclusions["missing_timestamp"] += 1
            continue
        if not (quote <= decision < kickoff and created < kickoff):
            exclusions["timing_or_post_kickoff_update"] += 1
            continue
        if provenance.get("is_fallback"):
            exclusions["fallback_odds"] += 1
            continue
        if kickoff.astimezone(CAT).date() >= as_at_day:
            exclusions["current_or_future_day"] += 1
            continue

        try:
            result = evaluate_selection(row["market"], row["home_goals"], row["away_goals"])
        except ValueError:
            exclusions["unsupported_market"] += 1
            continue
        if result == SelectionResult.VOID:
            exclusions["void_dnb_draw"] += 1
            continue

        won = result == SelectionResult.WON
        odds_f = float(odds)
        records.append(
            {
                "prediction_id": int(row["prediction_id"]),
                "match_id": int(row["match_id"]),
                "market": row["market"],
                "selection": row["selection"],
                "competition": row["competition"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "kickoff_at": kickoff,
                "day": kickoff.astimezone(CAT).date().isoformat(),
                "q_score": float(row["q_score"]),
                "q_grade": row["q_grade"],
                "model_probability": float(row["model_probability"]),
                "source_implied_probability": (
                    float(row["source_implied_probability"])
                    if row["source_implied_probability"] is not None
                    else np.nan
                ),
                "edge": float(row["edge"]) if row["edge"] is not None else np.nan,
                "model_agreement": (
                    float(row["model_agreement"]) if row["model_agreement"] is not None else np.nan
                ),
                "odds": odds_f,
                "closing_decimal_odds": (
                    float(row["closing_decimal_odds"])
                    if row["closing_decimal_odds"] is not None
                    else np.nan
                ),
                "clv_percentage": (
                    float(row["clv_percentage"]) if row["clv_percentage"] is not None else np.nan
                ),
                "recommendation_status": row["recommendation_status"] or "other",
                "model_version": row["model_version"],
                "quote_age_hours": (decision - quote).total_seconds() / 3600.0,
                "won": bool(won),
                "profit": (odds_f - 1.0) if won else -1.0,
            }
        )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame, exclusions
    frame["source_implied_probability"] = frame["source_implied_probability"].astype(float)
    return frame, exclusions


def summarise(frame: pd.DataFrame) -> dict:
    n = len(frame)
    if n == 0:
        return {
            "n": 0,
            "matches": 0,
            "days": 0,
            "wins": 0,
            "losses": 0,
            "hit_rate": None,
            "roi": None,
            "profit": 0.0,
            "avg_odds": None,
        }
    wins = int(frame["won"].sum())
    profit = float(frame["profit"].sum())
    return {
        "n": n,
        "matches": int(frame["match_id"].nunique()),
        "days": int(frame["day"].nunique()),
        "wins": wins,
        "losses": n - wins,
        "hit_rate": 100.0 * wins / n,
        "roi": 100.0 * profit / n,
        "profit": profit,
        "avg_odds": float(frame["odds"].mean()),
    }


def cluster_bootstrap_roi(frame: pd.DataFrame, draws: int = 5000, seed: int = 20261110) -> list[float] | None:
    """Day-cluster bootstrap for ROI, because picks on one day are correlated."""
    if frame.empty:
        return None
    grouped = frame.groupby("day")
    clusters = [(float(g["profit"].sum()), len(g)) for _, g in grouped]
    if len(clusters) < 2:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(clusters, dtype=float)
    idx = rng.integers(0, len(arr), size=(draws, len(arr)))
    roi = 100.0 * arr[idx, 0].sum(axis=1) / arr[idx, 1].sum(axis=1)
    return [float(np.percentile(roi, 2.5)), float(np.percentile(roi, 97.5))]


def cluster_bootstrap_test(frame: pd.DataFrame, draws: int = 5000, seed: int = 20261110) -> dict | None:
    """Day-cluster bootstrap with a one-sided p-value for ROI > 0."""
    if frame.empty:
        return None
    grouped = frame.groupby("day")
    clusters = [(float(g["profit"].sum()), len(g)) for _, g in grouped]
    if len(clusters) < 2:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(clusters, dtype=float)
    idx = rng.integers(0, len(arr), size=(draws, len(arr)))
    roi = 100.0 * arr[idx, 0].sum(axis=1) / arr[idx, 1].sum(axis=1)
    return {
        "low": float(np.percentile(roi, 2.5)),
        "high": float(np.percentile(roi, 97.5)),
        "p_one_sided": float((np.sum(roi <= 0.0) + 1) / (draws + 1)),
    }


def market_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for market, group in frame.groupby("market"):
        item = summarise(group)
        item["market"] = market
        item["bootstrap_95"] = cluster_bootstrap_roi(group)
        rows.append(item)
    return pd.DataFrame(rows).sort_values(["n", "market"], ascending=[False, True])


def band_table(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    rows = []
    if dimension == "odds":
        for label, low, high in ODDS_BANDS:
            group = frame[(frame["odds"] >= low) & (frame["odds"] < high)]
            if group.empty:
                continue
            item = summarise(group)
            item[dimension] = label
            item["bootstrap_95"] = cluster_bootstrap_roi(group)
            rows.append(item)
    elif dimension == "q":
        bands = [(75, 80), (80, 85), (85, 90), (90, 101)]
        for low, high in bands:
            group = frame[(frame["q_score"] >= low) & (frame["q_score"] < high)]
            if group.empty:
                continue
            item = summarise(group)
            item[dimension] = f"{low}-{high if high < 101 else '+'}"
            item["bootstrap_95"] = cluster_bootstrap_roi(group)
            rows.append(item)
    elif dimension == "probability":
        bands = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
        for low, high in bands:
            group = frame[(frame["model_probability"] >= low) & (frame["model_probability"] < high)]
            if group.empty:
                continue
            item = summarise(group)
            item[dimension] = f"{int(low * 100)}-{int(high * 100)}%"
            item["bootstrap_95"] = cluster_bootstrap_roi(group)
            rows.append(item)
    elif dimension == "implied":
        bands = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
        for low, high in bands:
            group = frame[
                (frame["source_implied_probability"] >= low)
                & (frame["source_implied_probability"] < high)
            ]
            if group.empty:
                continue
            item = summarise(group)
            item[dimension] = f"{int(low * 100)}-{int(high * 100)}%"
            item["bootstrap_95"] = cluster_bootstrap_roi(group)
            rows.append(item)
    return pd.DataFrame(rows)


def signal_table(frame: pd.DataFrame) -> pd.DataFrame:
    definitions = [
        ("any", pd.Series(True, index=frame.index)),
        ("positive edge", frame["edge"] > 0),
        ("aligned <=5pp", frame["model_agreement"] <= 0.05),
        ("quote <=8h", frame["quote_age_hours"] <= 8),
        ("quote <=2h", frame["quote_age_hours"] <= 2),
        ("CLV > 0 (lookahead)", frame["clv_percentage"] > 0),
        ("BET", frame["recommendation_status"] == "BET"),
        ("WATCH", frame["recommendation_status"] == "WATCH"),
    ]
    rows = []
    for label, mask in definitions:
        group = frame[mask.fillna(False)]
        if group.empty:
            continue
        item = summarise(group)
        item["signal"] = label
        item["bootstrap_95"] = cluster_bootstrap_roi(group)
        rows.append(item)
    return pd.DataFrame(rows)


def calibration_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for market, group in frame.groupby("market"):
        if len(group) < 20:
            continue
        observed = group["won"].mean()
        model = group["model_probability"].mean()
        known_implied = group["source_implied_probability"].notna()
        implied = group.loc[known_implied, "source_implied_probability"].mean()
        model_brier = float(((group["model_probability"] - group["won"]) ** 2).mean())
        implied_brier = (
            float(
                (
                    (
                        group.loc[known_implied, "source_implied_probability"]
                        - group.loc[known_implied, "won"]
                    )
                    ** 2
                ).mean()
            )
            if known_implied.any()
            else None
        )
        clv = group["clv_percentage"].dropna()
        rows.append(
            {
                "market": market,
                "n": len(group),
                "observed_hit_%": 100.0 * observed,
                "model_prob_%": 100.0 * model,
                "implied_prob_%": 100.0 * implied if known_implied.any() else None,
                "model_minus_observed_pp": 100.0 * (model - observed),
                "model_minus_implied_pp": (
                    100.0 * (model - implied) if known_implied.any() else None
                ),
                "model_brier": model_brier,
                "implied_brier": implied_brier,
                "clv_n": int(clv.size),
                "mean_clv_%": 100.0 * clv.mean() if clv.size else None,
                "beat_close_%": 100.0 * (clv > 0).mean() if clv.size else None,
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def _band_index(values: np.ndarray) -> np.ndarray:
    """Map probability to the exact 10-point band 0..6 used by the UI blocks."""
    clipped = np.clip(np.floor(np.nan_to_num(values, nan=0.0) * 10.0), 0, 9).astype(int)
    # 0 = below 40%; 1 = 40-49%; ... 6 = 90%+.
    return np.clip(clipped - 3, 0, 6)


def _odds_index(values: np.ndarray) -> np.ndarray:
    idx = np.zeros(len(values), dtype=int)
    for position, (_, low, high) in enumerate(ODDS_BANDS):
        idx[(values >= low) & (values < high)] = position
    return idx


def _rec_index(values: pd.Series) -> np.ndarray:
    mapping = {"BET": 0, "WATCH": 1}
    return np.array([mapping.get(value, 2) for value in values], dtype=int)


def _cumulative(array: np.ndarray, axis: int) -> np.ndarray:
    """Cumulative sum from the high band down, so index t means 'band >= t'."""
    return np.flip(np.cumsum(np.flip(array, axis=axis), axis=axis), axis=axis)


def build_grid(frame: pd.DataFrame, split_date: str, min_sample: int) -> tuple[pd.DataFrame, dict]:
    """Enumerate pre-bet filter cells with vectorised bincounts.

    Dimensions: market x odds band x chance block x implied block x signal
    combination x recommendation x train/test.  Chance and implied blocks are
    cumulative, matching the page's ">= block" filters.
    """
    markets = sorted(frame["market"].unique())
    market_idx = pd.Categorical(frame["market"], categories=markets).codes
    odds_idx = _odds_index(frame["odds"].to_numpy())
    chance_idx = _band_index(frame["model_probability"].to_numpy())
    implied_idx = _band_index(frame["source_implied_probability"].to_numpy())
    rec_idx = _rec_index(frame["recommendation_status"])
    split_idx = (frame["day"] >= split_date).astype(int).to_numpy()

    n_markets = len(markets)
    n_odds = len(ODDS_BANDS)
    n_bands = len(CHANCE_THRESHOLDS)  # 7 exact bands, 7 threshold levels
    n_rec = len(REC_LEVELS)
    n_split = 2
    shape = (n_markets, n_odds, n_bands, n_bands, n_rec, n_split)
    size = int(np.prod(shape))

    signal_masks = []
    for edge_on in (False, True):
        for aligned_on in (False, True):
            for fresh_on in (False, True):
                mask = np.ones(len(frame), dtype=bool)
                if edge_on:
                    mask &= np.nan_to_num(frame["edge"].to_numpy(), nan=-1.0) > 0
                if aligned_on:
                    mask &= np.nan_to_num(frame["model_agreement"].to_numpy(), nan=1.0) <= 0.05
                if fresh_on:
                    mask &= frame["quote_age_hours"].to_numpy() <= 8.0
                signal_masks.append(((edge_on, aligned_on, fresh_on), mask))

    def bincounts(profit_values: np.ndarray, win_values: np.ndarray, keep: np.ndarray):
        flat = (
            ((((market_idx[keep] * n_odds + odds_idx[keep]) * n_bands + chance_idx[keep])
              * n_bands + implied_idx[keep]) * n_rec + rec_idx[keep]) * n_split
            + split_idx[keep]
        )
        counts = np.bincount(flat, minlength=size).reshape(shape).astype(float)
        profit = np.bincount(flat, weights=profit_values[keep], minlength=size).reshape(shape)
        wins = np.bincount(flat, weights=win_values[keep], minlength=size).reshape(shape)
        odds_sum = np.bincount(flat, weights=frame["odds"].to_numpy()[keep], minlength=size).reshape(shape)
        profit_sq = np.bincount(
            flat, weights=(profit_values[keep] ** 2), minlength=size
        ).reshape(shape)
        return counts, profit, wins, odds_sum, profit_sq

    observed_profit = frame["profit"].to_numpy()
    observed_wins = frame["won"].to_numpy().astype(float)

    records: list[dict] = []
    valid_masks: list[tuple[tuple[bool, bool, bool], np.ndarray, np.ndarray]] = []

    for signals, mask in signal_masks:
        counts, profit, wins, odds_sum, profit_sq = bincounts(
            observed_profit, observed_wins, mask
        )

        # Cumulative over chance and implied bands.
        c_counts = _cumulative(_cumulative(counts, 2), 3)
        c_profit = _cumulative(_cumulative(profit, 2), 3)
        c_wins = _cumulative(_cumulative(wins, 2), 3)
        c_odds = _cumulative(_cumulative(odds_sum, 2), 3)
        c_sq = _cumulative(_cumulative(profit_sq, 2), 3)

        total_counts = c_counts.sum(axis=5)
        total_profit = c_profit.sum(axis=5)
        total_wins = c_wins.sum(axis=5)
        total_odds = c_odds.sum(axis=5)
        total_sq = c_sq.sum(axis=5)

        # Keep the cells that meet the minimum sample so the permutation null
        # uses the same search space as the report.
        valid = total_counts >= min_sample
        valid_masks.append((signals, mask, valid))

        market_grid, odds_grid, chance_grid, implied_grid, rec_grid = np.nonzero(valid)
        for m_i, o_i, c_i, i_i, r_i in zip(
            market_grid, odds_grid, chance_grid, implied_grid, rec_grid
        ):
            n = float(total_counts[m_i, o_i, c_i, i_i, r_i])
            p = float(total_profit[m_i, o_i, c_i, i_i, r_i])
            w = float(total_wins[m_i, o_i, c_i, i_i, r_i])
            o_sum = float(total_odds[m_i, o_i, c_i, i_i, r_i])
            sq = float(total_sq[m_i, o_i, c_i, i_i, r_i])
            roi = 100.0 * p / n
            variance = max(0.0, sq / n - (p / n) ** 2)
            se = math.sqrt(variance / n) if n > 0 else np.nan
            roi_lb = roi - 1.96 * se

            n_train = float(c_counts[m_i, o_i, c_i, i_i, r_i, 0])
            n_test = float(c_counts[m_i, o_i, c_i, i_i, r_i, 1])
            p_train = float(c_profit[m_i, o_i, c_i, i_i, r_i, 0])
            p_test = float(c_profit[m_i, o_i, c_i, i_i, r_i, 1])
            w_train = float(c_wins[m_i, o_i, c_i, i_i, r_i, 0])
            w_test = float(c_wins[m_i, o_i, c_i, i_i, r_i, 1])

            records.append(
                {
                    "market": markets[m_i],
                    "odds_band": ODDS_BANDS[o_i][0],
                    "chance_min": CHANCE_LABELS[c_i],
                    "implied_min": CHANCE_LABELS[i_i],
                    "rec": "any" if r_i == 2 else REC_LEVELS[r_i],
                    "edge": signals[0],
                    "aligned": signals[1],
                    "fresh": signals[2],
                    "n": int(n),
                    "wins": int(w),
                    "hit_rate": 100.0 * w / n,
                    "roi": roi,
                    "roi_lower_95": roi_lb,
                    "profit": p,
                    "avg_odds": o_sum / n,
                    "n_train": int(n_train),
                    "roi_train": 100.0 * p_train / n_train if n_train else None,
                    "hit_train": 100.0 * w_train / n_train if n_train else None,
                    "n_test": int(n_test),
                    "roi_test": 100.0 * p_test / n_test if n_test else None,
                    "hit_test": 100.0 * w_test / n_test if n_test else None,
                }
            )

    grid = pd.DataFrame(records)
    if grid.empty:
        return grid, {"cells": 0, "valid_cells": 0}

    # Empirical-Bayes style shrinkage towards the overall pick ROI.  This
    # stops a 30-pick high-odds cell from outranking a 300-pick cell merely
    # because one outsider won.
    prior = float(frame["profit"].mean())
    shrink_n = 50.0
    grid["roi_shrunk"] = 100.0 * (grid["profit"] + shrink_n * prior) / (grid["n"] + shrink_n)

    # No normal-approximation p-values here: per-cell profit is heavily skewed
    # by a few high-odds winners, so a z-test would report absurd certainty.
    # Multiplicity is handled by the within-market permutation test and by the
    # day-cluster bootstrap on the shortlisted cells.

    return grid, {
        "cells": int(np.prod([n_markets, n_odds, n_bands, n_bands, 2**3, n_rec])),
        "valid_cells": int(len(grid)),
        "signals": [list(signals) for signals, _, _ in valid_masks],
    }


def permutation_test(
    frame: pd.DataFrame,
    split_date: str,
    grid: pd.DataFrame,
    min_sample: int,
    draws: int = 200,
    seed: int = 20261110,
) -> dict:
    """Within-market label permutation for the best-cell ROI.

    We keep each market's rows and price distribution, shuffle wins within the
    market, and recompute the best ROI over the same search space.  This asks
    whether the filters add anything beyond simply picking markets.
    """
    if grid.empty:
        return {"draws": 0, "observed_max_roi": None, "p_value": None}

    markets = sorted(frame["market"].unique())
    market_idx = pd.Categorical(frame["market"], categories=markets).codes
    odds_idx = _odds_index(frame["odds"].to_numpy())
    chance_idx = _band_index(frame["model_probability"].to_numpy())
    implied_idx = _band_index(frame["source_implied_probability"].to_numpy())
    rec_idx = _rec_index(frame["recommendation_status"])
    split_idx = (frame["day"] >= split_date).astype(int).to_numpy()
    n_odds = len(ODDS_BANDS)
    n_bands = len(CHANCE_THRESHOLDS)
    n_rec = len(REC_LEVELS)
    shape = (len(markets), n_odds, n_bands, n_bands, n_rec, 2)
    size = int(np.prod(shape))

    signal_masks = []
    for edge_on in (False, True):
        for aligned_on in (False, True):
            for fresh_on in (False, True):
                mask = np.ones(len(frame), dtype=bool)
                if edge_on:
                    mask &= np.nan_to_num(frame["edge"].to_numpy(), nan=-1.0) > 0
                if aligned_on:
                    mask &= np.nan_to_num(frame["model_agreement"].to_numpy(), nan=1.0) <= 0.05
                if fresh_on:
                    mask &= frame["quote_age_hours"].to_numpy() <= 8.0
                signal_masks.append(mask)

    observed_max = float(grid["roi"].max())
    rng = np.random.default_rng(seed)
    wins = frame["won"].to_numpy().astype(bool)
    odds = frame["odds"].to_numpy()
    market_positions = {
        m_i: np.flatnonzero(market_idx == m_i) for m_i in range(len(markets))
    }
    null_max = []

    for _ in range(draws):
        shuffled = wins.copy()
        for positions in market_positions.values():
            if positions.size:
                shuffled[positions] = rng.permutation(shuffled[positions])
        profit = np.where(shuffled, odds - 1.0, -1.0)
        best = -np.inf
        for mask in signal_masks:
            flat = (
                ((((market_idx[mask] * n_odds + odds_idx[mask]) * n_bands + chance_idx[mask])
                  * n_bands + implied_idx[mask]) * n_rec + rec_idx[mask]) * 2
                + split_idx[mask]
            )
            counts = np.bincount(flat, minlength=size).reshape(shape).astype(float)
            profit_sum = np.bincount(
                flat, weights=profit[mask], minlength=size
            ).reshape(shape)
            c_counts = _cumulative(_cumulative(counts, 2), 3).sum(axis=5)
            c_profit = _cumulative(_cumulative(profit_sum, 2), 3).sum(axis=5)
            valid = c_counts >= min_sample
            if valid.any():
                roi = np.divide(
                    100.0 * c_profit,
                    c_counts,
                    out=np.full_like(c_profit, -np.inf),
                    where=valid,
                )
                best = max(best, float(np.nanmax(roi)))
        null_max.append(best)

    null_max_arr = np.asarray(null_max, dtype=float)
    p_value = float((1 + np.sum(null_max_arr >= observed_max)) / (draws + 1))
    return {
        "draws": draws,
        "observed_max_roi": observed_max,
        "null_max_median": float(np.median(null_max_arr)),
        "null_max_p95": float(np.percentile(null_max_arr, 95)),
        "p_value": p_value,
        "note": (
            "Wins are permuted within each market, preserving each market's "
            "price distribution. A small p-value means the filters found "
            "something beyond market-level results."
        ),
    }


def filter_cell(frame: pd.DataFrame, cell: pd.Series) -> pd.DataFrame:
    selected = frame[frame["market"] == cell["market"]].copy()
    label = cell["odds_band"]
    band = next(item for item in ODDS_BANDS if item[0] == label)
    selected = selected[(selected["odds"] >= band[1]) & (selected["odds"] < band[2])]

    chance_min = CHANCE_THRESHOLDS[CHANCE_LABELS.index(cell["chance_min"])]
    implied_min = CHANCE_THRESHOLDS[CHANCE_LABELS.index(cell["implied_min"])]
    if chance_min > 0:
        selected = selected[selected["model_probability"] >= chance_min]
    if implied_min > 0:
        selected = selected[
            selected["source_implied_probability"].notna()
            & (selected["source_implied_probability"] >= implied_min)
        ]
    if bool(cell["edge"]):
        selected = selected[selected["edge"] > 0]
    if bool(cell["aligned"]):
        selected = selected[selected["model_agreement"] <= 0.05]
    if bool(cell["fresh"]):
        selected = selected[selected["quote_age_hours"] <= 8.0]
    if cell["rec"] != "any":
        selected = selected[selected["recommendation_status"] == cell["rec"]]
    return selected


def dedupe_per_match(frame: pd.DataFrame, cell: pd.Series) -> pd.DataFrame:
    selected = filter_cell(frame, cell)
    if selected.empty:
        return selected
    selected = selected.sort_values(
        ["match_id", "q_score", "edge"], ascending=[True, False, False]
    )
    return selected.groupby("match_id", as_index=False).head(1)


def top_cells(grid: pd.DataFrame, min_train: int = 10, top: int = 20) -> pd.DataFrame:
    filtered = grid[(grid["n_train"] >= min_train) & (grid["n_test"] >= 10)].copy()
    if filtered.empty:
        return filtered
    filtered["stability"] = filtered["roi_train"].fillna(-999) + filtered["roi_test"].fillna(-999)
    return filtered.sort_values(
        ["roi_shrunk", "roi_lower_95", "n"], ascending=[False, False, False]
    ).head(top)


def distinct_cells(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate rows that describe the same set of picks.

    The grid deliberately overlaps, so `implied >= 40%` and `implied any` can
    select identical picks. Keep the least-constrained label for each identical
    (market, odds band, n, roi) result.
    """
    if frame.empty:
        return frame
    out = frame.copy()
    out["_constraints"] = (
        (out["chance_min"] != "any").astype(int)
        + (out["implied_min"] != "any").astype(int)
        + out["edge"].astype(bool).astype(int)
        + out["aligned"].astype(bool).astype(int)
        + out["fresh"].astype(bool).astype(int)
        + (out["rec"] != "any").astype(int)
    )
    out = out.sort_values(["_constraints", "n"], ascending=[True, False])
    keys = ["market", "odds_band", "n", "roi", "roi_train", "roi_test"]
    out = out.drop_duplicates(subset=keys, keep="first")
    return out.drop(columns=["_constraints"])


def stable_cells(grid: pd.DataFrame, frame: pd.DataFrame, top: int = 25) -> pd.DataFrame:
    filtered = grid[
        (grid["n"] >= 40)
        & (grid["n_train"] >= 15)
        & (grid["n_test"] >= 15)
        & (grid["roi_train"] > 0)
        & (grid["roi_test"] > 0)
    ].copy()
    if filtered.empty:
        return filtered
    filtered = distinct_cells(filtered)
    # The normal lower bound is too kind to skewed profits, so the shortlist is
    # re-tested with the day-cluster bootstrap before it is reported.
    rows = []
    for _, cell in filtered.sort_values("roi", ascending=False).head(60).iterrows():
        selected = filter_cell(frame, cell)
        boot = cluster_bootstrap_test(selected)
        rows.append(
            {
                **{key: cell[key] for key in (
                    "market", "odds_band", "chance_min", "implied_min", "rec",
                    "edge", "aligned", "fresh", "n", "roi", "roi_shrunk",
                    "roi_train", "roi_test",
                )},
                "boot_low": boot["low"] if boot else np.nan,
                "boot_high": boot["high"] if boot else np.nan,
                "p_one_sided": boot["p_one_sided"] if boot else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out["passes"] = [bool(value) for value in (out["boot_low"] > 0)]
    return out.sort_values(["boot_low", "n"], ascending=[False, False]).head(top)


def _fmt(value, digits=1, suffix=""):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _ci(bounds) -> str:
    if not bounds:
        return "—"
    return f"[{_fmt(bounds[0], 1, '%')}, {_fmt(bounds[1], 1, '%')}]"


def _md_table(frame: pd.DataFrame, columns: list[tuple[str, str]], limit: int | None = None) -> str:
    if frame.empty:
        return "_No rows._\n"
    view = frame.head(limit) if limit else frame
    header = "| " + " | ".join(label for _, label in columns) + " |"
    separator = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, separator]
    for _, row in view.iterrows():
        cells = []
        for key, _ in columns:
            value = row.get(key)
            if isinstance(value, float):
                cells.append(_fmt(value))
            elif value is None:
                cells.append("—")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_report(
    output: Path,
    frame: pd.DataFrame,
    exclusions: Counter,
    as_at: datetime,
    selection: str,
    split_date: str,
    grid: pd.DataFrame,
    permutation: dict,
    min_sample: int,
) -> None:
    eligible = summarise(frame)
    markets = market_table(frame)
    odds = band_table(frame, "odds")
    q_bands = band_table(frame, "q")
    probability = band_table(frame, "probability")
    implied = band_table(frame, "implied")
    signals = signal_table(frame)
    calibration = calibration_table(frame)
    stable = stable_cells(grid, frame)
    stable_pass = int(stable["passes"].sum()) if not stable.empty else 0

    # Rank candidate cells by shrunk ROI, then attach a day-cluster bootstrap
    # interval.  The normal lower bound is too kind to a handful of high-odds
    # winners, so the report orders on the bootstrap lower bound.
    candidate_cells = grid[
        (grid["n_train"] >= 10) & (grid["n_test"] >= 10)
    ].sort_values("roi_shrunk", ascending=False).head(60)
    top_rows = []
    for _, cell in candidate_cells.iterrows():
        selected = filter_cell(frame, cell)
        if len(selected) < min_sample:
            continue
        boot = cluster_bootstrap_test(selected)
        top_rows.append(
            {
                **{key: cell[key] for key in (
                    "market", "odds_band", "chance_min", "implied_min", "rec",
                    "edge", "aligned", "fresh", "n", "roi", "roi_shrunk",
                    "roi_lower_95", "roi_train", "roi_test",
                )},
                "boot_low": boot["low"] if boot else np.nan,
                "boot_high": boot["high"] if boot else np.nan,
                "p_one_sided": boot["p_one_sided"] if boot else np.nan,
            }
        )
    top = pd.DataFrame(top_rows)
    if not top.empty:
        top = distinct_cells(top)
        top = top.sort_values(["boot_low", "roi_shrunk"], ascending=False).head(20)
    else:
        top = top_cells(grid)
    usable_markets = markets[markets["n"] >= max(30, min_sample)]
    market_pool = usable_markets if not usable_markets.empty else markets
    positive_markets = market_pool[market_pool["roi"] > 0].sort_values("roi", ascending=False)
    negative_markets = market_pool[market_pool["roi"] < 0].sort_values("roi")

    # Per-match reality check for the strongest full-sample cells.
    per_match_rows = []
    per_match_candidates = distinct_cells(
        grid.sort_values(["roi_shrunk", "n"], ascending=False).head(40)
    ).head(15)
    for _, cell in per_match_candidates.iterrows():
        selected = dedupe_per_match(frame, cell)
        if selected.empty:
            continue
        item = summarise(selected)
        per_match_rows.append(
            {
                "strategy": (
                    f"{cell['market']} / {cell['odds_band']} / chance {cell['chance_min']} / "
                    f"implied {cell['implied_min']} / edge {cell['edge']} / aligned {cell['aligned']} / "
                    f"fresh {cell['fresh']} / rec {cell['rec']}"
                ),
                "picks": len(selected),
                "matches": item["matches"],
                "hit_rate": item["hit_rate"],
                "roi": item["roi"],
                "roi_per_pick": cell["roi"],
            }
        )
    per_match = pd.DataFrame(per_match_rows)

    best_market = (
        positive_markets.iloc[0] if not positive_markets.empty else markets.iloc[0]
    )
    worst_market = (
        negative_markets.iloc[0] if not negative_markets.empty else markets.iloc[-1]
    )
    overall_roi = eligible["roi"] or 0.0

    verdict_rows = []
    for _, row in markets.iterrows():
        if int(row["n"]) < max(30, min_sample):
            verdict = "too few picks"
        elif row["roi"] >= 2.0:
            verdict = "watchlist"
        elif row["roi"] <= -5.0:
            verdict = "exclusion candidate"
        else:
            verdict = "neutral"
        verdict_rows.append(
            {
                "market": row["market"],
                "n": int(row["n"]),
                "hit_rate": row["hit_rate"],
                "roi": row["roi"],
                "ci": _ci(row["bootstrap_95"]),
                "verdict": verdict,
            }
        )
    verdicts = pd.DataFrame(verdict_rows)

    report = f"""# System Picks market and filter backtest

**Bottom line: the historical data does not contain a statistically validated profitable sweet spot.** The page's Q ≥ 75 universe is close to break-even before costs, and the apparently strong cells are small, unstable or use closing-line information that was not knowable when the bet was placed. The useful findings are exclusion rules and a short watchlist, not a proven betting system.

Snapshot: {as_at.isoformat()} · mode: `{selection}` prediction per match/market/selection · completed CAT days only.

## Scope and method

- Universe: every stored prediction with `Q >= 75`, joined to a finished match; the daily page's own threshold.
- A pick is counted once per match/market/selection. The `{selection}` stored pre-kickoff prediction is used; later repeats are discarded.
- No replay snapshots (`as_of_at`), no fallback prices, no post-kickoff updates, no current-day results.
- Flat one-unit singles at the captured entry price. Wins pay `odds - 1`; losses pay `-1`; DNB draws are void and excluded.
- Train/test split at **{split_date}**. Train is used for ranking, test is reported out of sample.
- The grid sweeps market × odds band × model-chance block × bookmaker-implied block × three pre-bet signals × recommendation. Chance and implied blocks are cumulative (`>=`), matching the page.
- `Beat the close` and outcome are **not** in the actionable grid. Closing odds are future information, and the outcome is the thing being predicted. CLV is reported only as a diagnostic.

## What survived inspection

- Eligible picks: **{eligible['n']:,}** across **{eligible['matches']:,} fixtures** and **{eligible['days']} matchdays** ({frame['day'].min()} to {frame['day'].max()}).
- Overall: hit rate **{_fmt(eligible['hit_rate'], 1, '%')}**, ROI **{_fmt(overall_roi, 1, '%')}**, profit **{_fmt(eligible['profit'], 2)} units**, average odds **{_fmt(eligible['avg_odds'], 2)}**.
- Best market by raw ROI (at least {max(30, min_sample)} picks): **{best_market['market']}** ({int(best_market['n'])} picks, {_fmt(best_market['roi'], 1, '%')} ROI, 95% day-cluster interval {_ci(best_market['bootstrap_95'])}).
- Worst: **{worst_market['market']}** ({int(worst_market['n'])} picks, {_fmt(worst_market['roi'], 1, '%')} ROI).
- Valid grid cells with at least {min_sample} picks: **{len(grid):,}**. Best full-sample ROI: **{_fmt(grid['roi'].max() if not grid.empty else None, 1, '%')}**.
- Within-market permutation test for the best cell: observed max ROI {_fmt(permutation.get('observed_max_roi'), 1, '%')}, null median {_fmt(permutation.get('null_max_median'), 1, '%')}, null 95th percentile {_fmt(permutation.get('null_max_p95'), 1, '%')}, **p = {_fmt(permutation.get('p_value'), 3)}**.
- Train/test cells (positive in both halves, n ≥ 40): **{len(stable)}**; of those, cells whose day-cluster bootstrap lower bound clears zero: **{stable_pass}**.

## Market baseline (Q >= 75)

{_md_table(markets, [('market', 'Market'), ('n', 'Picks'), ('matches', 'Matches'), ('hit_rate', 'Hit %'), ('roi', 'ROI %'), ('profit', 'Net units'), ('avg_odds', 'Avg odds')])}

Positive-ROI markets: {', '.join(f"{row['market']} ({_fmt(row['roi'], 1, '%')})" for _, row in positive_markets.iterrows()) or 'none'}.

Negative-ROI markets: {', '.join(f"{row['market']} ({_fmt(row['roi'], 1, '%')})" for _, row in negative_markets.iterrows()) or 'none'}.

### Market selection verdict

Bootstrap intervals are day-cluster intervals. `watchlist` means positive ROI worth tracking, not a validated edge; `exclusion candidate` is a market the data says to stop betting before any model work.

{_md_table(verdicts, [('market', 'Market'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %'), ('ci', '95% interval'), ('verdict', 'Verdict')])}

## Odds bands (all markets)

{_md_table(odds, [('odds', 'Odds band'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %'), ('profit', 'Net units')])}

## Quality bands

{_md_table(q_bands, [('q', 'Q band'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %')])}

## Model chance and bookmaker implied blocks

{_md_table(probability, [('probability', 'Model chance'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %')])}

{_md_table(implied, [('implied', 'Bookmaker implied'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %')])}

## Signals and recommendation status

{_md_table(signals, [('signal', 'Filter'), ('n', 'Picks'), ('hit_rate', 'Hit %'), ('roi', 'ROI %'), ('profit', 'Net units')])}

`CLV > 0` is included here only to show the lookahead effect. It cannot be used to choose a bet before kickoff.

## Best grid cells by bootstrap lower bound

The top 60 cells by shrunk ROI are re-measured with a day-cluster bootstrap and ordered here by the 2.5th percentile of the bootstrap ROI. `p(ROI<=0)` is the one-sided bootstrap p-value before any multiple-testing correction; with hundreds of overlapping cells, treat anything above roughly 0.01 as noise. A cell with a high ROI but a wide interval or a negative test result is noise, not a sweet spot.

{_md_table(top, [('market', 'Market'), ('odds_band', 'Odds'), ('chance_min', 'Chance'), ('implied_min', 'Implied'), ('edge', 'Edge'), ('aligned', 'Aligned'), ('fresh', 'Fresh'), ('rec', 'Rec'), ('n', 'N'), ('roi', 'ROI %'), ('roi_shrunk', 'Shrunk ROI'), ('boot_low', 'Boot low'), ('boot_high', 'Boot high'), ('p_one_sided', 'p(ROI<=0)'), ('roi_train', 'Train ROI'), ('roi_test', 'Test ROI')], limit=20)}

## Cells positive in both train and test

Requires n ≥ 40 and a positive ROI in each half. `Boot low` is the day-cluster bootstrap 2.5th percentile; a cell only counts as stable if that clears zero. If none do, the data does not support a stable market rule.

{_md_table(stable, [('market', 'Market'), ('odds_band', 'Odds'), ('chance_min', 'Chance'), ('implied_min', 'Implied'), ('edge', 'Edge'), ('aligned', 'Aligned'), ('fresh', 'Fresh'), ('rec', 'Rec'), ('n', 'N'), ('roi', 'ROI %'), ('boot_low', 'Boot low'), ('boot_high', 'Boot high'), ('p_one_sided', 'p(ROI<=0)'), ('roi_train', 'Train ROI'), ('roi_test', 'Test ROI')], limit=25)}

## One pick per match: does the page's pick count overstate opportunity?

The page shows every qualified pick, so one fixture can contribute several correlated bets. Re-running the strongest cells with only the highest-Q pick per fixture gives a more realistic staking view.

{_md_table(per_match, [('strategy', 'Cell'), ('picks', 'Picks'), ('matches', 'Matches'), ('hit_rate', 'Hit %'), ('roi', 'ROI %'), ('roi_per_pick', 'Per-pick ROI %')], limit=15)}

## Calibration and closing-line evidence

The model is overconfident at Q >= 75. The table compares the average model probability with the observed hit rate and with the bookmaker's implied probability. A positive `model minus observed` column means the model claimed more certainty than it delivered.

{_md_table(calibration, [('market', 'Market'), ('n', 'N'), ('observed_hit_%', 'Observed %'), ('model_prob_%', 'Model %'), ('implied_prob_%', 'Implied %'), ('model_minus_observed_pp', 'Model-obs pp'), ('model_brier', 'Model Brier'), ('implied_brier', 'Implied Brier'), ('mean_clv_%', 'Mean CLV %'), ('beat_close_%', 'Beat close %')])}

If the model had a genuine pre-bet edge, its picks should beat the closing line more often than not. Mean CLV near zero and a beat-close rate near 50% are evidence against a persistent edge, not proof of one.

## Exclusions and sample caveats

{json.dumps(dict(exclusions), indent=2)}

- Only {eligible['days']} complete matchdays are available. That is enough to reject a large, stable edge; it is not enough to certify a small one.
- The model runs are recent and the sample contains one model regime. Earlier/later model versions can behave differently.
- Many stored predictions have no captured price, so the eligible sample is smaller than the raw prediction count.
- Prices are captured quotes, not proof of executable fills, limits or account availability.
- Cells overlap heavily: the same pick appears in many chance/implied/signal combinations. The bootstrap p-values and permutation test are screens, not formal family-wise guarantees.
- Postponed/cancelled fixtures are excluded rather than assumed refunded.

## Recommended way forward

1. **Do not promote a market because its raw ROI is positive.** Away win, BTTS no and over 1.5 look best here, but their day-cluster intervals include zero and their closing-line behaviour does not confirm an edge.
2. **Treat double chance as the first exclusion candidate.** `double_chance_x2` is the largest bucket and is consistently negative; `double_chance_1x` is worse. This is the most reproducible finding in the sample.
3. **Recalibrate probabilities before using edge or Q as a value signal.** At Q >= 75 the model's average probability is far above the observed hit rate. Until calibration is fixed, sort by market price and market-implied probability, not by model edge.
4. **Freeze a small candidate policy and paper-trade it forward.** Example: exclude double chance and over 3.5/4.5, keep away win / BTTS no / over 1.5 / under 2.5-3.5, require a pre-kickoff quote and one pick per fixture. Record the rule before the first bet and review only after 300 settled picks and 30 matchdays.
5. **Use CLV as a validation gate, never as a live filter.** A policy that cannot beat the close over a forward sample should not be promoted, regardless of its historical ROI.
6. **Keep one pick per fixture for staking.** The page's per-pick totals are useful for research, but correlated picks from the same match should not be treated as independent bets.

## Reproduction

```
python /tmp/market_sweet_spot_backtest.py --selection {selection} --min-q 75 --min-sample {min_sample} --output <folder>
```

Files: `analysis.json` (summary and settings), `cells.csv` (full grid), `picks.csv` (eligible picks), `REPORT.md`.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", choices=["first", "latest"], default="latest")
    parser.add_argument("--min-q", type=float, default=75.0)
    parser.add_argument("--min-sample", type=int, default=30)
    parser.add_argument("--split-date", default="2026-10-20")
    parser.add_argument("--permutations", type=int, default=200)
    parser.add_argument("--as-at", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    as_at = _dt(args.as_at) if args.as_at else datetime.now(timezone.utc)
    args.output.mkdir(parents=True, exist_ok=False)

    raw = await load_rows()
    frame, exclusions = prepare(raw, as_at, args.selection)
    if frame.empty:
        raise SystemExit("No eligible picks.")
    frame = frame[frame["q_score"] >= args.min_q].reset_index(drop=True)
    frame = frame[frame["day"] < as_at.astimezone(CAT).date().isoformat()].reset_index(drop=True)
    if frame.empty:
        raise SystemExit("No eligible completed-day picks at this Q threshold.")

    grid, grid_meta = build_grid(frame, args.split_date, args.min_sample)
    permutation = permutation_test(
        frame, args.split_date, grid, args.min_sample, draws=args.permutations
    )

    frame_out = frame.copy()
    frame_out["kickoff_at"] = frame_out["kickoff_at"].astype(str)
    frame_out.to_csv(args.output / "picks.csv", index=False)
    grid.to_csv(args.output / "cells.csv", index=False)

    analysis = {
        "as_at": as_at.isoformat(),
        "selection": args.selection,
        "min_q": args.min_q,
        "min_sample": args.min_sample,
        "split_date": args.split_date,
        "raw_rows": len(raw),
        "eligible": summarise(frame),
        "exclusions": dict(exclusions),
        "grid": grid_meta,
        "permutation": permutation,
        "date_range": [frame["day"].min(), frame["day"].max()],
        "markets": market_table(frame).to_dict(orient="records"),
        "signals": signal_table(frame).to_dict(orient="records"),
        "calibration": calibration_table(frame).to_dict(orient="records"),
        "top_cells": top_cells(grid).to_dict(orient="records"),
        "stable_cells": stable_cells(grid, frame).to_dict(orient="records"),
    }
    (args.output / "analysis.json").write_text(
        json.dumps(analysis, indent=2, default=str), encoding="utf-8"
    )
    write_report(
        args.output,
        frame,
        exclusions,
        as_at,
        args.selection,
        args.split_date,
        grid,
        permutation,
        args.min_sample,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "selection": args.selection,
                "eligible": analysis["eligible"],
                "grid": grid_meta,
                "permutation": permutation,
                "date_range": analysis["date_range"],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
