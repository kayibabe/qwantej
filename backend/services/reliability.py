"""Archive a computed reliability matrix without duplicating quant logic."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import ReliabilitySnapshot, ReliabilityState
from qwantej.performance import ReliabilityMatrix


def archive_reliability_matrix(
    session: Session,
    matrix: ReliabilityMatrix,
    *,
    competition_ids: Mapping[str, uuid.UUID],
    window_start: datetime,
    input_snapshot_ref: str,
    input_snapshot_hash: str,
    code_commit: str,
) -> tuple[ReliabilitySnapshot, ...]:
    """Persist one immutable row per observed league-market cell."""

    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise ValueError("window_start must be timezone-aware")
    if window_start > matrix.evaluated_as_of:
        raise ValueError("window_start cannot follow evaluated_as_of")
    for name, value in (
        ("input_snapshot_ref", input_snapshot_ref),
        ("input_snapshot_hash", input_snapshot_hash),
        ("code_commit", code_commit),
    ):
        if not value.strip():
            raise ValueError(f"{name} must not be blank")
    missing = sorted({cell.league for cell in matrix.cells} - competition_ids.keys())
    if missing:
        raise ValueError(f"competition ids missing for: {', '.join(missing)}")

    rows: list[ReliabilitySnapshot] = []
    for cell in matrix.cells:
        estimate = cell.segment_reliability
        row = ReliabilitySnapshot(
            competition_id=competition_ids[cell.league],
            competition_class=cell.competition_class,
            market_family=cell.market_family,
            evaluated_as_of=matrix.evaluated_as_of,
            window_start=window_start,
            window_end=matrix.evaluated_as_of,
            policy_version=matrix.policy_version,
            observation_count=estimate.observation_count,
            effective_sample_size=estimate.effective_sample_size,
            shrinkage_weight=estimate.shrinkage_weight,
            league_reliability=cell.league_reliability.posterior_mean * 100,
            market_reliability=cell.market_reliability.posterior_mean * 100,
            segment_reliability=estimate.posterior_mean * 100,
            posterior_standard_deviation=estimate.posterior_standard_deviation,
            conservative_lower_bound=estimate.conservative_lower_bound,
            status=ReliabilityState(estimate.status.value),
            grade=estimate.grade,
            components=asdict(estimate.components),
            diagnostics={
                "raw_score": estimate.raw_score,
                "global_posterior": matrix.global_reliability.posterior_mean,
                "league_effective_sample_size": (
                    cell.league_reliability.effective_sample_size
                ),
                "market_effective_sample_size": (
                    cell.market_reliability.effective_sample_size
                ),
            },
            future_rows_excluded=matrix.future_rows_excluded,
            input_snapshot_ref=input_snapshot_ref,
            input_snapshot_hash=input_snapshot_hash,
            code_commit=code_commit,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return tuple(rows)
