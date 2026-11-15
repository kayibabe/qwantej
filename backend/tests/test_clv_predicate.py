"""One definition of valid CLV, used by Analytics, the paper rules, and health.

The metric the whole forward experiment rests on used to be defined three
times (CLV gate, Analytics, health check) with slightly different rules. These
tests pin the single definition and the SQL counterpart.
"""
from datetime import datetime, timedelta, timezone
from itertools import product
from types import SimpleNamespace

from app.models import Match
from app.services.clv import (
    CLV_INVALID,
    CLV_UNMEASURED,
    CLV_VALID,
    clv_is_invalid,
    clv_is_valid,
    clv_measurement,
    invalid_clv_condition,
    valid_clv_condition,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=1)
KICKOFF = NOW + timedelta(hours=2)


def row(*, odds=2.0, clv=0.01, source=NOW, closing=LATER):
    return SimpleNamespace(
        closing_decimal_odds=odds,
        clv_percentage=clv,
        source_odds_at=source,
        closing_odds_at=closing,
    )


def test_valid_and_invalid_are_exact_complements():
    odds_values = [None, 0.0, 2.0]
    clv_values = [None, 0.01]
    time_values = [None, NOW, LATER]
    for odds, clv, source, closing in product(
        odds_values, clv_values, time_values, time_values
    ):
        prediction = row(odds=odds, clv=clv, source=source, closing=closing)
        assert clv_is_valid(prediction) is not clv_is_invalid(prediction)


def test_closing_must_be_strictly_after_the_entry_quote():
    assert clv_is_valid(row(source=NOW, closing=LATER))
    assert not clv_is_valid(row(source=NOW, closing=NOW))
    assert not clv_is_valid(row(source=LATER, closing=NOW))


def test_missing_pieces_are_never_valid():
    assert not clv_is_valid(row(odds=None))
    assert not clv_is_valid(row(clv=None))
    assert not clv_is_valid(row(source=None))
    assert not clv_is_valid(row(closing=None))


def test_a_post_kickoff_close_is_invalid_when_kickoff_is_supplied():
    prediction = row(closing=LATER)
    assert clv_is_valid(prediction, kickoff_at=KICKOFF)
    assert not clv_is_valid(prediction, kickoff_at=NOW + timedelta(minutes=30))
    # The complement follows the same argument.
    assert clv_is_invalid(prediction, kickoff_at=NOW + timedelta(minutes=30))


def test_measurement_separates_a_missing_quote_from_a_broken_close():
    # No usable close either way, but the cause decides whether the sample is
    # incomplete (capture gap) or the derivation is wrong (a real defect).
    unclosed = row(odds=None)
    assert clv_measurement(unclosed, has_post_entry_quote=True) == CLV_INVALID
    assert clv_measurement(unclosed, has_post_entry_quote=False) == CLV_UNMEASURED

    # A valid close is valid regardless of whether a later quote was observed.
    assert clv_measurement(row(), has_post_entry_quote=True) == CLV_VALID
    assert clv_measurement(row(), has_post_entry_quote=False) == CLV_VALID


def test_sql_conditions_cover_the_same_checks():
    plain = str(valid_clv_condition())
    assert "closing_decimal_odds IS NOT NULL" in plain
    assert "clv_percentage IS NOT NULL" in plain
    assert "source_odds_at IS NOT NULL" in plain
    assert "closing_odds_at IS NOT NULL" in plain
    assert "closing_odds_at > predictions.source_odds_at" in plain
    assert "kickoff_at" not in plain

    with_kickoff = str(valid_clv_condition(Match))
    assert "kickoff_at" in with_kickoff
    assert "closing_odds_at <=" in with_kickoff

    invalid = str(invalid_clv_condition())
    for column in ("source_odds_at", "closing_odds_at", "clv_percentage"):
        assert f"{column} IS NULL" in invalid
