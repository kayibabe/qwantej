"""Read-only bookmaker price audit for the Q>=75 first-pick universe.

The Q>=75 research argues the model has no information beyond the price and
that the only reliable lever left is the price actually obtained.  This audit
tests that lever directly:

    At the moment the entry price was recorded, was it already the best price
    quoted across the tracked bookmakers, and what would perfect line-shopping
    have added?

The entry price (`predictions.source_decimal_odds`) is already
``max(odds.decimal_odds)`` across the bookmaker rows for that market, so the
expected answer is "almost always yes".  Measuring it is still worth doing: it
either confirms the lever is exhausted or quantifies the remaining gap, and it
replaces the earlier attempt to benchmark against Betway, which has no rows in
`odds` or `odds_snapshots`.

Quotes are taken from `odds_snapshots` at or before the recorded entry
timestamp, within a bounded lookback, so the comparison is strictly
no-lookahead and like-for-like in time.

Run inside the backend container:
    python scripts/bookmaker_price_audit.py --out /tmp/bookmaker_audit
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.database import AsyncSessionLocal
from market_sweet_spot_backtest import load_rows, prepare

Q_MIN = 75.0
QUOTE_LOOKBACK = pd.Timedelta(hours=3)
DRAWS = 2000
SEED = 20261111


SNAPSHOT_QUERY = text(
    """
    SELECT match_id, bookmaker, market, selection, decimal_odds, captured_at
    FROM odds_snapshots
    WHERE match_id = ANY(:match_ids) AND decimal_odds > 1
    """
)


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


def entry_quotes(
    frame: pd.DataFrame, entries: dict[int, datetime], snaps: pd.DataFrame
) -> pd.DataFrame:
    """Last quote per bookmaker at or before the entry timestamp."""
    picks = frame[["prediction_id", "match_id", "market", "selection"]].copy()
    picks["entry_at"] = pd.to_datetime(picks["prediction_id"].map(entries), utc=True)
    merged = picks.merge(snaps, on=["match_id", "market", "selection"])
    age = merged["entry_at"] - merged["captured_at"]
    fresh = merged[(age >= pd.Timedelta(0)) & (age <= QUOTE_LOOKBACK)]
    return fresh.sort_values("captured_at").drop_duplicates(
        ["prediction_id", "bookmaker"], keep="last"
    )


def profit_of(price: np.ndarray, won: np.ndarray) -> np.ndarray:
    return np.where(won, price - 1.0, -1.0)


def day_bootstrap_ci(values: np.ndarray, days: np.ndarray) -> list[float] | None:
    if len(values) == 0:
        return None
    grouped = pd.DataFrame({"v": values, "d": days}).groupby("d")["v"].agg(["sum", "count"])
    sums, counts = grouped["sum"].to_numpy(), grouped["count"].to_numpy()
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(sums), size=(DRAWS, len(sums)))
    stats = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def book_comparison(frame: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    won = frame["won"].to_numpy()
    days = frame["day"].to_numpy()
    source = frame["odds"].to_numpy()
    rows = []
    for book in prices.columns:
        price = prices[book].to_numpy()
        mask = ~np.isnan(price)
        if mask.sum() < 30:
            continue
        p_book, w, d, src = price[mask], won[mask], days[mask], source[mask]
        diff = profit_of(p_book, w) - profit_of(src, w)
        rows.append(
            {
                "bookmaker": book,
                "picks": int(mask.sum()),
                "avg_price_vs_source_pct": float(np.mean(p_book / src - 1.0) * 100),
                "share_better_than_source_pct": float(np.mean(p_book > src + 1e-9) * 100),
                "roi_at_book_pct": float(np.mean(profit_of(p_book, w)) * 100),
                "roi_vs_source_pp": float(np.mean(diff) * 100),
                "roi_vs_source_ci_pp": [x * 100 for x in day_bootstrap_ci(diff, d)],
            }
        )
    return pd.DataFrame(rows).sort_values("avg_price_vs_source_pct", ascending=False)


def policy_comparison(frame: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    source = frame["odds"].to_numpy()
    won = frame["won"].to_numpy()
    days = frame["day"].to_numpy()
    source_profit = profit_of(source, won)
    candidates = {
        "recorded entry price": source,
        "best quoted at entry": prices.max(axis=1).to_numpy(),
        "median quoted at entry": prices.median(axis=1).to_numpy(),
    }
    rows = []
    for name, price in candidates.items():
        mask = ~np.isnan(price)
        profit = profit_of(price[mask], won[mask])
        paired = profit - source_profit[mask]
        rows.append(
            {
                "policy": name,
                "n": int(mask.sum()),
                "avg_price": float(np.mean(price[mask])),
                "roi_pct": float(np.mean(profit) * 100),
                "roi_ci_pct": [x * 100 for x in day_bootstrap_ci(profit, days[mask])],
                "roi_vs_recorded_pp": float(np.mean(paired) * 100),
                "roi_vs_recorded_ci_pp": [x * 100 for x in day_bootstrap_ci(paired, days[mask])],
            }
        )
    return pd.DataFrame(rows)


def md_table(frame: pd.DataFrame) -> str:
    def cell(value) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(f"{x:.2f}" for x in value) + "]" if value else "n/a"
        if isinstance(value, (float, np.floating)):
            return "n/a" if np.isnan(value) else f"{value:.2f}"
        return str(value)

    header = "| " + " | ".join(frame.columns) + " |"
    divider = "|" + "|".join("---" for _ in frame.columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join([header, divider, *body])


def write_outputs(out: Path, summary: dict, books: pd.DataFrame, policies: pd.DataFrame) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    books.to_csv(out / "book_comparison.csv", index=False)
    policies.to_csv(out / "policy_comparison.csv", index=False)
    report = [
        "# Bookmaker price audit (Q>=75 first picks)",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "Question: at the moment the entry price was recorded, was it already "
        "the best price available across the tracked bookmakers?",
        "",
        "## Coverage",
        "```json",
        json.dumps(summary["coverage"], indent=2, default=str),
        "```",
        "",
        "## Each book vs the recorded entry price, same picks",
        md_table(books),
        "",
        "## Pricing policy comparison",
        md_table(policies),
        "",
        "## Caveats",
        "- Quotes are the last snapshot per bookmaker at or before the recorded "
        f"entry timestamp, within {QUOTE_LOOKBACK.components.hours}h. This is a "
        "pre-entry comparison, not a closing-line measure.",
        "- `odds_snapshots` is not one capture per combo: 64,520 of 341,218 "
        "combos have two or more captures, so a bounded lookback is available.",
        "- Best-quoted-price assumes the same stake is placeable at the best "
        "book; stake limits, account restrictions and live availability are not modelled.",
        "- Betway is absent from both `odds` and `odds_snapshots`, so it cannot "
        "be benchmarked. The comparison is best-available vs recorded across the "
        "10 tracked books.",
        "- The sample is the sweet-spot first-pick universe, which is already "
        "negative ROI at the recorded price; this measures price capture, not edge.",
        "",
    ]
    (out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    as_at = datetime.now(timezone.utc)
    rows = await load_rows()
    frame, exclusions = prepare(rows, as_at, "first")
    universe = frame[frame["q_score"] >= Q_MIN].reset_index(drop=True)
    entries = {
        int(r["prediction_id"]): r["source_odds_at"]
        for r in rows
        if r.get("source_odds_at") is not None
    }

    snaps = await load_snapshots(sorted(universe["match_id"].unique().tolist()))
    if snaps.empty:
        raise SystemExit("No snapshots for the Q>=75 universe.")

    quotes = entry_quotes(universe, entries, snaps)
    prices = quotes.pivot(index="prediction_id", columns="bookmaker", values="decimal_odds")
    frame = (
        universe[universe["prediction_id"].isin(prices.index)]
        .set_index("prediction_id")
        .loc[prices.index]
        .reset_index()
    )
    prices = prices.loc[frame["prediction_id"]]

    source = frame["odds"].to_numpy()
    price_matrix = prices.to_numpy()
    best = prices.max(axis=1).to_numpy()
    coverage = {
        "q_min": Q_MIN,
        "eligible_q75_picks": int(len(universe)),
        "prepare_exclusions": dict(exclusions),
        "picks_with_entry_quote": int(len(frame)),
        "avg_books_per_pick": float(prices.notna().sum(axis=1).mean()),
        "picks_with_3plus_books": int((prices.notna().sum(axis=1) >= 3).sum()),
        "recorded_price_equals_best_pct": float(np.mean(np.isclose(best, source, atol=1e-9)) * 100),
        "recorded_price_below_best_pct": float(np.mean(best > source + 1e-9) * 100),
        "bookmakers_in_snapshots": sorted(snaps["bookmaker"].unique().tolist()),
    }
    summary = {
        "generated_at": as_at.isoformat(),
        "coverage": coverage,
        "quote_lookback_hours": QUOTE_LOOKBACK.components.hours,
    }
    books = book_comparison(frame, prices)
    policies = policy_comparison(frame, prices)
    write_outputs(Path(args.out), summary, books, policies)
    print(md_table(books))
    print(md_table(policies))
    print(json.dumps(coverage, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
