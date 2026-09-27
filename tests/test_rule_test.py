"""Known-answer tests for scripts/rule_test/analyze.py (synthetic archive rows)."""

from __future__ import annotations

import csv
import random

import pytest

from scripts.rule_test import analyze as A

COLS = [
    "id",
    "fixture_id",
    "market",
    "selection",
    "line",
    "prediction_timestamp",
    "decision_as_of",
    "quote_timestamp",
    "created_at",
    "ensemble_probability",
    "calibrated_probability",
    "conservative_probability",
    "fair_market_probability",
    "executable_odds",
    "bookmaker",
    "edge_pp",
    "expected_value",
    "dqs",
    "qss",
    "lrs",
    "mrs",
    "research_mode",
    "gate_passed",
    "model_version_id",
    "feature_version",
    "calibration_version",
    "risk_policy_version",
    "code_commit",
    "model_name",
    "model_version",
    "model_family",
    "kickoff_utc",
    "fixture_status",
    "home_goals",
    "away_goals",
    "league",
    "league_country",
    "league_validated",
    "outcome",
    "settled_at",
    "profit_loss",
    "stake",
    "taken_odds",
    "closing_odds",
    "clv",
    "n_effective",
    "n_settlement_rows",
]

T0, KO = "2026-09-01 10:00:00+00:00", "2026-09-01 15:00:00+00:00"
LATER = "2026-09-01 11:00:00+00:00"


def _row(i, fx, sel, p, odds, qss, hg, ag, outcome, **kw):
    r = dict.fromkeys(COLS, "")
    r.update(
        id=f"p{i}",
        fixture_id=fx,
        market="1X2",
        selection=sel,
        prediction_timestamp=T0,
        decision_as_of=T0,
        quote_timestamp=T0,
        created_at=T0,
        conservative_probability=p,
        executable_odds=odds,
        expected_value=round(p * odds - 1, 5),
        qss=qss,
        research_mode="f",
        gate_passed="t",
        model_version_id="m1",
        model_name="poisson",
        model_version="1.0",
        kickoff_utc=KO,
        fixture_status="finished",
        home_goals=hg,
        away_goals=ag,
        league="Premier League",
        league_country="England",
        outcome=outcome,
        n_effective=1,
        n_settlement_rows=1,
    )
    r.update(kw)
    return r


ROWS = [
    # Passes the rule: P .75, odds 1.5 (EV +.125), QSS 90; home win.
    _row(1, "f1", "home", 0.75, 1.50, 90, 2, 0, "win"),
    # Later re-forecast of the same pick: must be de-duplicated away.
    _row(
        2,
        "f1",
        "home",
        0.76,
        1.50,
        91,
        2,
        0,
        "win",
        decision_as_of=LATER,
        prediction_timestamp=LATER,
    ),
    # Group C but QSS 80; away pick loses.
    _row(3, "f2", "away", 0.72, 1.45, 80, 1, 0, "loss"),
    # Group B only: EV .71 * 1.3 - 1 < 0.
    _row(4, "f3", "home", 0.71, 1.30, 95, 1, 0, "win"),
    # Group A only: P .40.
    _row(5, "f4", "draw", 0.40, 3.40, 70, 0, 0, "win"),
    # Group C with no QSS recorded.
    _row(6, "f5", "home", 0.74, 1.50, "", 0, 1, "loss"),
    # Excluded: archived after kickoff.
    _row(7, "f6", "home", 0.80, 1.40, 95, 1, 0, "win", created_at="2026-09-01 16:00:00+00:00"),
    # Excluded: settlement disagrees with the 1-0 scoreline.
    _row(8, "f7", "home", 0.80, 1.40, 95, 1, 0, "loss"),
    # Excluded unless research rows are requested.
    _row(9, "f8", "home", 0.80, 1.40, 95, 1, 0, "win", research_mode="t"),
    # Excluded: unsettled.
    _row(10, "f9", "home", 0.80, 1.40, 95, "", "", ""),
]


@pytest.fixture()
def archive_csv(tmp_path):
    path = tmp_path / "archive.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(ROWS)
    return path


@pytest.fixture()
def rows(archive_csv):
    return A.load(str(archive_csv))


def _groups(eligible, rule=None):
    return {
        code: A.dedupe([r for r in eligible if fn(r)], A.PICK_KEY)
        for code, _, fn in (rule or A.Rule()).groups()
    }


