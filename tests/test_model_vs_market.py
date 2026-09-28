"""Known-answer tests for scripts/rule_test/model_vs_market.py (synthetic extract rows)."""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
import pytest

from scripts.rule_test import model_vs_market as M

KICKOFF = pd.Timestamp("2026-09-20 15:00", tz="UTC")


def _row(**over) -> dict:
    row = {
        "id": str(uuid.uuid4()), "fixture_id": str(uuid.uuid4()),
        "market": "1X2", "selection": "home", "line": None,
        "decision_as_of": KICKOFF - pd.Timedelta(hours=2), "kickoff_utc": KICKOFF,
        "ensemble_probability": 0.5, "calibrated_probability": 0.5,
        "conservative_probability": 0.45, "fair_market_probability": 0.5,
        "executable_odds": 1.9, "research_mode": False, "gate_passed": False,
        "fixture_status": "finished", "home_goals": 2, "away_goals": 1,
        "league": "Test League", "outcome": None,
    }
    row.update(over)
    return row


def _load(rows: list[dict], tmp_path) -> pd.DataFrame:
    path = tmp_path / "extract.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return M.load(str(path))


def test_grades_from_final_score_with_the_production_grader(tmp_path):
    df = _load([
        _row(),  # 2-1 home win
        _row(selection="away"),
        _row(market="TOTALS", selection="over", line=3.0),  # 3 goals on a 3.0 line
        _row(home_goals=None, away_goals=None),
        _row(fixture_status="in_play"),  # partial score is not a result
        _row(market="CORNERS", selection="over", line=9.5),
    ], tmp_path)
    assert list(df["score_outcome"]) == [
        "win", "loss", "push", "no score", "not finished", "ungradable"]


def test_live_cohort_drops_post_kickoff_and_superseded_rows(tmp_path):
    fid = str(uuid.uuid4())
    df = _load([
        _row(fixture_id=fid, calibrated_probability=0.40,
             decision_as_of=KICKOFF - pd.Timedelta(hours=6)),
        _row(fixture_id=fid, calibrated_probability=0.55,
             decision_as_of=KICKOFF - pd.Timedelta(hours=1)),
        _row(decision_as_of=KICKOFF + pd.Timedelta(minutes=5)),
        _row(research_mode=True),
    ], tmp_path)
    graded, audit = M.prepare(df, research=False)
    assert audit["other-cohort rows excluded"] == 1
    assert audit["post-kickoff rows excluded"] == 1
    assert audit["superseded re-forecasts excluded"] == 1
    assert len(graded) == 1
    assert graded["calibrated_probability"].item() == pytest.approx(0.55)  # latest kept


def test_research_cohort_keeps_post_kickoff_rows_but_reports_them(tmp_path):
    df = _load([_row(research_mode=True, decision_as_of=KICKOFF + pd.Timedelta(days=1)),
                _row()], tmp_path)
    graded, audit = M.prepare(df, research=True)
    assert audit["post-kickoff decision_as_of (kept, research)"] == 1
    assert len(graded) == 1


def test_settlement_that_disagrees_with_the_score_is_counted(tmp_path):
    df = _load([_row(outcome="loss"), _row(outcome="win")], tmp_path)
    _, audit = M.prepare(df, research=False)
    assert audit["settlement disagrees with final score"] == 1


def test_coherence_flags_double_chance_devigged_as_if_exclusive(tmp_path):
    rows = []
    for _ in range(5):
        fid = str(uuid.uuid4())
        # 1X2 correctly de-vigged: sums to 1.
        rows += [_row(fixture_id=fid, selection=s, fair_market_probability=p)
                 for s, p in (("home", 0.5), ("draw", 0.25), ("away", 0.25))]
        # Double Chance de-vigged as a 3-way exclusive market: sums to 1, should be 2.
        rows += [_row(fixture_id=fid, market="DOUBLE_CHANCE", selection=s,
                      fair_market_probability=p)
                 for s, p in (("1X", 0.375), ("12", 0.375), ("X2", 0.25))]
    coh = M.coherence(_load(rows, tmp_path)).set_index("market")
    assert coh.loc["1X2", "status"] == "ok"
    assert coh.loc["DOUBLE_CHANCE", "status"] == "INCOHERENT"
    assert coh.loc["DOUBLE_CHANCE", "mean sum"] == pytest.approx(1.0)


def test_coherence_passes_a_correct_double_chance_book(tmp_path):
    fid = str(uuid.uuid4())
    rows = [_row(fixture_id=fid, market="DOUBLE_CHANCE", selection=s, fair_market_probability=p)
            for s, p in (("1X", 0.75), ("12", 0.75), ("X2", 0.5))]
    coh = M.coherence(_load(rows, tmp_path)).set_index("market")
    assert coh.loc["DOUBLE_CHANCE", "status"] == "ok"


def _simulated(truth_is_market: bool, n: int = 1500) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    p_true = rng.uniform(0.2, 0.8, n)
    noisy = np.clip(p_true + rng.normal(0, 0.12, n), 0.02, 0.98)
    model, market = (noisy, p_true) if truth_is_market else (p_true, noisy)
    return pd.DataFrame({
        "fixture_id": [str(i) for i in range(n)],
        "calibrated_probability": model, "fair_market_probability": market,
        "y": (rng.uniform(size=n) < p_true).astype(float),
    })


def test_paired_brier_detects_the_better_forecaster():
    market_wins = M.paired(_simulated(truth_is_market=True), "calibrated_probability")
    assert market_wins["95% CI lo"] > 0
    assert market_wins["P(model better)"] < 0.01
    model_wins = M.paired(_simulated(truth_is_market=False), "calibrated_probability")
    assert model_wins["95% CI hi"] < 0
    assert model_wins["P(model better)"] > 0.99


def test_paired_brier_resamples_whole_fixtures():
    df = _simulated(truth_is_market=True, n=400)
    one_fixture = df.assign(fixture_id="same")
    assert M.paired(one_fixture, "calibrated_probability") == {"n": 400}


def test_edge_table_without_market_prices_explains_itself():
    df = _simulated(truth_is_market=True, n=10).assign(fair_market_probability=np.nan)
    assert "note" in M.edge_table(df, "calibrated_probability").columns


def test_report_end_to_end_separates_cohorts_and_excludes_incoherent_markets(tmp_path):
    rows = []
    for i in range(40):
        fid = str(uuid.uuid4())
        rows.append(_row(fixture_id=fid, home_goals=i % 3, away_goals=1))
        rows += [_row(fixture_id=fid, market="DOUBLE_CHANCE", selection=s,
                      fair_market_probability=1 / 3, research_mode=True, home_goals=i % 3,
                      away_goals=1)
                 for s in ("1X", "12", "X2")]
    path = tmp_path / "extract.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    out = tmp_path / "report.md"
    assert M.main([str(path), "--label", "synthetic", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "## LIVE forecasts" in text and "## RESEARCH / shadow forecasts" in text
    assert "INCOHERENT" in text
    assert "excludes INCOHERENT markets: DOUBLE_CHANCE" in text
