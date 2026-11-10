"""Out-of-sample calibration audit for the QwanEj prediction model.

The Q>=75 backtest found that the model is badly overconfident at the top of
the Q distribution.  Before spending effort on a model overhaul we need to
know whether that gap is (a) a monotone calibration problem that a mapping
can fix, or (b) a genuine ordering failure that needs new features/models.

This script answers that with an expanding-window walk-forward:

    train on every completed matchday before day D
    fit global Platt + isotonic (and per-market isotonic when sample allows)
    score day D out of sample

It reports, out of sample, raw vs calibrated vs bookmaker-implied Brier,
log-loss, ECE and the realised ROI of raw-edge versus calibrated-edge
selections.  Nothing is written to the database; this is an audit only.

Usage (inside the backend container):

    python /tmp/calibration_walk_forward.py --output /tmp/cal-audit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_sweet_spot_backtest import CAT, load_rows, prepare  # noqa: E402
from app.services.recalibration import calibrated_probability, fit_isotonic  # noqa: E402

EDGE_BANDS = [
    ("<=0", -1.0, 0.0),
    ("0-5pp", 0.0, 0.05),
    ("5-10pp", 0.05, 0.10),
    ("10-20pp", 0.10, 0.20),
    ("20pp+", 0.20, 1.0),
]


# ---------------------------------------------------------------- metrics


def _logit(probability: float) -> float:
    p = min(1.0 - 1e-6, max(1e-6, float(probability)))
    return math.log(p / (1.0 - p))


def brier(probabilities, outcomes) -> float | None:
    if not len(probabilities):
        return None
    return float(np.mean((np.asarray(probabilities) - np.asarray(outcomes)) ** 2))


def log_loss(probabilities, outcomes) -> float | None:
    if not len(probabilities):
        return None
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1.0 - 1e-6)
    y = np.asarray(outcomes, dtype=float)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def ece(probabilities, outcomes, bins: int = 10) -> float | None:
    if not len(probabilities):
        return None
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    total = len(p)
    value = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        mask = (p >= low) & (p < high if index < bins - 1 else p <= high)
        if mask.any():
            value += mask.sum() / total * abs(p[mask].mean() - y[mask].mean())
    return float(value)


def fit_platt(samples: list[tuple[float, float]]) -> dict | None:
    if len(samples) < 50:
        return None
    outcomes = np.asarray([y for _, y in samples], dtype=int)
    if len(set(outcomes.tolist())) < 2:
        return None
    logits = np.asarray([_logit(p) for p, _ in samples], dtype=float).reshape(-1, 1)
    model = LogisticRegression(C=2.0, solver="lbfgs", random_state=17)
    model.fit(logits, outcomes)
    return {
        "slope": float(model.coef_[0][0]),
        "intercept": float(model.intercept_[0]),
    }


def apply_platt(probability: float, fit: dict | None) -> float:
    if not fit:
        return float(probability)
    score = max(-35.0, min(35.0, fit["slope"] * _logit(probability) + fit["intercept"]))
    return 1.0 / (1.0 + math.exp(-score))


# ------------------------------------------------------------ walk-forward


def walk_forward(frame: pd.DataFrame, min_train: int, market_min: int) -> pd.DataFrame:
    days = sorted(frame["day"].unique())
    rows: list[dict] = []

    for day in days:
        train = frame[frame["day"] < day]
        test = frame[frame["day"] == day]
        if len(train) < min_train or test.empty:
            continue

        train_samples = list(zip(train["model_probability"], train["won"].astype(float)))
        global_platt = fit_platt(train_samples)
        global_iso = fit_isotonic(train_samples) if len(train_samples) >= 100 else []

        market_iso: dict[str, list[tuple[float, float]]] = {}
        market_platt: dict[str, dict | None] = {}
        for market, group in train.groupby("market"):
            if len(group) < market_min:
                continue
            samples = list(zip(group["model_probability"], group["won"].astype(float)))
            market_iso[market] = fit_isotonic(samples)
            market_platt[market] = fit_platt(samples)

        for _, pick in test.iterrows():
            raw = float(pick["model_probability"])
            iso = market_iso.get(pick["market"], global_iso)
            platt = market_platt.get(pick["market"], global_platt)
            rows.append(
                {
                    "day": day,
                    "match_id": int(pick["match_id"]),
                    "market": pick["market"],
                    "q_score": float(pick["q_score"]),
                    "raw": raw,
                    "platt": apply_platt(raw, platt),
                    "isotonic": calibrated_probability(iso, raw) if iso else raw,
                    "implied": float(pick["source_implied_probability"]),
                    "odds": float(pick["odds"]),
                    "won": bool(pick["won"]),
                }
            )

    return pd.DataFrame(rows)


# --------------------------------------------------------------- reporting


def describe(frame: pd.DataFrame, label: str, q_min: float | None = None) -> dict:
    view = frame if q_min is None else frame[frame["q_score"] >= q_min]
    outcomes = view["won"].astype(float).tolist()
    if not len(view):
        return {"scope": label, "n": 0}
    implied = view["implied"].to_numpy(dtype=float)
    implied_clean = np.clip(np.where(implied > 0, implied, 0.5), 1e-6, 1 - 1e-6)
    return {
        "scope": label,
        "n": int(len(view)),
        "hit_rate": float(100.0 * view["won"].mean()),
        "raw_prob": float(100.0 * view["raw"].mean()),
        "calibrated_prob": float(100.0 * view["isotonic"].mean()),
        "implied_prob": float(100.0 * np.mean(implied_clean)),
        "brier_raw": brier(view["raw"], outcomes),
        "brier_platt": brier(view["platt"], outcomes),
        "brier_isotonic": brier(view["isotonic"], outcomes),
        "brier_implied": brier(implied_clean, outcomes),
        "logloss_raw": log_loss(view["raw"], outcomes),
        "logloss_isotonic": log_loss(view["isotonic"], outcomes),
        "logloss_implied": log_loss(implied_clean, outcomes),
        "ece_raw": ece(view["raw"], outcomes),
        "ece_isotonic": ece(view["isotonic"], outcomes),
        "ece_implied": ece(implied_clean, outcomes),
    }


def edge_table(frame: pd.DataFrame, probability: str, label: str, q_min: float | None = None) -> list[dict]:
    view = frame if q_min is None else frame[frame["q_score"] >= q_min]
    rows = []
    edge = view[probability] - view["implied"]
    for name, low, high in EDGE_BANDS:
        mask = (edge > low) & (edge <= high)
        group = view[mask]
        if group.empty:
            continue
        rows.append(
            {
                "edge_source": label,
                "edge_band": name,
                "n": int(len(group)),
                "hit_rate": float(100.0 * group["won"].mean()),
                "roi": float(100.0 * group["profit"].mean()) if "profit" in group else _roi(group),
            }
        )
    return rows


def _roi(group: pd.DataFrame) -> float:
    profit = np.where(group["won"].to_numpy(), group["odds"].to_numpy() - 1.0, -1.0)
    return float(100.0 * profit.mean())


def relative_skill(scored: pd.DataFrame, draws: int = 300, seed: int = 20261110) -> dict:
    """Does the model add information beyond the bookmaker?

    Fits ``outcome ~ logit(implied) + logit(model)`` on the walk-forward
    scores.  A model coefficient whose bootstrap interval includes zero means
    the model contributes nothing once the price is known; a negative
    coefficient means it actively misleads.  Days are resampled as clusters.
    """
    view = scored[(scored["implied"] > 0) & (scored["implied"] < 1)].copy()
    if len(view) < 200:
        return {"fitted": False}

    def fit(frame: pd.DataFrame):
        x = np.column_stack(
            [
                np.asarray([_logit(p) for p in frame["implied"]]),
                np.asarray([_logit(p) for p in frame["raw"]]),
            ]
        )
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
    rng = np.random.default_rng(seed)
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
        "market_coefficient": float(base[0]),
        "model_coefficient": float(base[1]),
        "model_ci_low": float(np.percentile(arr, 2.5)),
        "model_ci_high": float(np.percentile(arr, 97.5)),
        "model_p_le_zero": float((np.sum(arr <= 0.0) + 1) / (len(arr) + 1)),
        "draws": len(arr),
    }


def market_table(frame: pd.DataFrame, q_min: float | None = None) -> list[dict]:
    view = frame if q_min is None else frame[frame["q_score"] >= q_min]
    rows = []
    for market, group in view.groupby("market"):
        if len(group) < 30:
            continue
        outcomes = group["won"].astype(float).tolist()
        implied = np.clip(group["implied"].to_numpy(dtype=float), 1e-6, 1 - 1e-6)
        rows.append(
            {
                "market": market,
                "n": int(len(group)),
                "hit_rate": float(100.0 * group["won"].mean()),
                "raw_prob": float(100.0 * group["raw"].mean()),
                "calibrated_prob": float(100.0 * group["isotonic"].mean()),
                "implied_prob": float(100.0 * implied.mean()),
                "brier_raw": brier(group["raw"], outcomes),
                "brier_isotonic": brier(group["isotonic"], outcomes),
                "brier_implied": brier(implied, outcomes),
                "roi": _roi(group),
            }
        )
    return sorted(rows, key=lambda item: -item["n"])


def _fmt(value, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._\n"
    lines = ["| " + " | ".join(label for _, label in columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(key)) for key, _ in columns) + " |")
    return "\n".join(lines) + "\n"


def build_report(output: Path, frame: pd.DataFrame, scored: pd.DataFrame, settings: dict) -> dict:
    overall = describe(scored, "all picks")
    top_q = describe(scored, "Q >= 75", q_min=75.0)
    edge_raw = edge_table(scored, "raw", "raw edge")
    edge_cal = edge_table(scored, "isotonic", "calibrated edge")
    edge_raw_top = edge_table(scored, "raw", "raw edge", q_min=75.0)
    edge_cal_top = edge_table(scored, "isotonic", "calibrated edge", q_min=75.0)
    markets = market_table(scored)
    markets_top = market_table(scored, q_min=75.0)
    skill = relative_skill(scored)
    skill_top = relative_skill(scored[scored["q_score"] >= 75.0])

    improvement = None
    if overall.get("brier_raw") and overall.get("brier_isotonic") is not None:
        improvement = 100.0 * (1.0 - overall["brier_isotonic"] / overall["brier_raw"])
    skill_vs_market = None
    if overall.get("brier_isotonic") and overall.get("brier_implied"):
        skill_vs_market = 1.0 - overall["brier_isotonic"] / overall["brier_implied"]

    report = f"""# Calibration walk-forward audit

