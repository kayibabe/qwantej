"""Test a forecast selection rule against archived, settled forecasts.

Compares four nested groups built from the CSV written by ``extract.py``:

    A. all eligible priced forecasts
    B. P >= p_min
    C. P >= p_min and EV > ev_min
    D. P >= p_min and EV > ev_min and QSS >= qss_min   (the rule)

plus C minus D (the forecasts the QSS gate removes), headline and broken down
by market, league, model version and kickoff month.

Definitions:
  probability  = conservative_probability (P_cons, the layer decisions use)
  EV           = expected_value = P_cons * executable_odds - 1
  QSS          = qss (0-100); a missing QSS never passes the QSS gate
  profit       = flat 1-unit stake at executable_odds; void/push return stake

Guards against overstating the evidence:
  * eligibility: live (non-research) rows with one effective settlement,
    complete price block, valid timing (quote <= decision <= kickoff, archived
    before kickoff), EV consistent with P_cons x odds, and a settlement that
    agrees with the final score;
  * repeated picks: only the first qualifying forecast per
    (fixture, market, selection, line) is kept;
  * correlated picks: ROI intervals resample whole matches.

Standard library only, so it runs anywhere the CSV is.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

BOOT = 2000
SEED = 20260927
# EV is stored to 5 dp, P_cons to 6 dp and odds to 3 dp, so recomputation
# differs by up to ~1e-5 from rounding alone; 1e-4 flags only real mismatches.
EV_TOL = 1e-4
PICK_KEY = ("fixture_id", "market", "selection", "line")
RESEARCH_REASON = "research_mode (retrospective/shadow, not live evidence)"


@dataclass(frozen=True)
class Rule:
    p_min: float = 0.70
    ev_min: float = 0.0
    qss_min: float = 82.0

    def groups(self) -> list[tuple[str, str, Callable[[dict], bool]]]:
        def b(r: dict) -> bool:
            return r["conservative_probability"] >= self.p_min

        def c(r: dict) -> bool:
            return b(r) and r["expected_value"] > self.ev_min

        def d(r: dict) -> bool:
            return c(r) and r["qss"] is not None and r["qss"] >= self.qss_min

        p, ev, q = f"{100 * self.p_min:g}%", f"{100 * self.ev_min:g}%", f"{self.qss_min:g}"
        return [
            ("A", "All eligible priced forecasts", lambda r: True),
            ("B", f"P >= {p}", b),
            ("C", f"P >= {p} & EV > {ev}", c),
            ("D", f"P >= {p} & EV > {ev} & QSS >= {q} (rule)", d),
        ]


# ---------------------------------------------------------------- parsing
def _f(v):
    return float(v) if v not in ("", None) else None


def _t(v):
    if v in ("", None):
        return None
    return datetime.fromisoformat(v.replace(" ", "T"))


def _b(v):
    return str(v).lower() in ("true", "t", "1")


def load(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            for k in (
                "line",
                "conservative_probability",
                "calibrated_probability",
                "ensemble_probability",
                "fair_market_probability",
                "executable_odds",
                "expected_value",
                "qss",
                "dqs",
                "clv",
                "taken_odds",
                "closing_odds",
                "profit_loss",
            ):
                r[k] = _f(r.get(k))
            for k in ("home_goals", "away_goals", "n_effective", "n_settlement_rows"):
                r[k] = int(float(r[k])) if r.get(k) not in ("", None) else None
            for k in (
                "prediction_timestamp",
                "decision_as_of",
                "quote_timestamp",
                "created_at",
                "kickoff_utc",
                "settled_at",
            ):
                r[k] = _t(r.get(k))
            r["research_mode"] = _b(r["research_mode"])
            r["gate_passed"] = _b(r["gate_passed"])
            r["league_label"] = (
                f"{r['league']} ({r['league_country']})" if r.get("league_country") else r["league"]
            )
            r["model_label"] = (
                f"{r['model_name']} v{r['model_version']}"
                if r.get("model_name")
                else "(no model version)"
            )
            r["market_label"] = r["market"]
            r["month"] = r["kickoff_utc"].strftime("%Y-%m") if r["kickoff_utc"] else "?"
            rows.append(r)
    return rows


# ------------------------------------------------ independent outcome check
def recompute(r: dict) -> str | None:
    """Mirror of backend.services.settlement.resolve_outcome; None = can't check."""
    h, a = r["home_goals"], r["away_goals"]
    if h is None or a is None:
        return None
    m, s = r["market"].upper(), r["selection"].lower()
    if m == "1X2":
        res = "home" if h > a else "draw" if h == a else "away"
        return "win" if s == res else "loss"
    if m == "DOUBLE_CHANCE":
        won = {"1x": h >= a, "x2": h <= a, "12": h != a}.get(s)
        return None if won is None else ("win" if won else "loss")
    if m == "BTTS":
        both = h > 0 and a > 0
        won = {"yes": both, "no": not both}.get(s)
        return None if won is None else ("win" if won else "loss")
    if m == "TOTALS" and r["line"] is not None:
        tot = h + a
        if tot == r["line"]:
            return "push"
        won = {"over": tot > r["line"], "under": tot < r["line"]}.get(s)
        return None if won is None else ("win" if won else "loss")
    return None


