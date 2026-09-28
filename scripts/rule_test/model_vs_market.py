"""Model probability vs market probability vs match outcome.

Reads the CSV written by ``extract.py`` (so production access stays in that
one read-only extract), grades every forecast from the fixture's final score
with the production grader (``backend.services.settlement.resolve_outcome``),
and scores the model's probability layers against the de-vigged market and
the realised result.

Live and research/shadow forecasts are reported in separate sections and are
never pooled. Before any model-vs-market comparison, a coherence check sums
the stored fair market probabilities across each complete selection set
(1X2 and BTTS should sum to 1, Double Chance to 2). A market that fails is
labelled INCOHERENT and left out of the headline comparison, because its
market probabilities are not probabilities of what they claim to be.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\rule_test\\model_vs_market.py EXTRACT.csv --out REPORT.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.services.settlement import SettlementError, resolve_outcome  # noqa: E402
from scripts.rule_test.analyze import evidence  # noqa: E402

MARKET = "fair_market_probability"
LAYERS = {
    "ensemble": "ensemble_probability",
    "calibrated": "calibrated_probability",
    "conservative": "conservative_probability",
    "market (de-vigged)": MARKET,
    "market (raw 1/odds)": "implied_probability",
}
MODEL_LAYERS = dict(list(LAYERS.items())[:3])
# Complete selection sets and the sum their fair probabilities must reach.
SELECTION_SETS = {
    "1X2": ({"home", "draw", "away"}, 1.0),
    "BTTS": ({"yes", "no"}, 1.0),
    "TOTALS": ({"over", "under"}, 1.0),
    "DOUBLE_CHANCE": ({"1x", "12", "x2"}, 2.0),
}
COHERENCE_TOLERANCE = 0.05
EDGE_BINS = [-100, -5, 0, 2, 5, 10, 100]
BOOT_REPS = 2000


# --------------------------------------------------------------------------- data

def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true", "t", "1"])


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"id": str, "fixture_id": str})
    num = ["ensemble_probability", "calibrated_probability", "conservative_probability",
           MARKET, "executable_odds", "line", "home_goals", "away_goals"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("decision_as_of", "kickoff_utc"):
        df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    for c in ("research_mode", "gate_passed"):
        df[c] = _bool(df[c])
    df["implied_probability"] = 1.0 / df["executable_odds"]
    df["score_outcome"] = [_grade(r) for r in df.itertuples()]
    return df


def _grade(r) -> str:
    # A partial score on a live or abandoned match is not a result.
    if str(r.fixture_status).strip().lower() != "finished":
        return "not finished"
    if pd.isna(r.home_goals) or pd.isna(r.away_goals):
        return "no score"
    fixture = SimpleNamespace(home_goals=int(r.home_goals), away_goals=int(r.away_goals))
    line = None if pd.isna(r.line) else float(r.line)
    try:
        return resolve_outcome(fixture, r.market, r.selection, line=line).value
    except SettlementError:
        return "ungradable"


def coherence(df: pd.DataFrame) -> pd.DataFrame:
    """Per market: mean fair-probability sum over complete selection sets."""
    rows = []
    priced = df[df[MARKET].notna()].assign(sel=lambda d: d["selection"].str.lower())
    for market, s in priced.groupby("market"):
        expected = SELECTION_SETS.get(market.upper())
        if expected is None:
            rows.append({"market": market, "complete sets": 0, "expected sum": np.nan,
                         "mean sum": np.nan, "status": "unknown market"})
            continue
        wanted, target = expected
        # Latest price per selection so re-forecasts do not inflate the sum.
        latest = s.sort_values("decision_as_of").groupby(
            ["fixture_id", "line", "sel"], dropna=False).tail(1)
        sets = latest.groupby(["fixture_id", "line"], dropna=False)
        sums = [g[MARKET].sum() for _, g in sets if set(g["sel"]) == wanted]
        if not sums:
            status = "not checkable (no complete set)"
            mean = np.nan
        else:
            mean = float(np.mean(sums))
            status = "ok" if abs(mean - target) <= COHERENCE_TOLERANCE else "INCOHERENT"
        rows.append({"market": market, "complete sets": len(sums), "expected sum": target,
                     "mean sum": mean, "status": status})
    return pd.DataFrame(rows)


def prepare(df: pd.DataFrame, *, research: bool) -> tuple[pd.DataFrame, dict]:
    """Cohort split, timing filter and one row per selection."""
    audit: dict[str, object] = {"archived rows": len(df)}
    cohort = df[df["research_mode"] == research]
    audit["other-cohort rows excluded"] = len(df) - len(cohort)
    for c in LAYERS.values():
        audit[f"non-null {c}"] = int(cohort[c].notna().sum())
    after_ko = cohort["decision_as_of"] > cohort["kickoff_utc"]
    if research:
        # Reported, not dropped: a retrospective row is post-kickoff by design.
        audit["post-kickoff decision_as_of (kept, research)"] = int(after_ko.sum())
        kept = cohort
    else:
        audit["post-kickoff rows excluded"] = int(after_ko.sum())
        kept = cohort[~after_ko]
    # Latest pre-kickoff forecast per selection; earlier re-runs would
    # double-count the fixture.
    key = kept[["fixture_id", "market", "selection"]].assign(line=kept["line"].fillna(-1))
    latest = kept.loc[kept.sort_values("decision_as_of").groupby(
        [key[c] for c in key.columns]).tail(1).index]
    audit["superseded re-forecasts excluded"] = len(kept) - len(latest)
    for outcome, n in latest["score_outcome"].value_counts().items():
        audit[f"outcome={outcome}"] = int(n)
    settled = latest["outcome"].isin(["win", "loss", "push", "void"])
    mismatch = settled & (latest["outcome"] != latest["score_outcome"])
    audit["settlement disagrees with final score"] = int(mismatch.sum())
    graded = latest[latest["score_outcome"].isin(["win", "loss"])].copy()
    graded["y"] = (graded["score_outcome"] == "win").astype(float)
    audit["graded win/loss rows analysed"] = len(graded)
    return graded, audit


# ------------------------------------------------------------------------ metrics

def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(
        (idx == b).sum() * abs(p[idx == b].mean() - y[idx == b].mean())
        for b in range(bins) if (idx == b).any()
    ) / len(p))


def score(p: pd.Series, y: pd.Series) -> dict:
    m = p.notna()
    p, y = p[m].to_numpy(float), y[m].to_numpy(float)
    if len(p) == 0:
        return {"n": 0}
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "n": len(p),
        "mean p": p.mean(),
        "hit rate": y.mean(),
        "hit - p": y.mean() - p.mean(),
        "Brier": np.mean((p - y) ** 2),
        "log loss": -np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)),
        "ECE": _ece(p, y),
    }


def paired(df: pd.DataFrame, model_col: str, *, seed: int = 0) -> dict:
    """Brier(model) - Brier(market) on shared rows; negative = model better.

    The interval resamples whole fixtures, so several selections on one match
    are not treated as independent evidence.
    """
    s = df[df[model_col].notna() & df[MARKET].notna()]
    if s["fixture_id"].nunique() < 2:
        return {"n": len(s)}
    d = (s[model_col] - s["y"]) ** 2 - (s[MARKET] - s["y"]) ** 2
    per_fixture = d.groupby(s["fixture_id"]).agg(["sum", "size"])
    sums, sizes = per_fixture["sum"].to_numpy(), per_fixture["size"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), (BOOT_REPS, len(sums)))
    boots = sums[idx].sum(axis=1) / sizes[idx].sum(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"n": len(s), "fixtures": len(sums), "Brier diff": d.mean(),
            "95% CI lo": lo, "95% CI hi": hi, "P(model better)": float((boots < 0).mean())}


def flat_roi(s: pd.DataFrame) -> float:
    s = s[s["executable_odds"].notna()]
    if s.empty:
        return float("nan")
    return float(np.where(s["y"] == 1, s["executable_odds"] - 1, -1.0).mean())


def calibration_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    s = df[df[col].notna()]
    t = s.groupby(pd.cut(s[col], np.linspace(0, 1, 11), include_lowest=True), observed=True).agg(
        n=("y", "size"), mean_p=(col, "mean"), hit=("y", "mean"))
    t["hit - p"] = t["hit"] - t["mean_p"]
    t["evidence"] = t["n"].map(evidence)
    return t


def edge_table(df: pd.DataFrame, model_col: str) -> pd.DataFrame:
    s = df[df[model_col].notna() & df[MARKET].notna()]
    if s.empty:
        return pd.DataFrame({"note": ["no rows with both model and market probability"]})
    buckets = pd.cut((s[model_col] - s[MARKET]) * 100, EDGE_BINS)
    rows = []
    for b, g in s.groupby(buckets, observed=True):
        rows.append({"model - market (pp)": str(b), "n": len(g), "model p": g[model_col].mean(),
                     "market p": g[MARKET].mean(), "hit": g["y"].mean(),
                     "flat ROI": flat_roi(g), "evidence": evidence(len(g))})
    return pd.DataFrame(rows).set_index("model - market (pp)")


def by_segment(df: pd.DataFrame, keys: list[str], model_col: str) -> pd.DataFrame:
    rows = []
    for k, s in df.groupby(keys, dropna=False):
        both = s[s[model_col].notna() & s[MARKET].notna()]
        rows.append({
            **dict(zip(keys, k if isinstance(k, tuple) else (k,), strict=True)),
            "n": len(s), "priced": len(both), "hit": s["y"].mean(),
            "model p": s[model_col].mean(), "market p": s[MARKET].mean(),
            "Brier model*": np.mean((both[model_col] - both["y"]) ** 2) if len(both) else np.nan,
            "Brier market*": np.mean((both[MARKET] - both["y"]) ** 2) if len(both) else np.nan,
            "flat ROI": flat_roi(s), "evidence": evidence(len(s)),
        })
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------- report

def _fmt(t: pd.DataFrame) -> str:
    return "```\n" + t.to_string(float_format=lambda v: f"{v:.4f}") + "\n```"


def section(graded: pd.DataFrame, audit: dict, title: str, incoherent: set[str]) -> str:
    out = [f"## {title}", "", "### Dataset funnel"]
    out += [f"- {k}: {v}" for k, v in audit.items()]
    if graded.empty:
        return "\n".join(out + ["", "No graded rows - nothing to analyse."])
    out += [
        f"- kickoff span: {graded['kickoff_utc'].min():%Y-%m-%d} .. "
        f"{graded['kickoff_utc'].max():%Y-%m-%d}",
        f"- fixtures: {graded['fixture_id'].nunique()}", "",
    ]
    coherent = graded[~graded["market"].isin(incoherent)]
    note = f" (excludes INCOHERENT markets: {', '.join(sorted(incoherent))})" if incoherent else ""

    out += ["### Probability layers, coherent markets" + note,
            _fmt(pd.DataFrame({k: score(coherent[c], coherent["y"]) for k, c in LAYERS.items()}).T)]
    out += ["", "### Paired Brier, model layer minus de-vigged market (negative = model better)"
            + note,
            _fmt(pd.DataFrame({k: paired(coherent, c) for k, c in MODEL_LAYERS.items()}).T)]
    for market, s in graded.groupby("market"):
        label = ""
        if market in incoherent:
            label = " - INCOHERENT market prices, comparison not meaningful"
        out += ["", f"### {market}{label}",
                "Paired Brier (calibrated vs market):",
                _fmt(pd.DataFrame({"calibrated": paired(s, "calibrated_probability")}).T),
                "Model vs market disagreement:", _fmt(edge_table(s, "calibrated_probability"))]
    for col in ("calibrated_probability", MARKET):
        src = coherent if col == MARKET else graded
        out += ["", f"### Calibration - {col}" + (note if col == MARKET else ""),
                _fmt(calibration_table(src, col))]
    out += ["", "### By market / selection", "(* Brier on priced rows only)",
            _fmt(by_segment(graded, ["market", "selection"], "calibrated_probability"))]
    out += ["", "### By value-gate result",
            _fmt(by_segment(graded, ["gate_passed"], "calibrated_probability"))]
    top = graded["league"].value_counts().head(15).index
    out += ["", "### By league (top 15 by volume)",
            _fmt(by_segment(graded[graded["league"].isin(top)], ["league"],
                            "calibrated_probability"))]
    return "\n".join(out)


def report(df: pd.DataFrame, label: str) -> str:
    coh = coherence(df)
    incoherent = set(coh.loc[coh["status"] == "INCOHERENT", "market"])
    out = [f"# Model vs market vs outcome - {label}", "",
           "Evidence: under 30 rows is insufficient, 30-99 thin, 100+ usable.", "",
           "## Market price coherence (fair probabilities over a complete selection set)",
           _fmt(coh), ""]
    for research, title in ((False, "LIVE forecasts"),
                            (True, "RESEARCH / shadow forecasts (never pooled with live)")):
        graded, audit = prepare(df, research=research)
        out += [section(graded, audit, title, incoherent), ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("extract", help="CSV written by extract.py")
    parser.add_argument("--label", default="archive", help="name shown in the report title")
    parser.add_argument("--out", help="write the Markdown report here instead of stdout")
    args = parser.parse_args(argv)
    text = report(load(args.extract), args.label)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
