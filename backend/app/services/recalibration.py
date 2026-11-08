"""Research-only probability recalibration for the Qwantej model.

Settled evidence shows the model is uniformly overconfident (negative
calibration gap in every 5pp band), which makes raw model-minus-market edge
anti-predictive: bigger claimed edge means worse realised ROI. This service
fits an isotonic (pooled adjacent violators) recalibration on settled,
point-in-time-safe samples and reports whether calibrated probabilities and
calibrated edge fix those diagnostics.

Nothing here writes to predictions, gates, tickets, or staking. It is an
analytics view: decision paths may only consume a fitted mapping after a
frozen prospective review, the same boundary the paper trackers keep.
"""

from __future__ import annotations

import math
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SelectionResult
from app.services.performance import (
    _EDGE_BAND_ORDER,
    _edge_band,
    _has_pre_kickoff_information,
    _has_pre_kickoff_quote,
    _probability_band,
    _research_predictions_query,
)
from app.services.settlement import evaluate_selection

MIN_FIT_SAMPLES = 50


def fit_isotonic(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """PAV isotonic regression. Returns sorted (x, fitted_y) block midpoints.

    Blocks pool adjacent violators: each block carries weight, outcome sum,
    and x-range; the returned breakpoints sit at block midpoints so the
    interpolator can linearly bridge between block means.
    """
    if not samples:
        return []
    # Pool repeated x values first: sorting (x, y) tuples would reorder
    # outcomes within a tie and hide the violations PAV must pool.
    grouped: dict[float, list[float]] = {}
    for x, y in samples:
        bucket = grouped.setdefault(x, [0.0, 0.0])
        bucket[0] += 1.0
        bucket[1] += y
    blocks: list[list[float]] = []
    for x in sorted(grouped):
        weight, total = grouped[x]
        blocks.append([weight, total, x, x])
        while (
            len(blocks) >= 2
            and blocks[-2][1] / blocks[-2][0] > blocks[-1][1] / blocks[-1][0]
        ):
            weight_b, sum_b, _, hi_b = blocks.pop()
            weight_a, sum_a, lo_a, _ = blocks.pop()
            blocks.append([weight_a + weight_b, sum_a + sum_b, lo_a, hi_b])
    return [((lo + hi) / 2.0, total / weight) for weight, total, lo, hi in blocks]


def calibrated_probability(breakpoints: list[tuple[float, float]], x: float) -> float:
    """Piecewise-linear calibration mapping; flat outside the fitted range."""
    if not breakpoints:
        return x
    if x <= breakpoints[0][0]:
        return min(1.0, max(0.0, breakpoints[0][1]))
    if x >= breakpoints[-1][0]:
        return min(1.0, max(0.0, breakpoints[-1][1]))
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if x0 <= x <= x1:
            span = x1 - x0
            t = (x - x0) / span if span > 0 else 0.0
            return min(1.0, max(0.0, y0 + t * (y1 - y0)))
    return min(1.0, max(0.0, breakpoints[-1][1]))


def brier_score(samples: list[tuple[float, float]]) -> float | None:
    if not samples:
        return None
    return round(sum((p - y) ** 2 for p, y in samples) / len(samples), 6)


def log_loss(samples: list[tuple[float, float]]) -> float | None:
    if not samples:
        return None
    total = 0.0
    for p, y in samples:
        clipped = min(1.0 - 1e-6, max(1e-6, p))
        total += -(y * math.log(clipped) + (1.0 - y) * math.log(1.0 - clipped))
    return round(total / len(samples), 6)


def expected_calibration_error(samples: list[tuple[float, float]], bin_count: int = 10) -> float | None:
    if not samples:
        return None
    bins: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]
    for p, y in samples:
        index = min(bin_count - 1, int(p * bin_count))
        bins[index].append((p, y))
    n = len(samples)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        hit = sum(y for _, y in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(hit - avg_p)
    return round(ece, 6)


async def recalibration_analysis(
    db: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    model_version: str | None = None,
) -> dict:
    """Fit and evaluate an isotonic recalibration on settled point-in-time samples."""
    result = await db.execute(_research_predictions_query(date_from, date_to, model_version))
    latest: dict[tuple[int, str, str], object] = {}
    for prediction in result.scalars().all():
        if model_version and prediction.model_version != model_version:
            continue
        match_date = prediction.match.kickoff_at.date()
        if date_from and match_date < date_from or date_to and match_date > date_to:
            continue
        key = (prediction.match_id, prediction.market, prediction.selection)
        if key in latest:
            continue
        if not _has_pre_kickoff_information(prediction):
            continue
        if not _has_pre_kickoff_quote(prediction):
            continue
        if prediction.source_decimal_odds is None or prediction.source_decimal_odds <= 1:
            continue
        if prediction.source_implied_probability is None:
            continue
        latest[key] = prediction

    rows = []
    for prediction in latest.values():
        match = prediction.match
        if match.home_goals is None or match.away_goals is None:
            continue
        try:
            outcome = evaluate_selection(prediction.selection, match.home_goals, match.away_goals)
        except ValueError:
            try:
                outcome = evaluate_selection(prediction.market, match.home_goals, match.away_goals)
            except ValueError:
                continue
        if outcome == SelectionResult.VOID:
            continue
        rows.append(
            (
                prediction.model_probability,
                1.0 if outcome == SelectionResult.WON else 0.0,
                prediction.source_implied_probability,
                prediction.source_decimal_odds,
                prediction.edge,
            )
        )

    if not rows:
        return {
            "model_version": model_version or "all",
            "sample_size": 0,
            "fitted": False,
            "limitations": [
                "No settled point-in-time samples in scope; nothing to recalibrate.",
                "Research only: fitted mappings never alter decision paths.",
            ],
        }

    fit_samples = [(p, y) for p, y, *_ in rows]
    breakpoints = fit_isotonic(fit_samples)
    fitted = len(fit_samples) >= MIN_FIT_SAMPLES
    calibrated = [
        (calibrated_probability(breakpoints, p), y, implied, odds, edge)
        for p, y, implied, odds, edge in rows
    ]

    def edge_bucket_table(samples_with_edge, *, use_calibrated: bool) -> list[dict]:
        groups: dict[str, list] = {}
        for cal_p, y, implied, odds, raw_edge in samples_with_edge:
            if use_calibrated:
                edge_value = cal_p - implied
            else:
                edge_value = raw_edge if raw_edge is not None else cal_p - implied
            if edge_value is None:
                continue
            groups.setdefault(_edge_band(edge_value), []).append((edge_value, y, odds))
        table = []
        for band in _EDGE_BAND_ORDER:
            items = groups.get(band)
            if not items:
                continue
            n = len(items)
            wins = sum(y for _, y, _ in items)
            staked = n
            returned = sum(odds for _, y, odds in items if y == 1.0)
            table.append({
                "edge_band": band,
                "sample_size": n,
                "hit_rate": round(wins / n, 4),
                "roi": round((returned - staked) / staked, 4),
            })
        return table

    band_rows = []
    groups: dict[str, list] = {}
    for p, y, *_ in rows:
        groups.setdefault(_probability_band(p), []).append((p, y))
    for band, items in sorted(groups.items()):
        n = len(items)
        hit = sum(y for _, y in items) / n
        avg_raw = sum(p for p, _ in items) / n
        avg_cal = (
            sum(calibrated_probability(breakpoints, p) for p, _ in items) / n
            if fitted
            else None
        )
        band_rows.append({
            "band": band,
            "sample_size": n,
            "hit_rate": round(hit, 4),
            "avg_raw_probability": round(avg_raw, 4),
            "avg_calibrated_probability": round(avg_cal, 4) if avg_cal is not None else None,
            "raw_gap": round(hit - avg_raw, 4),
            "calibrated_gap": round(hit - avg_cal, 4) if avg_cal is not None else None,
        })

    raw_samples = [(p, y) for p, y, *_ in rows]
    cal_samples = [(p, y) for p, y, *_ in calibrated]
    raw_edge_table = edge_bucket_table(
        [(p, y, implied, odds, edge) for p, y, implied, odds, edge in rows],
        use_calibrated=False,
    )
    cal_edge_table = (
        edge_bucket_table(calibrated, use_calibrated=True) if fitted else []
    )

    return {
        "model_version": model_version or "all",
        "sample_size": len(rows),
        "fitted": fitted,
        "min_fit_samples": MIN_FIT_SAMPLES,
        "mapping": [[round(x, 4), round(y, 4)] for x, y in breakpoints] if fitted else [],
        "raw": {
            "brier_score": brier_score(raw_samples),
            "log_loss": log_loss(raw_samples),
            "ece": expected_calibration_error(raw_samples),
        },
        "calibrated": {
            "brier_score": brier_score(cal_samples) if fitted else None,
            "log_loss": log_loss(cal_samples) if fitted else None,
            "ece": expected_calibration_error(cal_samples) if fitted else None,
        },
        "bands": band_rows,
        "raw_edge_roi": raw_edge_table,
        "calibrated_edge_roi": cal_edge_table,
        "limitations": [
            "Retrospective fit on the same population it is evaluated on: before/after metrics are in-sample and optimistic. Judge by frozen prospective evidence only.",
            f"Mapping withheld until at least {MIN_FIT_SAMPLES} settled samples; below that the raw bands are the honest view.",
            "Research only: this analysis cannot alter publication, picks, gates, or staking.",
        ],
    }
