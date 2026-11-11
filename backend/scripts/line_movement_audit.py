"""Does pre-entry line movement carry information beyond the entry price?

The Q>=75 backtests and the calibration walk-forward both say the model has no
information beyond the bookmaker's price.  One signal was never tested because
an earlier review wrongly concluded that ``odds_snapshots`` holds exactly one
capture per selection.  It does not: 64,520 of 341,218 combos have two or more
captures, and about 11,000 settled picks have a quote at least six hours before
the recorded entry price.

This script measures the signed move into the entry price:

    prior  = best price across books at the last capture at least 1h (and at
             most 48h) before the recorded entry timestamp
    entry  = the recorded entry price
    move   = logit(1/entry) - logit(1/prior)     (positive = price shortened)

and then asks whether ``move`` explains the result once the entry price is
known.  Everything is strictly pre-entry: the prior quote predates entry by at
least an hour, and the entry price is the one already stored.

Read-only.  Run inside the backend container:

    python scripts/line_movement_audit.py --out /tmp/line_movement
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sqlalchemy import text

from app.database import AsyncSessionLocal
from market_sweet_spot_backtest import load_rows, prepare

MIN_GAP = pd.Timedelta(hours=1)
MAX_GAP = pd.Timedelta(hours=48)
DRAWS = 2000
SEED = 20261111
QUINTILES = 5


SNAPSHOT_QUERY = text(
    """
    SELECT match_id, bookmaker, market, selection, decimal_odds, captured_at
    FROM odds_snapshots
    WHERE match_id = ANY(:match_ids) AND decimal_odds > 1
    """
)


def _logit(probability):
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


async def load_snapshots(match_ids: list[int]) -> pd.DataFrame:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        rows = (await db.execute(SNAPSHOT_QUERY, {"match_ids": match_ids})).mappings().all()
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        return frame
    frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True)
    frame["decimal_odds"] = frame["decimal_odds"].astype(float)
    return frame


def attach_prior(frame: pd.DataFrame, entries: dict[int, datetime], snaps: pd.DataFrame) -> pd.DataFrame:
    picks = frame[["prediction_id", "match_id", "market", "selection", "odds"]].copy()
    picks["entry_at"] = pd.to_datetime(picks["prediction_id"].map(entries), utc=True)
    merged = picks.merge(snaps, on=["match_id", "market", "selection"])
    gap = merged["entry_at"] - merged["captured_at"]
    eligible = merged[(gap >= MIN_GAP) & (gap <= MAX_GAP)]
    if eligible.empty:
        return pd.DataFrame()

    # Last quote per bookmaker inside the window, then best price across books.
    latest = (
        eligible.sort_values("captured_at")
        .drop_duplicates(["prediction_id", "bookmaker"], keep="last")
    )
    prior = (
        latest.groupby("prediction_id")
        .agg(prior_odds=("decimal_odds", "max"), prior_at=("captured_at", "max"),
             books=("bookmaker", "nunique"))
        .reset_index()
    )
    return picks.merge(prior, on="prediction_id")


def bootstrap_coefficient(view: pd.DataFrame, draws: int = DRAWS) -> dict:
    def fit(frame: pd.DataFrame):
        x = np.column_stack([_logit(1.0 / frame["odds"]), frame["move"]])
        y = frame["won"].astype(int).to_numpy()
        if len(set(y.tolist())) < 2:
            return None
        model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500, random_state=17)
        model.fit(x, y)
        return model.coef_[0]

    base = fit(view)
    if base is None:
        return {"fitted": False}

    days = sorted(view["day"].unique())
    groups = {day: group for day, group in view.groupby("day")}
    rng = np.random.default_rng(SEED)
    samples = []
    for _ in range(draws):
        chosen = rng.choice(days, size=len(days), replace=True)
        frame = pd.concat([groups[day] for day in chosen], ignore_index=True)
        coef = fit(frame)
        if coef is not None:
            samples.append(coef[1])
    if not samples:
        return {"fitted": False}
    arr = np.asarray(samples)
    return {
        "fitted": True,
        "n": int(len(view)),
        "price_coefficient": float(base[0]),
        "move_coefficient": float(base[1]),
        "move_ci_low": float(np.percentile(arr, 2.5)),
        "move_ci_high": float(np.percentile(arr, 97.5)),
        "p_move_le_zero": float((np.sum(arr <= 0.0) + 1) / (len(arr) + 1)),
        "draws": len(arr),
    }


def quintile_table(view: pd.DataFrame) -> pd.DataFrame:
    frame = view.copy()
    frame["band"] = pd.qcut(frame["move"], QUINTILES, labels=False, duplicates="drop")
    rows = []
    for band, group in frame.groupby("band"):
        profit = np.where(group["won"], group["odds"] - 1.0, -1.0)
        rows.append(
            {
                "band": int(band),
                "move_low": float(group["move"].min()),
                "move_high": float(group["move"].max()),
                "n": int(len(group)),
                "hit_rate_pct": float(group["won"].mean() * 100),
                "avg_odds": float(group["odds"].mean()),
                "roi_pct": float(profit.mean() * 100),
                "roi_ci_pct": [x * 100 for x in day_bootstrap_ci(profit, group["day"].to_numpy())],
            }
        )
    return pd.DataFrame(rows)


def day_bootstrap_ci(values: np.ndarray, days: np.ndarray) -> list[float] | None:
    if len(values) == 0:
        return None
    grouped = pd.DataFrame({"v": values, "d": days}).groupby("d")["v"].agg(["sum", "count"])
    sums, counts = grouped["sum"].to_numpy(), grouped["count"].to_numpy()
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(sums), size=(DRAWS, len(sums)))
    stats = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def md_table(frame: pd.DataFrame) -> str:
    def cell(value) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(f"{x:.2f}" for x in value) + "]" if value else "n/a"
        if isinstance(value, (float, np.floating)):
            return "n/a" if np.isnan(value) else f"{value:.3f}"
        return str(value)

    header = "| " + " | ".join(frame.columns) + " |"
    divider = "|" + "|".join("---" for _ in frame.columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join([header, divider, *body])


def build_report(out: Path, summary: dict, view: pd.DataFrame, bands: pd.DataFrame) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    view.to_csv(out / "picks.csv", index=False)
    bands.to_csv(out / "bands.csv", index=False)

    skill = summary["skill"]
    verdict = (
        "no information beyond the entry price"
        if (skill.get("move_ci_low") or 0.0) <= 0.0
        else "possible information beyond the entry price"
    )
    report = f"""# Pre-entry line movement audit

