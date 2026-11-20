#!/usr/bin/env python3
"""Backtest the five System Picks band-mix pairs, with or without the Q>=75 gate.

This replays strict pre-bet eligibility rules in the style of the System Picks /
market sweet-spot research scripts and keeps only picks whose model probability
and bookmaker-implied probability fall into one of the five saved "band mix"
pairs from the System Picks UI.

Five pairs (model chance % x bookmaker implied %):
  p0: <50    x 85-90
  p1: 50-55  x 90-95
  p2: 55-60  x 95-100
  p3: 60-65  x 90-95
  p4: 95-100 x 70-75

Bands use the same 5pp buckets as the UI: <50, 50-55, ..., 90-95, 95-100.

Eligibility (no-lookahead, settled history):
  - finished, non-excluded matches with known score
  - first or latest stored prediction per (match, market, selection)
  - valid recorded decimal odds (> 1)
  - no replay snapshot (as_of_at), no fallback odds
  - quote/decision/created timestamps present with quote <= decision < kickoff
    and created < kickoff
  - completed CAT matchday before the as-at day
  - supported, non-void settlement (DNB draws excluded as void)

Use --min-q 0 (default) to ignore the Q>=75 gate; set --min-q 75 to apply it.

Run from the backend directory or container /app context, for example:
  python scripts/band_mix_five_pairs_backtest.py --selection latest --output /tmp/band-mix-sweep
  python scripts/band_mix_five_pairs_backtest.py --min-q 75 --start-date 2026-09-14 --end-date 2026-11-06
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

# Allow running as `python scripts/...` from repo root or backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal
from app.models import SelectionResult
from app.services.settlement import evaluate_selection

CAT = timezone(timedelta(hours=2))

BAND_MIX_PAIRS: list[tuple[str, str]] = [
    ("<50", "85-90"),
    ("50-55", "90-95"),
    ("55-60", "95-100"),
    ("60-65", "90-95"),
    ("95-100", "70-75"),
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


def _dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def probability_band(value: float | None) -> str | None:
    """Same 5pp buckets as the UI band-mix filter."""
    if value is None or not math.isfinite(value):
        return None
    percent = value * 100.0
    if percent < 50:
        return "<50"
    lower = min(95, int(math.floor(percent / 5.0) * 5))
    return f"{lower}-{lower + 5}"


def pair_label(index: int) -> str:
    model, market = BAND_MIX_PAIRS[index]
    return f"{model}% x {market}%"


def pair_index_for(model_probability: float | None, implied_probability: float | None) -> int | None:
    model_band = probability_band(model_probability)
    market_band = probability_band(implied_probability)
    if model_band is None or market_band is None:
        return None
    for index, (pair_model, pair_market) in enumerate(BAND_MIX_PAIRS):
        if pair_model == model_band and pair_market == market_band:
            return index
    return None


async def load_rows() -> list[dict]:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        rows = (await db.execute(text(QUERY))).mappings().all()
    return [dict(row) for row in rows]


def prepare(
    rows: list[dict],
    as_at: datetime,
    selection: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[pd.DataFrame, Counter]:
    """Strict no-lookahead preparation over settled history."""
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

        if odds is None or not math.isfinite(float(odds)) or float(odds) <= 1:
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
        match_day = kickoff.astimezone(CAT).date()
        if match_day >= as_at_day:
            exclusions["current_or_future_day"] += 1
            continue
        if start_date and match_day < start_date:
            exclusions["before_start_date"] += 1
            continue
        if end_date and match_day > end_date:
            exclusions["after_end_date"] += 1
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
                "day": match_day.isoformat(),
                "q_score": float(row["q_score"]) if row["q_score"] is not None else np.nan,
                "q_grade": row["q_grade"],
                "model_probability": float(row["model_probability"]) if row["model_probability"] is not None else np.nan,
                "source_implied_probability": (
                    float(row["source_implied_probability"])
                    if row["source_implied_probability"] is not None
                    else np.nan
                ),
                "edge": float(row["edge"]) if row["edge"] is not None else np.nan,
                "model_agreement": float(row["model_agreement"]) if row["model_agreement"] is not None else np.nan,
                "odds": odds_f,
                "closing_decimal_odds": (
                    float(row["closing_decimal_odds"]) if row["closing_decimal_odds"] is not None else np.nan
                ),
                "clv_percentage": float(row["clv_percentage"]) if row["clv_percentage"] is not None else np.nan,
                "recommendation_status": row["recommendation_status"] or "other",
                "model_version": row["model_version"],
                "quote_age_hours": (decision - quote).total_seconds() / 3600.0,
                "won": bool(won),
                "profit": (odds_f - 1.0) if won else -1.0,
            }
        )

    frame = pd.DataFrame(records)
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


def cluster_bootstrap_roi(frame: pd.DataFrame, draws: int = 5000, seed: int = 20261121) -> list[float] | None:
    """Day-cluster bootstrap for ROI (picks on one day are correlated)."""
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


def _format_pct(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "n/a"
    return f"{value:.{digits}f}%"


def _format_num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "n/a"
    return f"{value:.{digits}f}"


def apply_band_mix(frame: pd.DataFrame, selected_pairs: list[int]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    selected = set(selected_pairs)
    indices = []
    labels = []
    for _, row in frame.iterrows():
        idx = pair_index_for(row.get("model_probability"), row.get("source_implied_probability"))
        if idx in selected:
            indices.append(idx)
            labels.append(pair_label(idx))
        else:
            indices.append(None)
            labels.append(None)
    out = frame.copy()
    out["pair_index"] = indices
    out["pair_label"] = labels
    out = out[out["pair_index"].notna()].copy()
    if out.empty:
        return out
    out["pair_index"] = out["pair_index"].astype(int)
    out["pair_label"] = out["pair_label"].astype(str)
    out["model_band"] = out["model_probability"].map(probability_band)
    out["implied_band"] = out["source_implied_probability"].map(probability_band)
    return out


def aggregate(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in frame.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        item = {col: val for col, val in zip(group_cols, keys)}
        item.update(summarise(group))
        rows.append(item)
    out = pd.DataFrame(rows)
    sort_cols = [c for c in ["day", "pair_index", "pair_label"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols).reset_index(drop=True)
    return out


def write_report(
    output: Path,
    *,
    args: argparse.Namespace,
    eligible: pd.DataFrame,
    matched: pd.DataFrame,
    exclusions: Counter,
    by_pair: pd.DataFrame,
    by_date_pair: pd.DataFrame,
    by_date: pd.DataFrame,
) -> None:
    overall = summarise(matched)
    overall_ci = cluster_bootstrap_roi(matched)

    lines: list[str] = []
    lines.append("# Band-mix five-pairs backtest")
    lines.append("")
    lines.append("Backtest of the five System Picks band-mix pairs using strict pre-bet settled-history eligibility.")
    lines.append(f"- as_at: `{args.as_at.isoformat()}`")
    lines.append(f"- selection: `{args.selection}` (one prediction per match/market/selection)")
    lines.append(f"- min_q: `{args.min_q}` ({'Q>=75 gate applied' if args.min_q >= 75 else 'Q>=75 gate ignored'})")
    lines.append(f"- start_date: `{args.start_date.isoformat() if args.start_date else 'auto (earliest eligible)'}`")
    lines.append(f"- end_date: `{args.end_date.isoformat() if args.end_date else 'as-at previous CAT day'}`")
    lines.append(f"- pairs: `{', '.join(f'p{i} {pair_label(i)}' for i in args.pair_indices)}`")
    lines.append("")

    lines.append("## Overall (matched picks)")
    lines.append("")
    if matched.empty:
        lines.append("_No picks matched the selected band-mix pairs under this filter._")
    else:
        ci_text = f"[{_format_pct(overall_ci[0])}, {_format_pct(overall_ci[1])}]" if overall_ci else "n/a"
        lines.append(f"- Picks: **{overall['n']}** across **{overall['matches']}** fixtures and **{overall['days']}** matchdays")
        lines.append(f"- Wins/Losses: **{overall['wins']} / {overall['losses']}**")
        lines.append(f"- Hit rate: **{_format_pct(overall['hit_rate'])}**")
        lines.append(f"- ROI: **{_format_pct(overall['roi'])}** (day-cluster 95% CI {ci_text})")
        lines.append(f"- Profit (1u): **{_format_num(overall['profit'])}** units")
        lines.append(f"- Avg odds: **{_format_num(overall['avg_odds'])}**")
        date_min = matched["day"].min() if not matched.empty else None
        date_max = matched["day"].max() if not matched.empty else None
        lines.append(f"- Date range: **{date_min}** to **{date_max}**")
    lines.append("")

    lines.append("## By pair")
    lines.append("")
    if by_pair.empty:
        lines.append("_No rows._")
    else:
        lines.append("| Pair | Picks | Matches | Days | Wins | Losses | Hit rate | ROI | Profit (1u) | Avg odds |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in by_pair.iterrows():
            lines.append(
                f"| p{int(r['pair_index'])} {r['pair_label']} | {int(r['n'])} | {int(r['matches'])} | {int(r['days'])} | "
                f"{int(r['wins'])} | {int(r['losses'])} | {_format_pct(r['hit_rate'])} | {_format_pct(r['roi'])} | "
                f"{_format_num(r['profit'])} | {_format_num(r['avg_odds'])} |"
            )
    lines.append("")

    lines.append("## By date")
    lines.append("")
    if by_date.empty:
        lines.append("_No rows._")
    else:
        lines.append("| Date | Picks | Matches | Wins | Losses | Hit rate | ROI | Profit (1u) | Avg odds |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in by_date.iterrows():
            lines.append(
                f"| {r['day']} | {int(r['n'])} | {int(r['matches'])} | {int(r['wins'])} | {int(r['losses'])} | "
                f"{_format_pct(r['hit_rate'])} | {_format_pct(r['roi'])} | {_format_num(r['profit'])} | {_format_num(r['avg_odds'])} |"
            )
    lines.append("")

    lines.append("## By date and pair")
    lines.append("")
    if by_date_pair.empty:
        lines.append("_No rows._")
    else:
        lines.append("| Date | Pair | Picks | Matches | Wins | Losses | Hit rate | ROI | Profit (1u) | Avg odds |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in by_date_pair.iterrows():
            lines.append(
                f"| {r['day']} | p{int(r['pair_index'])} {r['pair_label']} | {int(r['n'])} | {int(r['matches'])} | "
                f"{int(r['wins'])} | {int(r['losses'])} | {_format_pct(r['hit_rate'])} | {_format_pct(r['roi'])} | "
                f"{_format_num(r['profit'])} | {_format_num(r['avg_odds'])} |"
            )
    lines.append("")

    lines.append("## Eligibility and exclusions")
    lines.append("")
    lines.append(f"- Raw rows loaded: **{args.raw_rows}**")
    lines.append(f"- Eligible after prep (before Q/band filters): **{len(eligible)}**")
    if not eligible.empty:
        lines.append(f"- Eligible date range: **{eligible['day'].min()}** to **{eligible['day'].max()}**")
    lines.append(f"- Matched band-mix picks: **{len(matched)}**")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(dict(exclusions), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Results use recorded entry odds, one unit per pick, strict pre-kickoff eligibility, and settled outcomes only (DNB draws excluded).")
    lines.append("- Implied probability band is based on `predictions.source_implied_probability` (bookmaker-implied at capture), matching the UI band-mix definition.")
    lines.append("- This is a read-only historical backtest; it does not imply executable fills or future profitability.")

    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", choices=["first", "latest"], default="latest")
    parser.add_argument(
        "--min-q",
        type=float,
        default=0.0,
        help="Minimum Q score to include (default: 0, which ignores the Q>=75 gate). Use 75 to apply the gate.",
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=None, help="Inclusive CAT match date (YYYY-MM-DD).")
    parser.add_argument("--end-date", type=date.fromisoformat, default=None, help="Inclusive CAT match date (YYYY-MM-DD).")
    parser.add_argument("--as-at", type=str, default=None, help="As-at timestamp (ISO). Excludes current/future CAT day.")
    parser.add_argument(
        "--pairs",
        type=str,
        default="all",
        help="Comma-separated pair indices 0-4 (or 'all'). 0:<50x85-90,1:50-55x90-95,2:55-60x95-100,3:60-65x90-95,4:95-100x70-75",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output directory (must not exist).")
    args = parser.parse_args()

    if args.pairs.strip().lower() == "all":
        pair_indices = list(range(len(BAND_MIX_PAIRS)))
    else:
        pair_indices = []
        for token in args.pairs.split(","):
            token = token.strip().replace("p", "").replace("P", "")
            if token == "":
                continue
            idx = int(token)
            if idx < 0 or idx >= len(BAND_MIX_PAIRS):
                raise SystemExit(f"Invalid pair index: {idx} (expected 0-{len(BAND_MIX_PAIRS)-1})")
            pair_indices.append(idx)
        pair_indices = sorted(set(pair_indices))
        if not pair_indices:
            raise SystemExit("No pairs selected.")

    as_at = _dt(args.as_at) if args.as_at else datetime.now(timezone.utc)
    if as_at.tzinfo is None:
        as_at = as_at.replace(tzinfo=timezone.utc)

    args.output.mkdir(parents=True, exist_ok=False)

    raw = await load_rows()
    frame, exclusions = prepare(raw, as_at, args.selection, start_date=args.start_date, end_date=args.end_date)

    eligible = frame.copy()
    if not eligible.empty and args.min_q > 0:
        eligible = eligible[eligible["q_score"] >= args.min_q].reset_index(drop=True)

    args.raw_rows = len(raw)
    args.as_at = as_at
    args.pair_indices = pair_indices

    matched = apply_band_mix(eligible, pair_indices)

    by_date_pair = aggregate(matched, ["day", "pair_index", "pair_label"])
    by_pair = aggregate(matched, ["pair_index", "pair_label"])
    by_date = aggregate(matched, ["day"])

    if not matched.empty:
        matched.sort_values(["day", "pair_index", "kickoff_at", "match_id", "prediction_id"]).to_csv(
            args.output / "picks.csv", index=False
        )
    else:
        pd.DataFrame().to_csv(args.output / "picks.csv", index=False)
    by_date_pair.to_csv(args.output / "by_date_pair.csv", index=False)
    by_pair.to_csv(args.output / "by_pair.csv", index=False)
    by_date.to_csv(args.output / "by_date.csv", index=False)

    overall = summarise(matched)
    overall["bootstrap_95_roi"] = cluster_bootstrap_roi(matched)

    summary = {
        "as_at": as_at.isoformat(),
        "selection": args.selection,
        "min_q": args.min_q,
        "q_gate_ignored": args.min_q < 75,
        "start_date": args.start_date.isoformat() if args.start_date else None,
        "end_date": args.end_date.isoformat() if args.end_date else None,
        "pairs": [
            {"index": i, "model_band": BAND_MIX_PAIRS[i][0], "implied_band": BAND_MIX_PAIRS[i][1], "label": pair_label(i)}
            for i in pair_indices
        ],
        "raw_rows": len(raw),
        "eligible_after_prep": len(frame),
        "eligible_after_q_filter": len(eligible),
        "matched_picks": len(matched),
        "overall": overall,
        "by_pair": by_pair.to_dict(orient="records"),
        "by_date": by_date.to_dict(orient="records"),
        "by_date_pair": by_date_pair.to_dict(orient="records"),
        "date_range": [matched["day"].min(), matched["day"].max()] if not matched.empty else None,
        "exclusions": dict(exclusions),
        "notes": [
            "Strict pre-bet eligibility: settled, pre-kickoff timestamps, no replay/fallback, valid odds, non-void settlement.",
            "Band mix uses model_probability and source_implied_probability in 5pp UI buckets.",
            "One unit per pick at recorded entry odds.",
        ],
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_report(
        args.output,
        args=args,
        eligible=eligible,
        matched=matched,
        exclusions=exclusions,
        by_pair=by_pair,
        by_date_pair=by_date_pair,
        by_date=by_date,
    )

    print(
        json.dumps(
            {
                "output": str(args.output),
                "selection": args.selection,
                "min_q": args.min_q,
                "q_gate_ignored": args.min_q < 75,
                "pairs": [pair_label(i) for i in pair_indices],
                "eligible_after_prep": len(frame),
                "eligible_after_q_filter": len(eligible),
                "matched_picks": len(matched),
                "overall": overall,
                "date_range": summary["date_range"],
                "exclusions": dict(exclusions),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
