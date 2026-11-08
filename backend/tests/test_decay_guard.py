from datetime import date, timedelta
from app.services.recommendation_ledger import (
    _decay_guard,
    _source_assessment,
    walk_forward_accumulator_selections,
)

WON, LOST, PENDING = 'won', 'lost', 'pending'


def row(day, market, result, odds=2.0, versions=('v1',), sources=('published',)):
    return {
        'target_date': day.isoformat(),
        'market': market,
        'result': result,
        'odds': odds,
        'model_versions': set(versions),
        'sources': set(sources),
    }


def test_decay_guard_young_cohort_passes():
    history = [row(date(2026, 10, 1) + timedelta(days=i), 'm', WON) for i in range(4)]
    passes, n, roi = _decay_guard(history, 1.0, window=10, min_roi=0.0)
    assert passes is True
    assert n == 4
    assert roi is None


def test_decay_guard_recent_window_votes():
    base = date(2026, 10, 1)
    # 15 wins then 10 losses: full history is positive, recent window is not.
    history = [row(base + timedelta(days=i), 'm', WON) for i in range(15)]
    history += [row(base + timedelta(days=15 + i), 'm', LOST) for i in range(10)]
    passes, n, roi = _decay_guard(history, 1.0, window=10, min_roi=0.0)
    assert passes is False
    assert n == 10
    assert roi == -1.0
    # Recover the last five picks and the window returns to break-even.
    for entry in history[-5:]:
        entry['result'] = WON
    passes, n, roi = _decay_guard(history, 1.0, window=10, min_roi=0.0)
    assert passes is True
    assert roi == 0.0


def test_decay_guard_ignores_pending_and_voids():
    base = date(2026, 10, 1)
    history = [row(base + timedelta(days=i), 'm', WON) for i in range(9)]
    history.append(row(base + timedelta(days=9), 'm', PENDING))
    passes, n, roi = _decay_guard(history, 1.0, window=10, min_roi=0.0)
    assert passes is True  # only 9 settled rows: too young to judge
    assert n == 9


def _two_market_days():
    """Away win decays after qualifying; Over 2.5 stays healthy."""
    base = date(2026, 10, 1)
    days = []
    for i in range(25):
        day = base + timedelta(days=i)
        if i < 15:
            days.append(row(day, 'away_win', WON))
        else:
            days.append(row(day, 'away_win', LOST))
        if i < 5:
            days.append(row(day, 'over_2.5', WON))
        else:
            days.append(row(day, 'over_2.5', WON if i % 2 == 0 else LOST))
    return days


def test_walk_forward_suspends_decayed_market():
    result = walk_forward_accumulator_selections(_two_market_days())
    suspended = {entry['market']: entry for entry in result['all_unique']['suspended_markets']}
    assert 'away_win' in suspended
    # Final evaluation sees days 14-23: 1 win, 9 losses.
    assert suspended['away_win']['recent_roi'] == -0.8
    assert suspended['away_win']['recent_picks'] == 10
    # qualifying_markets lists every market that ever qualified; the
    # suspended list carries the current state, so a decayed market stays
    # in the former but must not contribute legs on the final day.
    qualifying = {entry['market'] for entry in result['all_unique']['qualifying_markets']}
    assert 'over_2.5' in qualifying
    assert 'over_2.5' not in suspended
    # The last day's selections contain no decayed-market legs.
    last_day = max({r['target_date'] for r in _two_market_days()})
    last_rows = [r for r in result['all_unique']['rows'] if r['target_date'] == last_day]
    assert all(r['market'] != 'away_win' for r in last_rows)
    assert result['thresholds']['decay_window'] == 10


def test_source_assessment_demotes_trailing_strongest():
    assessment = _source_assessment({
        'published': {'roi': -0.004, 'hit_rate': 0.674},
        'strongest': {'roi': -0.053, 'hit_rate': 0.571},
    })
    assert assessment['published']['weight'] == 'primary'
    assert assessment['strongest']['weight'] == 'research_only'
    assert 'trails' in assessment['strongest']['note']

    assessment = _source_assessment({
        'published': {'roi': -0.004, 'hit_rate': 0.674},
        'strongest': {'roi': 0.01, 'hit_rate': 0.6},
    })
    assert assessment['strongest']['weight'] == 'secondary'
    assert assessment['strongest']['note'] is None