**Question: is the Q>=75 overconfidence a calibration bug or a model-ordering failure?**

Method: expanding-window walk-forward. Each matchday is scored out of sample
after fitting Platt and isotonic mappings on every earlier matchday. No
prediction is fitted on its own day, and no closing-line or outcome field is
used as an input. Per-market isotonic mappings are used when a market has at
least {settings['market_min']} prior picks, otherwise the global mapping.

## Headline

- Out-of-sample picks: **{overall['n']:,}** over **{scored['day'].nunique()}** matchdays.
- All picks: observed **{_fmt(overall['hit_rate'], 1)}%**, raw model **{_fmt(overall['raw_prob'], 1)}%**, calibrated **{_fmt(overall['calibrated_prob'], 1)}%**, bookmaker **{_fmt(overall['implied_prob'], 1)}%**.
- Brier: raw **{_fmt(overall['brier_raw'])}**, isotonic **{_fmt(overall['brier_isotonic'])}**, implied **{_fmt(overall['brier_implied'])}**.
- Isotonic reduces Brier by **{_fmt(improvement, 1)}%** versus raw, but it still scores **{_fmt(skill_vs_market * 100.0 if skill_vs_market is not None else None, 1)}% worse** than the bookmaker's implied probability (positive skill score = better than market).
- Q >= 75: observed **{_fmt(top_q['hit_rate'], 1)}%**, raw model **{_fmt(top_q['raw_prob'], 1)}%**, calibrated **{_fmt(top_q['calibrated_prob'], 1)}%**, implied **{_fmt(top_q['implied_prob'], 1)}%**.
- Q >= 75 Brier: raw **{_fmt(top_q['brier_raw'])}**, isotonic **{_fmt(top_q['brier_isotonic'])}**, implied **{_fmt(top_q['brier_implied'])}**.
- Market-relative test (outcome ~ logit(implied) + logit(model), days clustered): model coefficient **{_fmt(skill.get('model_coefficient'), 3)}** with 95% CI **[{_fmt(skill.get('model_ci_low'), 3)}, {_fmt(skill.get('model_ci_high'), 3)}]**, p(coef<=0) = **{_fmt(skill.get('model_p_le_zero'), 3)}**.

