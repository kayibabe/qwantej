"""Guard against the UI, paper rule, and backtest drifting apart."""

import importlib.util
from pathlib import Path

from app.services.band_mix import BAND_MIX_PAIRS, in_band_mix


def test_backtest_uses_the_same_five_pairs():
    path = Path(__file__).parents[1] / 'scripts' / 'band_mix_five_pairs_backtest.py'
    spec = importlib.util.spec_from_file_location('band_mix_backtest', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = []
    for m_lo, m_hi, i_lo, i_hi in BAND_MIX_PAIRS:
        model = '<50' if m_lo == 0 else f'{m_lo * 100:g}-{m_hi * 100:g}'
        implied = f'{i_lo * 100:g}-{i_hi * 100:g}'
        expected.append((model, implied))
    assert module.BAND_MIX_PAIRS == expected


def test_pair_bounds_match_the_ui_buckets():
    assert in_band_mix(0.499, 0.87)
    assert not in_band_mix(0.50, 0.87)
    assert in_band_mix(0.50, 0.90)
    assert in_band_mix(0.95, 0.70)
    assert in_band_mix(1.0, 0.72)    # 100% still lands in the UI's 95-100 bucket
    assert not in_band_mix(0.97, 0.62)
