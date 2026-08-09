"""
ensemble.py — Combine ZINB + Bayesian + Elo into a weighted ensemble.

Weights are market-specific because each model has different strengths:
  - Goals markets (Over/Under): ZINB is primary (goal distributions)
  - 1X2/Double Chance: Elo is primary (match outcome ratings)
  - BTTS: ZINB is primary
  - Team goals (HO0.5, AO0.5): ZINB is primary

Default weights are configurable and will be calibrated in Phase 1C
via isotonic regression on ForecastSnapshot Brier scores.

Signal gate: signal_type = "SIGNAL" when value_edge > MIN_VALUE_EDGE.
All markets produce a row — NO_SIGNAL rows are archived to make
absence-of-signal measurable (needed for Brier calibration).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MODEL_VERSION = "1.0.0"
MIN_VALUE_EDGE = 0.03   # 3% minimum edge over fair price to call SIGNAL

# Market weights: {market: {model: weight}}
# Missing models get weight 0. Weights are normalised among available models.
_MARKET_WEIGHTS: dict[str, dict[str, float]] = {
    "Over 1.5":            {"zinb": 0.50, "bayesian": 0.50, "elo": 0.00},
    "Over 2.5":            {"zinb": 0.50, "bayesian": 0.50, "elo": 0.00},
    "Under 2.5":           {"zinb": 0.50, "bayesian": 0.50, "elo": 0.00},
    "Under 3.5":           {"zinb": 0.50, "bayesian": 0.50, "elo": 0.00},
    "BTTS Yes":            {"zinb": 0.50, "bayesian": 0.50, "elo": 0.00},
    "1X (Home or Draw)":   {"zinb": 0.30, "bayesian": 0.35, "elo": 0.35},
    "X2 (Draw or Away)":   {"zinb": 0.30, "bayesian": 0.35, "elo": 0.35},
    "Home Over 0.5":       {"zinb": 0.55, "bayesian": 0.45, "elo": 0.00},
    "Away Over 0.5":       {"zinb": 0.55, "bayesian": 0.45, "elo": 0.00},
}


@dataclass
class EnsembleResult:
    market: str
    zinb_prob: Optional[float]
    bayesian_prob: Optional[float]
    elo_prob: Optional[float]
    ensemble_prob: float
    confidence: str            # "High" | "Medium" | "Low"
    fair_odds: float           # 1 / ensemble_prob
    market_odds: Optional[float]
    value_edge: Optional[float]   # market_odds * ensemble_prob - 1
    is_value_bet: bool
    signal_type: str           # "SIGNAL" | "NO_SIGNAL"
    data_quality_score: float
    lambda_home: Optional[float] = None
    lambda_away: Optional[float] = None
    elo_home: Optional[float] = None
    elo_away: Optional[float] = None
    model_version: str = MODEL_VERSION


def _confidence(prob: float) -> str:
    if prob >= 0.70:
        return "High"
    if prob >= 0.55:
        return "Medium"
    return "Low"


def _data_quality(
    zinb_prob: Optional[float],
    bayesian_prob: Optional[float],
    elo_prob: Optional[float],
    market_odds: Optional[float],
) -> float:
    """0–1 score reflecting how many model inputs were available."""
    score = 0.0
    if zinb_prob is not None:
        score += 0.35
    if bayesian_prob is not None:
        score += 0.40
    if elo_prob is not None:
        score += 0.15
    if market_odds is not None:
        score += 0.10
    return round(score, 3)


def _weighted_ensemble(
    market: str,
    zinb_prob: Optional[float],
    bayesian_prob: Optional[float],
    elo_prob: Optional[float],
) -> float:
    """Compute weighted ensemble probability for a market."""
    weights = _MARKET_WEIGHTS.get(market, {"zinb": 0.40, "bayesian": 0.60, "elo": 0.00})
    probs = {
        "zinb": zinb_prob,
        "bayesian": bayesian_prob,
        "elo": elo_prob,
    }
    total_weight = 0.0
    weighted_sum = 0.0
    for model, w in weights.items():
        p = probs.get(model)
        if p is not None and 0.0 < p < 1.0:
            weighted_sum += w * p
            total_weight += w

    if total_weight == 0.0:
        # No model produced a valid probability — fall back to prior
        available = [p for p in (zinb_prob, bayesian_prob, elo_prob) if p is not None]
        return sum(available) / len(available) if available else 0.5

    # Renormalise among available models to preserve weight semantics
    return round(weighted_sum / total_weight, 6)


class EnsembleEngine:
    """
    Combines model outputs into EnsembleResult per market.

    Args:
        zinb_probs:     {market: prob} from ZINBMarketsModel
        bayesian_probs: {market: prob} from BayesianFixtureResult.market_results
        elo_1x2:        (p_home_win, p_draw, p_away_win) from EloSystem.predict_1x2
        market_odds:    {market: best_decimal_odd} from Bayesian / API-Football
        lambda_home:    expected home goals (from ZINB)
        lambda_away:    expected away goals (from ZINB)
        elo_home:       home Elo rating (raw, for archiving)
        elo_away:       away Elo rating (raw, for archiving)
    """

    def compute(
        self,
        zinb_probs: dict[str, float],
        bayesian_probs: dict[str, float],
        elo_1x2: tuple[float, float, float] | None,
        market_odds: dict[str, float],
        lambda_home: Optional[float] = None,
        lambda_away: Optional[float] = None,
        elo_home: Optional[float] = None,
        elo_away: Optional[float] = None,
    ) -> list[EnsembleResult]:

        # Map Elo 1X2 to the double-chance markets we serve
        elo_probs: dict[str, Optional[float]] = {}
        if elo_1x2 is not None:
            p_h, p_d, p_a = elo_1x2
            elo_probs["1X (Home or Draw)"] = round(p_h + p_d, 6)
            elo_probs["X2 (Draw or Away)"] = round(p_d + p_a, 6)

        results: list[EnsembleResult] = []
        from app.engines.zinb_markets import PHASE1A_MARKETS

        for market in PHASE1A_MARKETS:
            z_prob = zinb_probs.get(market)
            b_prob = bayesian_probs.get(market)
            e_prob = elo_probs.get(market)

            ensemble = _weighted_ensemble(market, z_prob, b_prob, e_prob)
            if ensemble <= 0.0:
                continue

            fair = round(1.0 / ensemble, 4) if ensemble > 0 else None
            m_odds = market_odds.get(market)
            edge = round(m_odds * ensemble - 1.0, 4) if m_odds and m_odds > 1.0 else None
            is_value = edge is not None and edge >= MIN_VALUE_EDGE
            signal_type = "SIGNAL" if is_value else "NO_SIGNAL"
            conf = _confidence(ensemble)
            dq = _data_quality(z_prob, b_prob, e_prob, m_odds)

            results.append(EnsembleResult(
                market=market,
                zinb_prob=z_prob,
                bayesian_prob=b_prob,
                elo_prob=e_prob,
                ensemble_prob=ensemble,
                confidence=conf,
                fair_odds=fair,
                market_odds=m_odds,
                value_edge=edge,
                is_value_bet=is_value,
                signal_type=signal_type,
                data_quality_score=dq,
                lambda_home=lambda_home,
                lambda_away=lambda_away,
                elo_home=elo_home,
                elo_away=elo_away,
            ))

        return results
