import pytest

from app.models import MatchStatus
from app.services.fixture_ingestor import _extract_regulation_time_score, _map_status


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("FT", MatchStatus.FINISHED),
        ("AET", MatchStatus.FINISHED),
        ("PEN", MatchStatus.FINISHED),
        ("PST", MatchStatus.POSTPONED),
        ("CANC", MatchStatus.CANCELLED),
        ("ABD", MatchStatus.ABANDONED),
        ("AWD", MatchStatus.AWARDED),
        ("WO", MatchStatus.AWARDED),
    ],
)
def test_provider_fixture_statuses_preserve_unresolved_outcomes(status, expected):
    assert _map_status(status) == expected


@pytest.mark.parametrize("status", ["AET", "PEN"])
def test_extra_time_and_penalty_fixtures_use_the_provider_regulation_score(status):
    data = {
        "fixture": {"status": {"short": status}},
        "goals": {"home": 3, "away": 2},
        "score": {
            "fulltime": {"home": 1, "away": 1},
            "extratime": {"home": 3, "away": 2},
            "penalty": {"home": 5, "away": 4},
        },
    }

    assert _extract_regulation_time_score(data) == (1, 1)


def test_extra_time_result_without_regulation_score_fails_closed():
    data = {
        "fixture": {"status": {"short": "AET"}},
        "goals": {"home": 2, "away": 1},
        "score": {"fulltime": {"home": None, "away": None}},
    }

    assert _extract_regulation_time_score(data) == (None, None)


def test_regular_time_final_score_prefers_fulltime_and_falls_back_to_goals():
    fixture = {"fixture": {"status": {"short": "FT"}}, "goals": {"home": 2, "away": 0}}

    assert _extract_regulation_time_score({**fixture, "score": {"fulltime": {"home": 1, "away": 0}}}) == (1, 0)
    assert _extract_regulation_time_score(fixture) == (2, 0)


def test_live_extra_time_score_remains_the_current_live_score():
    data = {
        "fixture": {"status": {"short": "ET"}},
        "goals": {"home": 3, "away": 2},
        "score": {"fulltime": {"home": 1, "away": 1}},
    }

    assert _extract_regulation_time_score(data) == (3, 2)
