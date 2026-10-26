from copy import deepcopy

import pytest

from app.services.frozen_score_cohort import code_digest, digest, score


def manifest():
    row = dict(prediction_id=10, match_id=1, competition_id=2, market="home_win",
               kickoff_at="2026-10-25T11:00:00+00:00", forecast_at="2026-10-25T04:04:00+00:00",
               poisson_prob=0.8, model_probability=0.7,
               score_distribution_parameters=dict(home_rate=1.5, away_rate=1.0, dixon_coles_rho=0.0))
    history = [dict(match_id=i + 100, market="home_win", competition_id=2,
                    kickoff_at="2026-10-24T12:00:00+00:00", outcome=1) for i in range(30)]
    # Same-day outcomes must never enter the comparison baseline.
    history.append(dict(match_id=200, market="home_win", competition_id=2,
                        kickoff_at="2026-10-25T01:00:00+00:00", outcome=0))
    payload = dict(cohort_id="test", forecasts=[row], baseline_history=history,
                   analysis_code_sha256=code_digest())
    return dict(payload=payload, sha256=digest(payload))


def result(status="finished", home=2, away=0, excluded=False):
    return {1: dict(status=status, home_goals=home, away_goals=away,
                    excluded_from_models=excluded)}


def test_pending_and_missing_results_remain_in_denominator():
    for outcomes, disposition in [(result("scheduled", None, None), "scheduled"),
                                   ({}, "missing_match"),
                                   (result(home=None), "missing_or_invalid_score"),
                                   (result(excluded=True), "excluded_from_models")]:
        report = score(manifest(), outcomes)
        assert report["status"] == "awaiting_outcomes"
        assert report["total_forecasts"] == 1
        assert report["forecast_dispositions"] == {disposition: 1}
        assert report["markets"]["home_win"]["poisson_prob"]["model"]["brier"] is None


def test_saved_probabilities_and_earlier_day_baseline_are_scored():
    report = score(manifest(), result())
    field = report["markets"]["home_win"]["poisson_prob"]
    assert field["model"]["brier"] == pytest.approx(0.04)
    assert field["comparisons"]["competition"]["baseline"]["mean_probability"] == pytest.approx(31 / 32)
    assert report["score_rate_diagnostics"]["snapshot_match_count"] == 1
    assert report["resolved_score_fixtures"] == 1


def test_draw_no_bet_void_does_not_become_a_loss():
    frozen = manifest()
    frozen["payload"]["forecasts"][0]["market"] = "dnb_home"
    frozen["sha256"] = digest(frozen["payload"])
    report = score(frozen, result(home=1, away=1))
    assert report["forecast_dispositions"] == {"void": 1}
    assert report["markets"]["dnb_home"]["poisson_prob"]["model"]["n"] == 0
    assert report["resolved_score_fixtures"] == 1


def test_manifest_and_scorer_drift_fail_closed():
    frozen = manifest()
    modified = deepcopy(frozen)
    modified["payload"]["forecasts"][0]["poisson_prob"] = 0.9
    with pytest.raises(ValueError, match="checksum"):
        score(modified, result())
    frozen["payload"]["analysis_code_sha256"] = "changed"
    frozen["sha256"] = digest(frozen["payload"])
    with pytest.raises(ValueError, match="Analysis code changed"):
        score(frozen, result())