## Does the model beat the market?

A model can be badly calibrated and still add information. The test below asks whether the model's probability explains outcomes once the closing/entry price is known. It is the difference between "recalibrate" and "overhaul".

| Scope | N | Market coef | Model coef | Model 95% CI | p(coef<=0) | Verdict |
|---|---|---|---|---|---|---|
| all picks | {skill.get('n', 0)} | {_fmt(skill.get('market_coefficient'), 3)} | {_fmt(skill.get('model_coefficient'), 3)} | [{_fmt(skill.get('model_ci_low'), 3)}, {_fmt(skill.get('model_ci_high'), 3)}] | {_fmt(skill.get('model_p_le_zero'), 3)} | {'no demonstrated information beyond price' if (skill.get('model_ci_low') or 0) <= 0 else 'possible information beyond price'} |
| Q >= 75 | {skill_top.get('n', 0)} | {_fmt(skill_top.get('market_coefficient'), 3)} | {_fmt(skill_top.get('model_coefficient'), 3)} | [{_fmt(skill_top.get('model_ci_low'), 3)}, {_fmt(skill_top.get('model_ci_high'), 3)}] | {_fmt(skill_top.get('model_p_le_zero'), 3)} | {'no demonstrated information beyond price' if (skill_top.get('model_ci_low') or 0) <= 0 else 'possible information beyond price'} |