**Question: does the price move into our entry price carry information the entry price does not already contain?**

## Method

- Population: the same strict no-lookahead first-pick universe as the
  sweet-spot report (settled fixtures only, first stored pre-kickoff
  prediction, valid non-fallback odds).
- Prior quote: the last capture per bookmaker at least 1 hour and at most 48
  hours before the recorded entry timestamp, then the best price across books.
- Move: `logit(1/entry_odds) - logit(1/prior_odds)`. Positive means the price
  shortened into our entry; negative means it drifted out.
- Test: `won ~ logit(1/entry_odds) + move`, with matchdays resampled as
  clusters. If the move coefficient interval includes zero, the movement adds
  nothing once the price is known.

## Coverage

- Eligible Q-universe picks with settled results: **{summary['eligible_picks']:,}**
- Picks with a usable prior quote: **{summary['picks_with_prior']:,}**
  ({summary['coverage_pct']:.1f}% of eligible)
- Median books behind the prior quote: **{summary['median_books']:.1f}**

## Result

| Metric | Value |
| --- | --- |
| N | {skill.get('n', 0)} |
| Move coefficient | {skill.get('move_coefficient', float('nan')):.3f} |
| 95% CI | [{skill.get('move_ci_low', float('nan')):.3f}, {skill.get('move_ci_high', float('nan')):.3f}] |
| p(coefficient <= 0) | {skill.get('p_move_le_zero', float('nan')):.3f} |
| Verdict | {verdict} |

## ROI by movement quintile

{md_table(bands)}

## Caveats

- **Structural coverage limit.** Predictions are created a median of ~9 hours
  before kickoff and the first stored pick coincides with the first snapshot,
  so a first pick has no pre-entry price history by construction.  Only later
  pre-kickoff predictions have a measurable prior quote, which is why the
  sample is a pilot rather than a powered test.
- Snapshot coverage is sparse before 2026-09-14 and uneven afterwards.
- The prior quote is "best price across books", so part of the measured move
  can be a change in which bookmaker is best rather than a genuine market move.
- Capture cadence is not fixed; a 1-hour minimum gap is used to avoid comparing
  two near-simultaneous fetches.
- This is a retrospective test on a sample that was not pre-registered. A
  positive result would justify a frozen prospective test, not a live rule.
- Promotion would still require the market-relative and CLV gates in
  `docs/CALIBRATION_AND_POLICY_2026-11-10.md`.
"""
    (out / "REPORT.md").write_text(report, encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--selection", choices=("first", "latest"), default="latest")
    args = parser.parse_args()

    as_at = datetime.now(timezone.utc)
    rows = await load_rows()
    frame, exclusions = prepare(rows, as_at, args.selection)
    entries = {
        int(r["prediction_id"]): r["source_odds_at"]
        for r in rows
        if r.get("source_odds_at") is not None
    }

    snaps = await load_snapshots(sorted(frame["match_id"].unique().tolist()))
    if snaps.empty:
        raise SystemExit("No snapshots for the universe.")

    joined = attach_prior(frame, entries, snaps)
    if joined.empty:
        raise SystemExit("No picks with a prior quote.")

    joined = joined.merge(
        frame[["prediction_id", "won", "day", "q_score"]],
        on="prediction_id",
        how="left",
    )
    joined["move"] = _logit(1.0 / joined["odds"]) - _logit(1.0 / joined["prior_odds"])
    joined = joined.replace([np.inf, -np.inf], np.nan).dropna(subset=["move", "won", "day"])

    summary = {
        "generated_at": as_at.isoformat(),
        "selection_mode": args.selection,
        "min_gap_hours": MIN_GAP.total_seconds() / 3600,
        "max_gap_hours": MAX_GAP.total_seconds() / 3600,
        "eligible_picks": int(len(frame)),
        "picks_with_prior": int(len(joined)),
        "coverage_pct": float(len(joined) / len(frame) * 100) if len(frame) else 0.0,
        "median_books": float(joined["books"].median()) if len(joined) else 0.0,
        "prepare_exclusions": dict(exclusions),
        "skill": bootstrap_coefficient(joined),
        "move_corr_q": float(np.corrcoef(joined["move"], joined["q_score"])[0, 1])
        if len(joined) > 2
        else None,
    }
    bands = quintile_table(joined)
    build_report(Path(args.out), summary, joined, bands)
    print(md_table(bands))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
