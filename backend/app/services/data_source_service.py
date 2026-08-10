"""
data_source_service.py — Data Value Score computation for external data sources.

Formula (per strategy document):
    DVS = 0.30 × Accuracy
        + 0.20 × Calibration
        + 0.20 × ROI
        + 0.15 × Coverage
        + 0.10 × Timeliness
        + 0.05 × Cost

All component scores are normalised to [0, 1] where 1 = best.

Components
----------
Accuracy (0-1):
    Derived from Brier improvement vs. baseline: improvement / max_improvement.
    Capped at 1.0 for negative Brier improvement (source hurts accuracy → 0.0).

Calibration (0-1):
    Uses external_forecasts Brier scores: 1 - avg_brier / naive_brier.
    naive_brier = 0.25 (maximum for a binary predictor at 50% baseline).

ROI (0-1):
    Simulated flat-stake ROI using external_forecasts predictions as signals:
    (sum(payout) - sum(stake)) / sum(stake).
    Normalised from [-1, +0.5] → [0, 1].

Coverage (0-1):
    % of historical fixtures in our DB where this source has a prediction row.
    Coverage = matched_predictions / total_fixtures.

Timeliness (0-1):
    Static per-source lookup — how early (pre-match) the data is available.
    Real-time (API-Football) = 1.0; post-match only (historical CSVs) = 0.4.

Cost (0-1):
    Static per-source lookup — 1.0 = fully free, lower for commercial licenses.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source_experiment import DataSourceExperiment
from app.models.external_forecast import ExternalForecast

logger = logging.getLogger(__name__)

# ── Static per-source lookup tables ──────────────────────────────────────────

_TIMELINESS: dict[str, float] = {
    "api_football":        1.0,   # real-time odds + fixture data
    "forebet":             0.85,  # D-1 predictions (evening before)
    "betmines":            0.85,
    "socceraitips":        0.80,
    "socceroracle":        0.80,
    "nerdy_tips":          0.75,
    "football_data_co_uk": 0.45,  # published the day after match completion
    "openfootball":        0.40,  # curated historical, delayed publish
    "statsbomb":           0.40,  # historical only
}

_COST: dict[str, float] = {
    "api_football":        0.65,  # paid API plan
    "forebet":             1.00,  # free public scrape
    "betmines":            0.90,  # free with rate limits
    "socceraitips":        0.90,
    "socceroracle":        0.90,
    "nerdy_tips":          0.90,
    "football_data_co_uk": 1.00,  # free CSV download
    "openfootball":        1.00,  # open data
    "statsbomb":           0.30,  # commercial license for full dataset
}

# ── Score normalisation helpers ───────────────────────────────────────────────

_DVS_WEIGHTS = {
    "accuracy":    0.30,
    "calibration": 0.20,
    "roi":         0.20,
    "coverage":    0.15,
    "timeliness":  0.10,
    "cost":        0.05,
}

_NAIVE_BRIER = 0.25   # worst-case for a 50/50 binary predictor
_MAX_ROI = 0.50       # normalise ROI relative to 50% (excellent for this domain)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _accuracy_score(brier_improvement: float, baseline_brier: float) -> float:
    """Brier improvement expressed as a fraction of the naive Brier baseline."""
    if baseline_brier <= 0:
        return 0.5
    # brier_improvement = baseline_brier - source_brier (positive = better)
    return _clamp(brier_improvement / _NAIVE_BRIER)


def _calibration_score(avg_brier: Optional[float]) -> float:
    """How well-calibrated is the source? Lower Brier = better."""
    if avg_brier is None:
        return 0.5   # unknown → neutral
    return _clamp(1.0 - avg_brier / _NAIVE_BRIER)


def _roi_score(roi_decimal: float) -> float:
    """
    ROI from flat-stake simulation, normalised from [-1, +MAX_ROI] → [0, 1].
    An ROI of 0% (break-even) maps to ~0.67 (better than break-even counts as good).
    """
    # Shift so 0% ROI → score = 0.67; -100% → 0; +50% → 1.0
    shifted = (roi_decimal + 1.0) / (1.0 + _MAX_ROI)
    return _clamp(shifted)


def _coverage_score(coverage_pct: float) -> float:
    """Coverage fraction [0, 1]."""
    return _clamp(coverage_pct / 100.0)


def compute_data_value_score(
    source: str,
    brier_improvement: float,
    baseline_brier: float,
    coverage_pct: float,
    roi_pct: float,
    avg_external_brier: Optional[float] = None,
) -> dict[str, float]:
    """
    Compute all six Data Value Score components and the final composite score.

    Args:
        source: source identifier (e.g. "football_data_co_uk")
        brier_improvement: baseline_brier - source_brier (positive = better)
        baseline_brier: Brier score without this source
        coverage_pct: % of fixtures this source covers (0-100)
        roi_pct: flat-stake ROI percentage (-100 to +∞)
        avg_external_brier: avg Brier score from external_forecasts table (if applicable)

    Returns a dict of {component_name: score, "data_value_score": final}
    """
    accuracy    = _accuracy_score(brier_improvement, baseline_brier)
    calibration = _calibration_score(avg_external_brier)
    roi         = _roi_score(roi_pct / 100.0)
    coverage    = _coverage_score(coverage_pct)
    timeliness  = _TIMELINESS.get(source, 0.60)
    cost        = _COST.get(source, 0.80)

    dvs = (
        _DVS_WEIGHTS["accuracy"]    * accuracy
        + _DVS_WEIGHTS["calibration"] * calibration
        + _DVS_WEIGHTS["roi"]         * roi
        + _DVS_WEIGHTS["coverage"]    * coverage
        + _DVS_WEIGHTS["timeliness"]  * timeliness
        + _DVS_WEIGHTS["cost"]        * cost
    )

    return {
        "accuracy_score":    round(accuracy, 4),
        "calibration_score": round(calibration, 4),
        "roi_score":         round(roi, 4),
        "coverage_score":    round(coverage, 4),
        "timeliness_score":  round(timeliness, 4),
        "cost_score":        round(cost, 4),
        "data_value_score":  round(dvs, 4),
    }


async def update_experiment_scores(
    db: AsyncSession,
    experiment: DataSourceExperiment,
) -> None:
    """
    Compute Data Value Score for a single DataSourceExperiment row and write to DB.

    Pulls coverage and ROI from the external_forecasts table when available.
    Saves all component scores + composite score on the experiment row.
    """
    source = experiment.source

    # ── Coverage: count external_forecast rows for this source vs. total fixtures
    from app.models.fixture import Fixture
    total_fixtures = (await db.scalar(
        select(func.count(Fixture.id))
    )) or 1

    ef_count = (await db.scalar(
        select(func.count(ExternalForecast.id)).where(
            ExternalForecast.source == source
        )
    )) or 0

    coverage_pct = round(100.0 * ef_count / max(total_fixtures, 1), 2)

    # ── Calibration: average Brier from settled external forecasts
    avg_brier_row = await db.execute(
        select(
            func.avg(ExternalForecast.brier_o25).label("brier_o25"),
            func.avg(ExternalForecast.brier_1x2_home).label("brier_home"),
        ).where(
            ExternalForecast.source == source,
            ExternalForecast.settled.is_(True),
        )
    )
    brier_row = avg_brier_row.first()
    avg_ext_brier = None
    if brier_row and (brier_row.brier_o25 or brier_row.brier_home):
        values = [v for v in (brier_row.brier_o25, brier_row.brier_home) if v is not None]
        avg_ext_brier = sum(values) / len(values) if values else None

    # ── ROI simulation: flat-stake on settled external_forecast predictions
    # A "bet" = pick the most confident 1X2 outcome when prob > 0.6
    roi_pct = 0.0
    settled_ef = await db.execute(
        select(
            ExternalForecast.home_win_prob,
            ExternalForecast.draw_prob,
            ExternalForecast.away_win_prob,
            ExternalForecast.over_25_prob,
            ExternalForecast.brier_1x2_home,
            ExternalForecast.brier_1x2_draw,
            ExternalForecast.brier_1x2_away,
            ExternalForecast.brier_o25,
            ExternalForecast.actual_home_goals,
            ExternalForecast.actual_away_goals,
        ).where(
            ExternalForecast.source == source,
            ExternalForecast.settled.is_(True),
        )
    )
    ef_rows = settled_ef.all()
    if ef_rows:
        total_stake = 0.0
        total_profit = 0.0
        for r in ef_rows:
            ag = r.actual_away_goals
            hg = r.actual_home_goals
            if hg is None or ag is None:
                continue
            # Simulate 1X2 bet at best predicted outcome when prob > threshold
            probs = {
                "H": r.home_win_prob or 0,
                "D": r.draw_prob or 0,
                "A": r.away_win_prob or 0,
            }
            best_outcome = max(probs, key=lambda k: probs[k])
            best_prob = probs[best_outcome]
            if best_prob < 0.60:
                continue
            # Use implied fair odds (no edge model for external sources)
            fair_odds = round(1.0 / best_prob, 2) if best_prob > 0 else 0
            if fair_odds < 1.10:
                continue
            total_stake += 1.0
            actual_result = "H" if hg > ag else ("D" if hg == ag else "A")
            if actual_result == best_outcome:
                total_profit += fair_odds - 1.0
            else:
                total_profit -= 1.0
        if total_stake > 0:
            roi_pct = round(100.0 * total_profit / total_stake, 2)

    # ── Compute composite score
    scores = compute_data_value_score(
        source=source,
        brier_improvement=experiment.brier_improvement,
        baseline_brier=experiment.baseline_brier,
        coverage_pct=coverage_pct,
        roi_pct=roi_pct,
        avg_external_brier=avg_ext_brier,
    )

    experiment.accuracy_score    = scores["accuracy_score"]
    experiment.calibration_score = scores["calibration_score"]
    experiment.roi_score         = scores["roi_score"]
    experiment.coverage_score    = scores["coverage_score"]
    experiment.timeliness_score  = scores["timeliness_score"]
    experiment.cost_score        = scores["cost_score"]
    experiment.data_value_score  = scores["data_value_score"]
    experiment.updated_at        = datetime.now(timezone.utc)


async def compute_all_data_value_scores(db: AsyncSession) -> list[dict]:
    """
    Recompute Data Value Scores for all DataSourceExperiment rows.

    Called by the admin endpoint and optionally after settlement.
    Returns a list of {source, market, data_value_score, components}.
    """
    experiments = (await db.execute(select(DataSourceExperiment))).scalars().all()
    if not experiments:
        logger.info("data_source_service: no experiments to score")
        return []

    results = []
    for exp in experiments:
        try:
            await update_experiment_scores(db, exp)
            results.append({
                "source": exp.source,
                "market": exp.market,
                "data_value_score": exp.data_value_score,
                "accuracy_score":    exp.accuracy_score,
                "calibration_score": exp.calibration_score,
                "roi_score":         exp.roi_score,
                "coverage_score":    exp.coverage_score,
                "timeliness_score":  exp.timeliness_score,
                "cost_score":        exp.cost_score,
            })
        except Exception as e:
            logger.warning(
                "data_source_service: score failed for %s/%s — %s",
                exp.source, exp.market, e,
            )

    try:
        await db.commit()
        logger.info(
            "data_source_service: updated DVS for %d experiments", len(results)
        )
    except Exception as e:
        await db.rollback()
        logger.error("data_source_service: commit failed — %s", e)

    return results


async def get_source_rankings(db: AsyncSession) -> list[dict]:
    """
    Return sources ranked by average Data Value Score across all their experiments.
    Sources with no experiments fall back to static timeliness+cost defaults.
    """
    rows = (await db.execute(select(DataSourceExperiment))).scalars().all()

    by_source: dict[str, list[float]] = {}
    for r in rows:
        if r.data_value_score is not None:
            by_source.setdefault(r.source, []).append(r.data_value_score)

    # Include known sources with no experiments yet
    all_sources = set(_TIMELINESS.keys()) | set(by_source.keys())

    rankings = []
    for source in all_sources:
        if source in by_source:
            avg_dvs = sum(by_source[source]) / len(by_source[source])
            n_experiments = len(by_source[source])
        else:
            # No Brier data yet — estimate from static scores only
            static_dvs = compute_data_value_score(
                source=source,
                brier_improvement=0.0,
                baseline_brier=_NAIVE_BRIER,
                coverage_pct=0.0,
                roi_pct=0.0,
            )
            avg_dvs = static_dvs["data_value_score"]
            n_experiments = 0

        rankings.append({
            "source":            source,
            "data_value_score":  round(avg_dvs, 4),
            "n_experiments":     n_experiments,
            "timeliness":        _TIMELINESS.get(source, 0.60),
            "cost":              _COST.get(source, 0.80),
        })

    rankings.sort(key=lambda x: x["data_value_score"], reverse=True)
    return rankings