## What the numbers mean

- If calibrated Brier is close to implied Brier, a monotone mapping is enough and the model can stay.
- If calibrated Brier is still clearly worse than implied, the model's ordering is wrong, not just its level, and that is the case for a model change.
- If calibrated edge bands still show worse ROI at higher edge, the edge signal remains anti-predictive even after calibration.

## Reliability, all picks

{markdown_table([overall, top_q], [('scope', 'Scope'), ('n', 'N'), ('hit_rate', 'Observed %'), ('raw_prob', 'Raw %'), ('calibrated_prob', 'Calibrated %'), ('implied_prob', 'Implied %'), ('brier_raw', 'Brier raw'), ('brier_isotonic', 'Brier iso'), ('brier_implied', 'Brier implied'), ('ece_raw', 'ECE raw'), ('ece_isotonic', 'ECE iso')])}

## Edge bands, out of sample (all picks)

{markdown_table(edge_raw + edge_cal, [('edge_source', 'Edge'), ('edge_band', 'Band'), ('n', 'N'), ('hit_rate', 'Hit %'), ('roi', 'ROI %')])}

## Edge bands at Q >= 75

{markdown_table(edge_raw_top + edge_cal_top, [('edge_source', 'Edge'), ('edge_band', 'Band'), ('n', 'N'), ('hit_rate', 'Hit %'), ('roi', 'ROI %')])}

## Per-market calibration (all picks)

{markdown_table(markets, [('market', 'Market'), ('n', 'N'), ('hit_rate', 'Observed %'), ('raw_prob', 'Raw %'), ('calibrated_prob', 'Calibrated %'), ('implied_prob', 'Implied %'), ('brier_raw', 'Brier raw'), ('brier_isotonic', 'Brier iso'), ('brier_implied', 'Brier implied'), ('roi', 'ROI %')])}

## Per-market calibration at Q >= 75

{markdown_table(markets_top, [('market', 'Market'), ('n', 'N'), ('hit_rate', 'Observed %'), ('raw_prob', 'Raw %'), ('calibrated_prob', 'Calibrated %'), ('implied_prob', 'Implied %'), ('brier_raw', 'Brier raw'), ('brier_isotonic', 'Brier iso'), ('brier_implied', 'Brier implied'), ('roi', 'ROI %')])}

## Caveats

- The mapping is refitted every matchday, but the model itself is a single deployed version; regime changes are not modelled.
- Per-market isotonic is only fitted when the market has enough prior picks, so small markets fall back to the global mapping.
- Walk-forward scoring starts only after {settings['min_train']} prior picks exist, so early matchdays are not scored.
- This audit says how much a mapping can fix. It does not by itself authorise changing live decisions; that still needs a frozen prospective review.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return {
        "settings": settings,
        "overall": overall,
        "q75": top_q,
        "edge_raw": edge_raw,
        "edge_calibrated": edge_cal,
        "edge_raw_q75": edge_raw_top,
        "edge_calibrated_q75": edge_cal_top,
        "markets": markets,
        "markets_q75": markets_top,
        "relative_skill": skill,
        "relative_skill_q75": skill_top,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-train", type=int, default=300)
    parser.add_argument("--market-min", type=int, default=250)
    parser.add_argument("--as-at", default=None)
    args = parser.parse_args()

    as_at = (
        datetime.fromisoformat(args.as_at)
        if args.as_at
        else datetime.now(timezone.utc)
    )
    args.output.mkdir(parents=True, exist_ok=True)

    raw = asyncio.run(load_rows())
    frame, exclusions = prepare(raw, as_at, "first")
    if frame.empty:
        raise SystemExit("No eligible picks.")
    frame = frame[frame["day"] < as_at.astimezone(CAT).date().isoformat()].reset_index(drop=True)

    scored = walk_forward(frame, args.min_train, args.market_min)
    if scored.empty:
        raise SystemExit("Not enough prior days to score out of sample.")

    scored["profit"] = np.where(scored["won"], scored["odds"] - 1.0, -1.0)
    scored.to_csv(args.output / "scored.csv", index=False)

    summary = build_report(
        args.output,
        frame,
        scored,
        {
            "min_train": args.min_train,
            "market_min": args.market_min,
            "as_at": as_at.isoformat(),
            "eligible_all_q": int(len(frame)),
            "exclusions": dict(exclusions),
        },
    )
    (args.output / "analysis.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "scored": len(scored)}, indent=2))


if __name__ == "__main__":
    main()
