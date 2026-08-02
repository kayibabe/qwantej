"""
zinb_goals.py — ZINB-based total goals market selector.

Evaluates Over 1.5, Over 2.5, Under 2.5, Under 3.5 using home_xg / away_xg
(ZINB-fitted expected goals, or form-lambda fallback).  Returns the single best
qualifying market per fixture; caller writes a separate Signal row alongside
any Hybrid B signal.

Thresholds (team-level conditions from ZINB calibration research):

  Market    | EXCELLENT                                | GOOD
  ──────────|──────────────────────────────────────────|──────────────────────────
  Over 1.5  | total≥4.5, H≥1.0, A≥1.0,               | total≥2.7, max≥1.2, min≥0.6
            | max≥1.5, min≥0.6                         |
  Over 2.5  | total≥3.8, H≥1.3, A≥1.3,               | total≥3.3, max≥1.5, min≥0.6,
            | max≥1.7, |diff|≤1.8                      | |diff|≤1.8
  Under 2.5 | total≤1.8, H≤1.0, A≤1.0, max≤1.2       | total≤2.2, H≤1.3, A≤1.3
  Under 3.5 | total≤2.4, H≤1.3, A≤1.3, max≤1.7       | total≤3.0, max≤2.2

Multi-market tie-break (within same confidence tier, reliability-ranked):
  Under 3.5 > Over 1.5 > Over 2.5 > Under 2.5
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ZinbGoalsResult:
    market: str          # "Over 1.5" | "Over 2.5" | "Under 2.5" | "Under 3.5"
    confidence: str      # "EXCELLENT" | "GOOD"
    total_lambda: float
    home_lambda: float
    away_lambda: float
    rule_key: str        # "zinb_o15" | "zinb_o25" | "zinb_u25" | "zinb_u35"


def _classify_over15(lh: float, la: float) -> Optional[str]:
    total = lh + la
    mx, mn = max(lh, la), min(lh, la)
    if total >= 4.5 and lh >= 1.0 and la >= 1.0 and mx >= 1.5 and mn >= 0.6:
        return "EXCELLENT"
    if total >= 2.7 and mx >= 1.2 and mn >= 0.6:
        return "GOOD"
    return None


def _classify_over25(lh: float, la: float) -> Optional[str]:
    total = lh + la
    diff = abs(lh - la)
    if total >= 3.8 and lh >= 1.3 and la >= 1.3 and max(lh, la) >= 1.7 and diff <= 1.8:
        return "EXCELLENT"
    if total >= 3.3 and max(lh, la) >= 1.5 and min(lh, la) >= 0.6 and diff <= 1.8:
        return "GOOD"
    return None


def _classify_under25(lh: float, la: float) -> Optional[str]:
    total = lh + la
    mx = max(lh, la)
    if total <= 1.8 and lh <= 1.0 and la <= 1.0 and mx <= 1.2:
        return "EXCELLENT"
    if total <= 2.2 and lh <= 1.3 and la <= 1.3:
        return "GOOD"
    return None


def _classify_under35(lh: float, la: float) -> Optional[str]:
    total = lh + la
    if total <= 2.4 and lh <= 1.3 and la <= 1.3 and max(lh, la) <= 1.7:
        return "EXCELLENT"
    if total <= 3.0 and max(lh, la) <= 2.2:
        return "GOOD"
    return None


# Ordered by descending reliability — the tie-break order within the same tier.
_MARKET_CLASSIFIERS = [
    ("Under 3.5", "zinb_u35", _classify_under35),
    ("Over 1.5",  "zinb_o15", _classify_over15),
    ("Over 2.5",  "zinb_o25", _classify_over25),
    ("Under 2.5", "zinb_u25", _classify_under25),
]

_CONF_RANK = {"EXCELLENT": 2, "GOOD": 1}


def evaluate(home_xg: float, away_xg: float) -> Optional[ZinbGoalsResult]:
    """
    Return the single best qualifying ZINB goals market signal.
    Returns None when no market passes its threshold.
    """
    if home_xg <= 0 or away_xg <= 0:
        return None

    total = home_xg + away_xg
    candidates: list[ZinbGoalsResult] = []

    for market_name, rule_key, classifier in _MARKET_CLASSIFIERS:
        conf = classifier(home_xg, away_xg)
        if conf:
            candidates.append(ZinbGoalsResult(
                market=market_name,
                confidence=conf,
                total_lambda=round(total, 4),
                home_lambda=round(home_xg, 4),
                away_lambda=round(away_xg, 4),
                rule_key=rule_key,
            ))

    if not candidates:
        return None

    # Highest confidence wins; insertion order (reliability priority) breaks ties.
    return max(candidates, key=lambda r: _CONF_RANK[r.confidence])