# ---------------------------------------------------------- data quality
def audit(rows: list[dict], include_research: bool = False) -> tuple[list[dict], Counter]:
    """Tag every row with exclusion reasons; return (eligible rows, reason counts)."""
    reasons: Counter = Counter()
    eligible = []
    for r in rows:
        why = []
        if r["research_mode"] and not include_research:
            why.append(RESEARCH_REASON)
        if not r["outcome"]:
            why.append("no effective settlement (unsettled / pending)")
        if r["n_effective"] and r["n_effective"] > 1:
            why.append("more than one effective settlement")
        for fld in ("conservative_probability", "executable_odds", "expected_value"):
            if r[fld] is None:
                why.append(f"missing {fld}")
        if r["executable_odds"] is not None and r["executable_odds"] <= 1:
            why.append("executable_odds <= 1")
        if r["quote_timestamp"] is None and r["executable_odds"] is not None:
            why.append("missing quote_timestamp")
        ko = r["kickoff_utc"]
        if (
            r["quote_timestamp"]
            and r["decision_as_of"]
            and r["quote_timestamp"] > r["decision_as_of"]
        ):
            why.append("timing: quote after decision_as_of")
        if ko and r["decision_as_of"] and r["decision_as_of"] > ko:
            why.append("timing: decision_as_of after kickoff")
        if ko and r["prediction_timestamp"] and r["prediction_timestamp"] > ko:
            why.append("timing: prediction_timestamp after kickoff")
        if ko and r["created_at"] and r["created_at"] > ko:
            why.append("timing: archived (created_at) after kickoff")
        p, o, ev = r["conservative_probability"], r["executable_odds"], r["expected_value"]
        if None not in (p, o, ev) and abs(ev - (p * o - 1)) > EV_TOL:
            why.append("EV inconsistent with P_cons x odds")
        if r["outcome"]:
            chk = recompute(r)
            if chk is not None and r["outcome"] != chk:
                why.append("settlement disagrees with scoreline")
            if r["fixture_status"] != "finished" and r["outcome"] in ("win", "loss"):
                why.append("settled win/loss but fixture not finished")
        r["excl"] = why
        reasons.update(why)
        if not why:
            eligible.append(r)
    return eligible, reasons


