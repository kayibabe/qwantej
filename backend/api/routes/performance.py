"""GET /performance — KPI reports over settled predictions."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from backend.api.deps import DbDep
from backend.api.routes.dashboard import PRODUCT_DAY_ZONE
from backend.core.security import RequireApiKey
from backend.schemas.performance import (
    AccumulatorPeriodResultOut,
    AccumulatorProductResultOut,
    AccumulatorResultsOut,
    KPIReportOut,
    PerformanceSegmentsOut,
)
from backend.services.accumulator_results import accumulator_results_by_period
from backend.services.performance import (
    awaiting_settlement_count,
    performance_by_segment,
    performance_report,
)
from qwantej.performance.accumulator_results import GRANULARITIES

router = APIRouter(
    prefix="/performance",
    tags=["performance"],
    dependencies=[RequireApiKey],
)

_VALID_SUBJECT_TYPES = {"prediction", "accumulator"}
_VALID_SEGMENTS = {"market", "league", "model_version", "product"}
PerformanceScope = Literal["all", "production", "research"]


def _day_boundary(value: date | None, *, end: bool = False) -> datetime | None:
    if value is None:
        return None
    local = datetime.combine(value, time.min, tzinfo=PRODUCT_DAY_ZONE)
    return local.astimezone(UTC) if not end else (local + timedelta(days=1)).astimezone(UTC)


@router.get("/report", response_model=KPIReportOut)
def get_performance_report(
    db: DbDep,
    subject_type: Annotated[str, Query()] = "prediction",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
    selection: Annotated[str | None, Query(max_length=80)] = None,
    min_probability: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_odds: Annotated[float | None, Query(gt=1)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    scope: Annotated[PerformanceScope, Query()] = "all",
) -> KPIReportOut:
    """Return overall KPIs for effective settlements in the requested scope.

    Optional filters:
    - ``subject_type`` — ``prediction`` (default) or ``accumulator``
    - ``since`` / ``until`` — settlement timestamp window ``[since, until)``
    - ``market`` — restrict to one market family (e.g. ``1X2``, ``BTTS``)
    - ``selection`` — restrict to the archived selection (e.g. ``UNDER_2_5``)
    - ``min_probability`` / ``min_odds`` — inclusive archived execution filters
    - ``date_from`` / ``date_to`` — inclusive match-date window in Africa/Blantyre
    - ``scope`` — ``production``, ``research`` or ``all`` (default)

    KPI dimensions covered: predictive (Brier, BSS, log-loss, ECE, calibration
    slope/intercept), betting (hit rate, average odds, break-even rate), market
    quality (mean CLV), financial (ROI, total stake/profit), risk (max drawdown,
    volatility).
    """
    if subject_type not in _VALID_SUBJECT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"subject_type must be one of {sorted(_VALID_SUBJECT_TYPES)}",
        )
    if market is not None and subject_type != "prediction":
        raise HTTPException(
            status_code=422,
            detail="market filter is only supported for subject_type=prediction",
        )
    if until is not None and since is not None and since >= until:
        raise HTTPException(status_code=422, detail="since must be before until")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    if any(v is not None for v in (selection, min_probability, min_odds, date_from, date_to)) and subject_type != "prediction":
        raise HTTPException(status_code=422, detail="match filters are only supported for subject_type=prediction")

    report = performance_report(
        db,
        subject_type=subject_type,
        since=since,
        until=until,
        market=market,
        selection=selection,
        min_probability=min_probability,
        min_odds=min_odds,
        match_since=_day_boundary(date_from),
        match_until=_day_boundary(date_to, end=True),
        scope=scope,
    )
    return KPIReportOut(
        **report.__dict__,
        n_awaiting=awaiting_settlement_count(
            db, subject_type=subject_type, now=datetime.now(UTC)
        ),
    )


@router.get("/segments", response_model=PerformanceSegmentsOut)
def get_performance_segments(
    db: DbDep,
    by: Annotated[str, Query()] = "market",
    subject_type: Annotated[str, Query()] = "prediction",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
    selection: Annotated[str | None, Query(max_length=80)] = None,
    min_probability: Annotated[float | None, Query(ge=0, le=1)] = None,
    min_odds: Annotated[float | None, Query(gt=1)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    scope: Annotated[PerformanceScope, Query()] = "all",
) -> PerformanceSegmentsOut:
    """Return KPI reports broken down by a segmentation dimension and scope.

    ``by=product`` is available for accumulator evidence and uses the immutable
    stored accumulator product (for example ``daily_safe``), never a label
    derived from current configuration.

    - ``by`` — ``market``, ``league``, or ``model_version`` (default: ``market``)
    - ``subject_type`` — ``prediction`` (default) or ``accumulator``
    - ``since`` — restrict to settlements on or after this ISO-8601 timestamp

    Each segment key maps to a full :class:`KPIReportOut`.
    """
    if by not in _VALID_SEGMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"by must be one of {sorted(_VALID_SEGMENTS)}",
        )
    if subject_type not in _VALID_SUBJECT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"subject_type must be one of {sorted(_VALID_SUBJECT_TYPES)}",
        )
    if until is not None and since is not None and since >= until:
        raise HTTPException(status_code=422, detail="since must be before until")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    if any(v is not None for v in (market, selection, min_probability, min_odds, date_from, date_to)) and subject_type != "prediction":
        raise HTTPException(status_code=422, detail="match filters are only supported for subject_type=prediction")

    segments = performance_by_segment(
        db,
        by=by,
        subject_type=subject_type,
        since=since,
        until=until,
        market=market,
        selection=selection,
        min_probability=min_probability,
        min_odds=min_odds,
        match_since=_day_boundary(date_from),
        match_until=_day_boundary(date_to, end=True),
        scope=scope,
    )
    return PerformanceSegmentsOut(
        by=by,
        segments={k: KPIReportOut(**v.__dict__) for k, v in segments.items()},
    )


@router.get("/accumulator-results", response_model=AccumulatorResultsOut)
def get_accumulator_results(
    db: DbDep,
    granularity: Annotated[str, Query()] = "day",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    product: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 31,
) -> AccumulatorResultsOut:
    """Return which accumulator products won, grouped by year, month or day.

    - ``granularity`` — ``year``, ``month`` or ``day`` (default ``day``);
      periods are the ticket's publication date in the Africa/Blantyre
      product day, the same calendar as ``/dashboard/today`` and
      ``/accumulators?date=``
    - ``since`` / ``until`` — publication window ``[since, until)``
    - ``product`` — restrict to one product (e.g. ``core``, ``daily_safe``)
    - ``limit`` — most recent periods returned (newest first)

    A ticket's result is derived from its legs' effective settlements: any
    lost leg loses it; it is won once every leg is settled and at least one
    won. Daily Picks are flagged (``daily_pick``) and never merged with the
    value products.
    """
    if granularity not in GRANULARITIES:
        raise HTTPException(
            status_code=422,
            detail=f"granularity must be one of {list(GRANULARITIES)}",
        )
    if since is not None and until is not None and since >= until:
        raise HTTPException(status_code=422, detail="since must be before until")

    periods = accumulator_results_by_period(
        db,
        granularity=granularity,  # type: ignore[arg-type]  # validated above
        since=since,
        until=until,
        product=product,
        tz=PRODUCT_DAY_ZONE,
    )
    return AccumulatorResultsOut(
        granularity=granularity,
        total_periods=len(periods),
        periods=[
            AccumulatorPeriodResultOut(
                period=p.period,
                products=[
                    AccumulatorProductResultOut(
                        product=t.product,
                        daily_pick=t.product.lower().startswith("daily_"),
                        won=t.won,
                        lost=t.lost,
                        void=t.void,
                        pending=t.pending,
                        total=t.total,
                        win_rate=t.win_rate,
                        profit_units=t.profit_units,
                    )
                    for t in p.products
                ],
            )
            for p in periods[:limit]
        ],
    )
