import pytest

from app.services.over45 import summarize_samples


def test_all_lines_use_equal_team_weights_and_complement():
    samples = {
        "home": [dict(id=1, scored=0, conceded=0)],
        "away": [dict(id=2, scored=2, conceded=1), dict(id=3, scored=5, conceded=0)],
    }
    evidence = summarize_samples(samples)
    for n, expected in enumerate([.5, .5, .5, .25, .25]):
        assert evidence["metrics"][f"over{n}5_frequency"] == pytest.approx(expected)
        assert evidence["metrics"][f"under{n}5_frequency"] == pytest.approx(1 - expected)
    assert evidence["recent_matches"] == samples
    assert evidence["metrics"]["projected_xg"] is None


def test_absent_team_sample_is_unknown_not_zero():
    evidence = summarize_samples({"home": [], "away": [dict(id=1, scored=0, conceded=0)]})
    for n in range(5):
        assert evidence["metrics"][f"over{n}5_frequency"] is None
        assert evidence["metrics"][f"under{n}5_frequency"] is None
