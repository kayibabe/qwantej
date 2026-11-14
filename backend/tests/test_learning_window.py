"""The weekly challenger window must be clamped, never invalid.

Regression guard for the fix that stopped the learning loop idling for weeks:
once the prospective holdout has started, a requested window that reaches
earlier is clamped to the holdout start instead of being skipped. The clamp has
to preserve the ordering that ``train_learning_challenger`` enforces.
"""
from datetime import date, timedelta

import pytest

from app.services.model_learning import resolve_learning_window

HOLDOUT = date(2026, 11, 10)


def test_before_the_holdout_starts_the_run_is_skipped():
    assert resolve_learning_window(
        validation_end=HOLDOUT - timedelta(days=1),
        validation_not_before=HOLDOUT,
        validation_days=7,
        train_days=90,
    ) is None


def test_short_window_is_clamped_to_the_holdout_start():
    window = resolve_learning_window(
        validation_end=date(2026, 11, 13),
        validation_not_before=HOLDOUT,
        validation_days=7,
        train_days=90,
    )
    assert window.requested_start == date(2026, 11, 7)
    assert window.start == HOLDOUT
    assert window.clamped is True
    assert window.end == date(2026, 11, 13)
    # Training stops the day before validation, never inside the holdout.
    assert window.train_end == date(2026, 11, 9)
    assert window.train_start == date(2026, 11, 9) - timedelta(days=89)


def test_window_fully_inside_the_holdout_is_not_clamped():
    window = resolve_learning_window(
        validation_end=date(2026, 12, 20),
        validation_not_before=HOLDOUT,
        validation_days=7,
        train_days=90,
    )
    assert window.requested_start == window.start == date(2026, 12, 14)
    assert window.clamped is False


@pytest.mark.parametrize("end_offset", range(0, 120, 7))
def test_resolved_window_always_satisfies_the_challenger_invariant(end_offset):
    window = resolve_learning_window(
        validation_end=HOLDOUT + timedelta(days=end_offset),
        validation_not_before=HOLDOUT,
        validation_days=7,
        train_days=90,
    )
    assert window.train_start <= window.train_end < window.start <= window.end


@pytest.mark.parametrize("validation_days,train_days", [(0, 90), (7, 0), (-1, 90)])
def test_degenerate_periods_are_rejected(validation_days, train_days):
    with pytest.raises(ValueError):
        resolve_learning_window(
            validation_end=date(2026, 11, 13),
            validation_not_before=HOLDOUT,
            validation_days=validation_days,
            train_days=train_days,
        )