def test_audit_excludes_each_invalid_row_for_its_reason(rows):
    eligible, reasons = A.audit(rows)

    assert sorted(r["id"] for r in eligible) == ["p1", "p2", "p3", "p4", "p5", "p6"]
    assert reasons["timing: archived (created_at) after kickoff"] == 1
    assert reasons["settlement disagrees with scoreline"] == 1
    assert reasons[A.RESEARCH_REASON] == 1
    assert reasons["no effective settlement (unsettled / pending)"] == 1
    # Stored EV is rounded to 5 dp; rounding alone must not be flagged.
    assert "EV inconsistent with P_cons x odds" not in reasons


def test_research_rows_only_counted_on_request(rows):
    eligible, reasons = A.audit(rows, include_research=True)

    assert "p9" in {r["id"] for r in eligible}
    assert A.RESEARCH_REASON not in reasons


def test_groups_are_nested_and_keep_the_first_forecast_per_pick(rows):
    eligible, _ = A.audit(rows)
    g = _groups(eligible)

    assert [r["id"] for r in g["D"]] == ["p1"]
    assert sorted(r["id"] for r in g["C"]) == ["p1", "p3", "p6"]
    assert sorted(r["id"] for r in g["B"]) == ["p1", "p3", "p4", "p6"]
    assert len(g["A"]) == 5


def test_custom_thresholds_change_membership(rows):
    eligible, _ = A.audit(rows)
    g = _groups(eligible, A.Rule(p_min=0.70, ev_min=0.0, qss_min=75.0))

    assert sorted(r["id"] for r in g["D"]) == ["p1", "p3"]


def test_summary_metrics_match_hand_calculation(rows):
    eligible, _ = A.audit(rows)
    g = _groups(eligible)
    rng = random.Random(1)

    s_a = A.summarise(g["A"], rng)
    # Profits: p1 +.5, p3 -1, p4 +.3, p5 +2.4, p6 -1 -> +1.2 over 5 stakes.
    assert s_a["units"] == pytest.approx(1.2)
    assert s_a["roi"] == pytest.approx(0.24)
    assert (s_a["W"], s_a["L"], s_a["matches"]) == (3, 2, 5)
    assert s_a["roi_ci"][0] <= s_a["roi"] <= s_a["roi_ci"][1]

    s_c = A.summarise(g["C"], rng)
    assert s_c["hit"] == pytest.approx(1 / 3)
    assert s_c["units"] == pytest.approx(-1.5)
    assert s_c["mean_p"] == pytest.approx((0.75 + 0.72 + 0.74) / 3)


def test_wilson_interval_matches_reference_values():
    lo, hi = A.wilson(1, 3)

    assert lo == pytest.approx(0.0615, abs=1e-3)
    assert hi == pytest.approx(0.7923, abs=1e-3)
    assert A.wilson(0, 0) == (None, None)


def test_per_version_dedupe_keeps_one_row_per_version(rows):
    eligible, _ = A.audit(rows)

    assert len(A.dedupe(eligible, A.PICK_KEY + ("model_version_id",))) == 5


@pytest.mark.parametrize(
    ("market", "selection", "line", "hg", "ag", "expected"),
    [
        ("TOTALS", "over", 2.0, 1, 1, "push"),
        ("TOTALS", "under", 2.5, 1, 1, "win"),
        ("DOUBLE_CHANCE", "X2", None, 0, 0, "win"),
        ("DOUBLE_CHANCE", "12", None, 0, 0, "loss"),
        ("BTTS", "yes", None, 1, 0, "loss"),
        ("1X2", "away", None, 0, 2, "win"),
        ("UNKNOWN", "x", None, 1, 0, None),
    ],
)
def test_recompute_mirrors_settlement_rules(market, selection, line, hg, ag, expected):
    row = {
        "home_goals": hg,
        "away_goals": ag,
        "market": market,
        "selection": selection,
        "line": line,
    }

    assert A.recompute(row) == expected


def test_cli_writes_report(archive_csv, tmp_path):
    out = tmp_path / "report.md"

    assert A.main([str(archive_csv), "--label", "synthetic", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Source: **synthetic**" in text
    assert "| D. P >= 70% & EV > 0% & QSS >= 82 (rule) | 1 |" in text