# ---------------------------------------------------------------- metrics
def dedupe(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Keep the first qualifying forecast per pick (earliest decision time)."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: (x["decision_as_of"], x["prediction_timestamp"], x["id"])):
        k = tuple(r[f] for f in key_fields)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def profit(r: dict) -> float:
    if r["outcome"] == "win":
        return r["executable_odds"] - 1
    if r["outcome"] == "loss":
        return -1.0
    return 0.0


def wilson(w: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return (None, None)
    ph = w / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    m = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def cluster_boot_roi(rows: list[dict], rng: random.Random) -> tuple[float | None, float | None]:
    """95% CI for flat ROI resampling whole matches (picks on one match are correlated)."""
    by_fx = defaultdict(list)
    for r in rows:
        by_fx[r["fixture_id"]].append(profit(r))
    clusters = list(by_fx.values())
    if len(clusters) < 5:
        return (None, None)
    stats = []
    for _ in range(BOOT):
        s = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        n = sum(len(c) for c in s)
        stats.append(sum(sum(c) for c in s) / n)
    stats.sort()
    return (stats[int(0.025 * BOOT)], stats[int(0.975 * BOOT) - 1])


def summarise(rows: list[dict], rng: random.Random) -> dict:
    n = len(rows)
    wins = sum(r["outcome"] == "win" for r in rows)
    losses = sum(r["outcome"] == "loss" for r in rows)
    decided = wins + losses
    dec = [r for r in rows if r["outcome"] in ("win", "loss")]
    s = {
        "picks": n,
        "matches": len({r["fixture_id"] for r in rows}),
        "W": wins,
        "L": losses,
        "V/P": n - decided,
        "hit": wins / decided if decided else None,
        "hit_ci": wilson(wins, decided),
        "mean_p": sum(r["conservative_probability"] for r in dec) / len(dec) if dec else None,
        "breakeven": sum(1 / r["executable_odds"] for r in dec) / len(dec) if dec else None,
        "avg_odds": sum(r["executable_odds"] for r in rows) / n if n else None,
        "claimed_ev": sum(r["expected_value"] for r in rows) / n if n else None,
        "roi": sum(profit(r) for r in rows) / n if n else None,
        "units": sum(profit(r) for r in rows),
        "roi_ci": cluster_boot_roi(rows, rng) if n else (None, None),
        "brier": (
            sum((r["conservative_probability"] - (r["outcome"] == "win")) ** 2 for r in dec)
            / len(dec)
        )
        if dec
        else None,
    }
    clv = [r["clv"] for r in rows if r["clv"] is not None]
    s["clv"] = sum(clv) / len(clv) if clv else None
    s["clv_n"] = len(clv)
    s["cal_gap"] = (s["hit"] - s["mean_p"]) if s["hit"] is not None else None
    return s


# ------------------------------------------------------------- formatting
def pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def ci(t):
    return "–" if t[0] is None else f"[{100 * t[0]:.0f}, {100 * t[1]:.0f}]"


def num(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def evidence(n):
    return "insufficient" if n < 30 else "thin" if n < 100 else "usable"


HEAD = (
    "| Group | Picks | Matches | W-L-V | Hit | Hit 95% CI | Mean P | Cal gap | "
    "Break-even | Avg odds | Claimed EV | Flat ROI | ROI 95% CI (match-clustered) | "
    "Units | Brier | CLV (n) | Evidence |"
)
SEP = "|" + "---|" * 17


def row_md(label: str, s: dict) -> str:
    gap = "–" if s["cal_gap"] is None else f"{100 * s['cal_gap']:+.1f}pp"
    clv = "–" if s["clv"] is None else f"{s['clv']:+.3f}"
    return (
        f"| {label} | {s['picks']} | {s['matches']} | {s['W']}-{s['L']}-{s['V/P']} | "
        f"{pct(s['hit'])} | {ci(s['hit_ci'])} | {pct(s['mean_p'])} | {gap} | "
        f"{pct(s['breakeven'])} | {num(s['avg_odds'], 2)} | {pct(s['claimed_ev'])} | "
        f"{pct(s['roi'])} | {ci(s['roi_ci'])} | {s['units']:+.2f} | {num(s['brier'])} | "
        f"{clv} ({s['clv_n']}) | {evidence(s['picks'])} |"
    )


def report(
    rows: list[dict], source_label: str, rule: Rule | None = None, include_research: bool = False
) -> str:
    rule = rule or Rule()
    rng = random.Random(SEED)
    groups = rule.groups()
    in_d = groups[3][2]
    eligible, reasons = audit(rows, include_research)
    out: list[str] = []
    w = out.append

    w(f"# Rule test — {groups[3][1]}\n")
    w(
        f"Source: **{source_label}** · {len(rows)} archived predictions · "
        f"{len(eligible)} eligible settled priced forecasts before de-duplication\n"
    )
    if include_research:
        w(
            "> **Research-mode rows included.** These are retrospective or shadow forecasts, "
            "not live evidence; treat this run as secondary.\n"
        )
    w(
        "Definitions: probability = `conservative_probability` (P_cons); "
        "EV = P_cons × executable odds − 1; missing QSS fails the QSS gate; ROI = flat 1-unit "
        "stake at the archived executable odds, void/push return the stake. Each pick = first "
        "qualifying forecast per (fixture, market, selection, line); later re-forecasts of the "
        "same pick are dropped. ROI intervals resample whole matches, so several picks on one "
        "match count as one piece of evidence. Evidence: <30 picks insufficient, 30–99 thin, "
        "≥100 usable.\n"
    )

    w("## 1. Data quality and exclusions\n")
    w("A forecast can fail several checks; counts are per check, not additive.\n")
    w("| Check | Rows failing |\n|---|---|")
    for k, v in reasons.most_common():
        w(f"| {k} | {v} |")
    if not reasons:
        w("| (none) | 0 |")
    w("")
    settled_live = [r for r in rows if r["outcome"] and not r["research_mode"]]
    w(f"Settled live forecasts: {len(settled_live)}. Missing-field rates among them:\n")
    w("| Field | Missing | Share |\n|---|---|---|")
    for fld in (
        "conservative_probability",
        "executable_odds",
        "expected_value",
        "qss",
        "quote_timestamp",
        "bookmaker",
        "model_version_id",
        "clv",
        "closing_odds",
    ):
        miss = sum(1 for r in settled_live if r.get(fld) in (None, ""))
        w(f"| {fld} | {miss} | {pct(miss / len(settled_live)) if settled_live else '–'} |")
    w("")
    corrected = sum(1 for r in rows if (r["n_settlement_rows"] or 0) > 1)
    w(
        f"Predictions whose settlement was corrected at least once (effective row used): "
        f"{corrected}\n"
    )
    w(
        f"`gate_passed` among eligible: {sum(r['gate_passed'] for r in eligible)} true, "
        f"{sum(not r['gate_passed'] for r in eligible)} false (all kept — the test is about "
        "the rule, not the live gate).\n"
    )

    pick_counts = Counter(tuple(r[f] for f in PICK_KEY) for r in eligible)
    rep = {k: c for k, c in pick_counts.items() if c > 1}
    fx_sel = defaultdict(set)
    for r in eligible:
        fx_sel[r["fixture_id"]].add((r["market"], r["selection"], r["line"]))
    multi = sum(1 for v in fx_sel.values() if len(v) > 1)
    w("## 2. Repeated picks on the same match\n")
    w(
        f"- Distinct picks among eligible rows: {len(pick_counts)} "
        f"(from {len(eligible)} rows; {sum(rep.values()) - len(rep)} duplicate re-forecasts "
        f"dropped across {len(rep)} picks)."
    )
    w(
        f"- Matches carrying more than one distinct pick: {multi} of {len(fx_sel)}. "
        "These are correlated, so intervals are clustered by match.\n"
    )

    w("## 3. Headline comparison\n")
    w(HEAD)
    w(SEP)
    picked = {}
    for code, label, fn in groups:
        picked[code] = dedupe([r for r in eligible if fn(r)], PICK_KEY)
        w(row_md(f"{code}. {label}", summarise(picked[code], rng)))
    c_not_d = [r for r in picked["C"] if not in_d(r)]
    w(row_md("C∖D. passes C but not the QSS gate", summarise(c_not_d, rng)))
    no_qss = sum(1 for r in picked["C"] if r["qss"] is None)
    w("")
    w(f"Group C picks with no QSS recorded (fail D by omission, not by score): {no_qss}\n")

    for n_, dim, title, key in (
        (4, "market_label", "market", PICK_KEY),
        (5, "league_label", "league", PICK_KEY),
        (6, "model_label", "model version", PICK_KEY + ("model_version_id",)),
        (7, "month", "kickoff month (stability check)", PICK_KEY),
    ):
        w(f"## {n_}. By {title}\n")
        if dim == "model_label":
            w(
                "Per-version picks are de-duplicated within each version, so two versions "
                "forecasting the same pick are both counted here (and once in the headline).\n"
            )
        for v in sorted({r[dim] for r in eligible}):
            sub = [r for r in eligible if r[dim] == v]
            w(f"### {v}\n")
            w(HEAD)
            w(SEP)
            for code, label, fn in groups:
                g = dedupe([r for r in sub if fn(r)], key)
                w(row_md(f"{code}. {label}", summarise(g, rng)))
            w("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test a selection rule on archived forecasts.")
    parser.add_argument("csv", help="CSV written by extract.py")
    parser.add_argument("--label", help="source label shown in the report header")
    parser.add_argument("--out", help="write the Markdown report here (default: stdout)")
    parser.add_argument(
        "--include-research",
        action="store_true",
        help="also count research/shadow rows (secondary view only)",
    )
    parser.add_argument("--p-min", type=float, default=Rule.p_min)
    parser.add_argument("--ev-min", type=float, default=Rule.ev_min)
    parser.add_argument("--qss-min", type=float, default=Rule.qss_min)
    args = parser.parse_args(argv)

    text = report(
        load(args.csv),
        args.label or args.csv,
        Rule(args.p_min, args.ev_min, args.qss_min),
        args.include_research,
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
