"""GET /performance — KPI reports over settled predictions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.api.deps import DbDep
from backend.core.security import RequireApiKey
from backend.schemas.performance import KPIReportOut, PerformanceSegmentsOut
from backend.services.performance import performance_by_segment, performance_report

router = APIRouter(
    prefix="/performance",
    tags=["performance"],
    dependencies=[RequireApiKey],
)

_VALID_SUBJECT_TYPES = {"prediction", "accumulator"}
_VALID_SEGMENTS = {"market", "league", "model_version"}


@router.get("/report", response_model=KPIReportOut)
def get_performance_report(
    db: DbDep,
    subject_type: Annotated[str, Query()] = "prediction",
    since: Annotated[datetime | None, Query()] = None,
    market: Annotated[str | None, Query(max_length=40)] = None,
) -> KPIReportOut:
    """Return overall KPIs for all effective (non-superseded) settlements.

    Optional filters:
    - ``subject_type`` — ``prediction`` (default) or ``accumulator``
    - ``since`` — only include settlements on or after this ISO-8601 timestamp
    - ``market`` — restrict to one market family (e.g. ``1X2``, ``BTTS``)

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

    report = performance_report(
        db,
        subject_type=subject_type,
        since=since,
        market=market,
    )
    return KPIReportOut(**report.__dict__)


@router.get("/segments", response_model=PerformanceSegmentsOut)
def get_performance_segments(
    db: DbDep,
    by: Annotated[str, Query()] = "market",
    subject_type: Annotated[str, Query()] = "prediction",
    since: Annotated[datetime | None, Query()] = None,
) -> PerformanceSegmentsOut:
    """Return KPI reports broken down by a segmentation dimension.

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

    segments = performance_by_segment(
        db,
        by=by,
        subject_type=subject_type,
        since=since,
    )
    return PerformanceSegmentsOut(
        by=by,
        segments={k: KPIReportOut(**v.__dict__) for k, v in segments.items()},
    )
