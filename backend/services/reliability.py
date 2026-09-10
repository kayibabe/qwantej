"""Archive a computed reliability matrix without duplicating quant logic."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Competition,
    Fixture,
    Prediction,
    ReliabilitySnapshot,
    ReliabilityState,
    Settlement,
    SettlementOutcome,
)
from qwantej.performance import ReliabilityMatrix, ReliabilityObservation, build_reliability_matrix

_DEFAULT_POLICY_VERSION = "reliability-v1"


@dataclass(frozen=True)
class ReliabilityLookupResult:
    """Reliability scores and identity for one (competition, market_family) cell."""

    snapshot_id: uuid.UUID
    league_reliability: float   # 0-100
    market_reliability: float   # 0-100
    segment_reliability: float  # 0-100
    status: str                 # "qualified" | "watch" | "restricted" | "blacklisted"


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


def current_reliability_for_fixture(
    session: Session,
    competition_id: uuid.UUID,
    market_family: str,
    *,
    as_of: datetime,
    policy_version: str = _DEFAULT_POLICY_VERSION,
) -> ReliabilityLookupResult | None:
    """Return the most recent qualifying reliability snapshot for a fixture.

    A snapshot qualifies when:
    - It matches (competition_id, market_family, policy_version).
    - Its evaluated_as_of does not exceed as_of (no look-ahead).
    - Its created_at does not exceed as_of (no backdated snapshots for past decisions).

    The query sorts by evaluated_as_of DESC then created_at DESC so that the most
    recent valid snapshot wins, and ties across policy batches are deterministic.

    Returns None when no qualifying row exists — the signal pipeline treats this
    as fail-closed (reliability gate emits RELIABILITY_LOW).
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    stmt = (
        select(ReliabilitySnapshot)
        .where(
            ReliabilitySnapshot.competition_id == competition_id,
            ReliabilitySnapshot.market_family == market_family,
            ReliabilitySnapshot.policy_version == policy_version,
            ReliabilitySnapshot.evaluated_as_of <= as_of,
            ReliabilitySnapshot.created_at <= as_of,
        )
        .order_by(
            ReliabilitySnapshot.evaluated_as_of.desc(),
            ReliabilitySnapshot.created_at.desc(),
        )
        .limit(1)
    )
    snap = session.scalars(stmt).first()
    if snap is None:
        return None
    return ReliabilityLookupResult(
        snapshot_id=snap.id,
        league_reliability=float(snap.league_reliability),
        market_reliability=float(snap.market_reliability),
        segment_reliability=float(snap.segment_reliability),
        status=snap.status.value,
    )


def _ensure_aware(dt: datetime) -> datetime:
    """Return dt with UTC tzinfo when it is naive (SQLite returns naive datetimes)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def query_reliability_observations(
    session: Session,
    *,
    as_of: datetime,
) -> tuple[list[ReliabilityObservation], dict[str, uuid.UUID]]:
    """Build ReliabilityObservation objects from all effective WIN/LOSS settlements.

    Only unsuperseded WIN/LOSS settlements with a recorded taken_probability and
    a calibrated_probability on the linked prediction are included.  Filtered to
    settled_at <= as_of for PIT safety.

    Returns (observations, competition_id_map) where competition_id_map maps
    competition.name → competition.id for use in archive_reliability_matrix.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    superseded_ids = (
        select(Settlement.supersedes_id)
        .where(Settlement.supersedes_id.is_not(None))
    )

    stmt = (
        select(Settlement, Prediction, Competition)
        .join(Prediction, Prediction.id == Settlement.subject_id)
        .join(Fixture, Fixture.id == Prediction.fixture_id)
        .join(Competition, Competition.id == Fixture.competition_id)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.outcome.in_([SettlementOutcome.WIN, SettlementOutcome.LOSS]),
            Settlement.taken_odds.is_not(None),
            Settlement.id.not_in(superseded_ids),
            Settlement.settled_at <= as_of,
            Prediction.calibrated_probability.is_not(None),
        )
    )

    observations: list[ReliabilityObservation] = []
    competition_id_map: dict[str, uuid.UUID] = {}
    # Tracks all UUIDs seen per name to detect ambiguous (non-unique) names.
    _name_to_ids: dict[str, set[uuid.UUID]] = {}

    for settlement, prediction, competition in session.execute(stmt):
        competition_class = f"tier-{competition.tier}" if competition.tier else "tier-1"
        competition_id_map[competition.name] = competition.id
        _name_to_ids.setdefault(competition.name, set()).add(competition.id)

        is_win = settlement.outcome == SettlementOutcome.WIN
        taken_odds = float(settlement.taken_odds)
        profit_units = (taken_odds - 1.0) if is_win else -1.0

        decision_as_of = _ensure_aware(prediction.decision_as_of)
        settled_at = _ensure_aware(settlement.settled_at)

        observations.append(
            ReliabilityObservation(
                observation_id=str(settlement.subject_id),
                league=competition.name,
                market_family=prediction.market,
                competition_class=competition_class,
                decision_as_of=decision_as_of,
                outcome_observed_at=settled_at,
                predicted_probability=float(prediction.calibrated_probability),
                outcome=1 if is_win else 0,
                profit_units=profit_units,
                closing_line_value=(
                    float(settlement.clv) if settlement.clv is not None else None
                ),
                model_stability=1.0,
            )
        )

    ambiguous = sorted(name for name, ids in _name_to_ids.items() if len(ids) > 1)
    if ambiguous:
        raise ValueError(
            f"ambiguous competition names (multiple IDs): {', '.join(ambiguous)}; "
            "ensure competition names are unique in the database"
        )

    return observations, competition_id_map


def rebuild_reliability_snapshots(
    session: Session,
    *,
    as_of: datetime,
    code_commit: str,
) -> int:
    """Rebuild reliability snapshots from all settled predictions up to as_of.

    Intended for post-settlement invocation so the next signal pipeline run
    uses up-to-date lrs/mrs scores.  Returns the number of new snapshot rows
    written, or 0 when there are no qualifying observations.

    Session contract: flushes but does not commit.  The caller controls the
    commit boundary (same convention as the settlement worker).
    """
    observations, competition_id_map = query_reliability_observations(
        session, as_of=as_of
    )
    if not observations:
        return 0

    fingerprints = sorted(
        f"{obs.observation_id}:{obs.league}:{obs.market_family}:{obs.competition_class}"
        f":{obs.decision_as_of.isoformat()}:{obs.outcome_observed_at.isoformat()}"
        f":{obs.predicted_probability:.8f}:{obs.outcome}:{obs.profit_units:.6f}"
        f":{obs.closing_line_value}:{obs.model_stability:.4f}"
        for obs in observations
    )
    snapshot_hash = hashlib.sha256("|".join(fingerprints).encode()).hexdigest()
    window_start = min(obs.decision_as_of for obs in observations)

    matrix = build_reliability_matrix(observations, evaluated_as_of=as_of)
    rows = archive_reliability_matrix(
        session,
        matrix,
        competition_ids=competition_id_map,
        window_start=window_start,
        input_snapshot_ref="settlement-worker-rebuild",
        input_snapshot_hash=snapshot_hash,
        code_commit=code_commit,
    )
    return len(rows)
