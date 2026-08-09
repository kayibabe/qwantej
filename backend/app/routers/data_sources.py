from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user_optional
from app.models.data_source_experiment import DataSourceExperiment
from app.models.user import User

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


class ExperimentOut(BaseModel):
    id: int
    source: str
    market: str
    league: Optional[str]
    experiment_start: str
    experiment_end: str
    baseline_brier: float
    baseline_n: int
    source_brier: float
    source_n: int
    brier_improvement: float
    p_value: Optional[float]
    accepted: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


class SourceSummary(BaseModel):
    source: str
    experiment_count: int
    accepted_count: int
    latest_brier_improvement: Optional[float]
    experiments: list[ExperimentOut]


@router.get("", response_model=list[SourceSummary])
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    _user: Optional[User] = Depends(get_current_user_optional),
):
    """Return DataSourceExperiment results grouped by source, newest first."""
    result = await db.execute(
        select(DataSourceExperiment).order_by(
            DataSourceExperiment.source,
            DataSourceExperiment.created_at.desc(),
        )
    )
    all_exps = result.scalars().all()

    # Group by source
    groups: dict[str, list[DataSourceExperiment]] = {}
    for exp in all_exps:
        groups.setdefault(exp.source, []).append(exp)

    summaries: list[SourceSummary] = []
    for source, exps in groups.items():
        accepted = [e for e in exps if e.accepted]
        latest_improvement = exps[0].brier_improvement if exps else None
        summaries.append(SourceSummary(
            source=source,
            experiment_count=len(exps),
            accepted_count=len(accepted),
            latest_brier_improvement=latest_improvement,
            experiments=[
                ExperimentOut(
                    id=e.id,
                    source=e.source,
                    market=e.market,
                    league=e.league,
                    experiment_start=str(e.experiment_start),
                    experiment_end=str(e.experiment_end),
                    baseline_brier=e.baseline_brier,
                    baseline_n=e.baseline_n,
                    source_brier=e.source_brier,
                    source_n=e.source_n,
                    brier_improvement=e.brier_improvement,
                    p_value=e.p_value,
                    accepted=e.accepted,
                    notes=e.notes,
                )
                for e in exps
            ],
        ))

    # Sort: sources with accepted experiments first, then by name
    summaries.sort(key=lambda s: (-s.accepted_count, s.source))
    return summaries
