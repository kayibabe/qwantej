"""Canonical definition of the five System Picks band-mix pairs.

The pairs use the same 5pp buckets as the UI band-mix filter and the
five-pairs backtest: (model probability band, stored bookmaker-implied band).
The Q-score is deliberately not part of a pair — band mix is about where the
model and the market sit, not about the model's quality score.

Bands are half-open [low, high); the top band includes exactly 1.0, matching
the UI's 95+ bucket (probabilityBand clamps 100% into 95-100).
"""

BAND_MIX_PAIRS: tuple[tuple[float, float, float, float], ...] = (
    (0.00, 0.50, 0.85, 0.90),   # <50% x 85-90%
    (0.50, 0.55, 0.90, 0.95),   # 50-55% x 90-95%
    (0.55, 0.60, 0.95, 1.00),   # 55-60% x 95-100%
    (0.60, 0.65, 0.90, 0.95),   # 60-65% x 90-95%
    (0.95, 1.00, 0.70, 0.75),   # 95-100% x 70-75%
)


def _upper_op(high: float) -> str:
    return '<=' if high >= 1.0 else '<'


def _within(value: float, low: float, high: float) -> bool:
    return low <= value <= high if high >= 1.0 else low <= value < high


def pair_label(index: int) -> str:
    m_lo, m_hi, i_lo, i_hi = BAND_MIX_PAIRS[index]
    model = '<50' if m_lo == 0.0 else f'{m_lo * 100:g}-{m_hi * 100:g}'
    implied = f'{i_lo * 100:g}-{i_hi * 100:g}'
    return f'{model}% x {implied}%'


def in_band_mix(model_probability, implied_probability) -> bool:
    """True when the two probabilities fit any of the five exact pairs."""
    for m_lo, m_hi, i_lo, i_hi in BAND_MIX_PAIRS:
        if _within(model_probability, m_lo, m_hi) and _within(implied_probability, i_lo, i_hi):
            return True
    return False


def band_mix_lateral() -> tuple[str, dict]:
    """One-pick-per-fixture lateral for the five pairs, with no Q predicate."""
    clauses = []
    params = {}
    for index, (m_lo, m_hi, i_lo, i_hi) in enumerate(BAND_MIX_PAIRS):
        clauses.append(
            f'(p.model_probability >= :m_lo_{index} AND p.model_probability {_upper_op(m_hi)} :m_hi_{index} '
            f'AND p.source_implied_probability >= :i_lo_{index} '
            f'AND p.source_implied_probability {_upper_op(i_hi)} :i_hi_{index})'
        )
        params.update({
            f'm_lo_{index}': m_lo,
            f'm_hi_{index}': m_hi,
            f'i_lo_{index}': i_lo,
            f'i_hi_{index}': i_hi,
        })
    lateral = f"""LEFT JOIN LATERAL (SELECT * FROM predictions p WHERE p.match_id=m.id
                    AND p.source_decimal_odds IS NOT NULL
                    AND ({' OR '.join(clauses)})
                    ORDER BY p.created_at,p.id LIMIT 1) p ON TRUE"""
    return lateral, params
