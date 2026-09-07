"""DB-backed feature extraction: load historical results → compute features.

Uses backend.models for persistence and qwantej.features.engineering for
the pure, leakage-free computation. The caller controls the point-in-time
cut via *as_of*: only fixtures with kickoff_utc < as_of and status=finished
are included in the training set.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Fixture, FixtureStatus, OddsQuote, StatsSnapshot
from qwantej.features.engineering import (
    HistoricalResult,
    MatchFeatures,
    compute_match_features,
)


class FeatureExtractionError(ValueError):
    """Raised when features cannot be safely extracted."""


def extract_fixture_features(
    session: Session,
    fixture: Fixture,
    *,
    as_of: datetime,
    n_recent: int = 30,
    k_factor: float = 20.0,
    home_elo_advantage: float = 65.0,
    initial_elo: float = 1500.0,
    league_home_avg_fallback: float = 1.5,
    league_away_avg_fallback: float = 1.2,
) -> tuple[MatchFeatures, list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
    """Extract features for *fixture* from the DB, using only data before *as_of*.

    Returns ``(MatchFeatures, stats_snapshot_ids, odds_quote_ids, historical_fixture_ids)``.
    ``stats_snapshot_ids`` and ``odds_quote_ids`` are the odds/stats source rows used;
    ``historical_fixture_ids`` are the canonical Fixture rows whose results were fed
    to the ELO and Poisson strength computation — include their hash in the feature
    snapshot so the training set can be replayed and verified independently.

    Raises FeatureExtractionError if the feature point-in-time contract is
    violated (e.g. as_of is not before kickoff).
    """
    _require_aware(as_of, "as_of")
    kickoff = _as_utc(fixture.kickoff_utc)
    as_of_utc = as_of.astimezone(UTC)

    if as_of_utc >= kickoff:
        raise FeatureExtractionError(
            f"as_of ({as_of_utc.isoformat()}) must be before kickoff "
            f"({kickoff.isoformat()})"
        )

    # Load all finished fixtures in the same competition before as_of.
    # The competition scope prevents cross-league data leakage (different leagues
    # have different goal distributions and strength pools).
    historical_rows = session.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == fixture.competition_id,
            Fixture.status == FixtureStatus.FINISHED,
            Fixture.kickoff_utc < as_of_utc,
            Fixture.id != fixture.id,
        )
        .order_by(Fixture.kickoff_utc, Fixture.id)
    ).all()

    historical = [
        HistoricalResult(
            home_team_id=str(row.home_team_id),
            away_team_id=str(row.away_team_id),
            home_goals=row.home_goals or 0,
            away_goals=row.away_goals or 0,
            kickoff_utc=_as_utc(row.kickoff_utc),
        )
        for row in historical_rows
        if row.home_goals is not None and row.away_goals is not None
    ]

    features = compute_match_features(
        historical,
        str(fixture.home_team_id),
        str(fixture.away_team_id),
        n_recent=n_recent,
        k_factor=k_factor,
        home_elo_advantage=home_elo_advantage,
        initial_elo=initial_elo,
        league_home_avg_fallback=league_home_avg_fallback,
        league_away_avg_fallback=league_away_avg_fallback,
    )

    # Record source ids for lineage
    stats_ids = _fixture_stats_ids(session, fixture.id, as_of_utc)
    odds_ids = _fixture_odds_ids(session, fixture.id, as_of_utc)
    # Historical fixture IDs used for ELO/Poisson training — only settled rows
    # (home_goals/away_goals not None) actually entered the computation.
    historical_fixture_ids = [
        row.id for row in historical_rows
        if row.home_goals is not None and row.away_goals is not None
    ]

    return features, stats_ids, odds_ids, historical_fixture_ids


def historical_training_hash(fixture_ids: list[uuid.UUID]) -> str:
    """SHA-256 hex digest of the sorted training fixture IDs.

    Include this as ``_training_fixture_ids_hash`` in the feature snapshot so
    the ELO/Poisson training set can be replayed: re-run the same DB query with
    the same as_of and competition scope, filter to settled rows, sort by ID,
    and compare the digest to verify the snapshot is reproducible.
    """
    sorted_ids = sorted(str(fid) for fid in fixture_ids)
    payload = "\n".join(sorted_ids).encode()
    return hashlib.sha256(payload).hexdigest()


def _fixture_stats_ids(
    session: Session, fixture_id: uuid.UUID, as_of_utc: datetime
) -> list[uuid.UUID]:
    rows = session.scalars(
        select(StatsSnapshot)
        .where(
            StatsSnapshot.fixture_id == fixture_id,
            StatsSnapshot.as_of_timestamp <= as_of_utc,
        )
        .order_by(StatsSnapshot.as_of_timestamp.desc())
        .limit(10)
    ).all()
    return [row.id for row in rows]


def _fixture_odds_ids(
    session: Session, fixture_id: uuid.UUID, as_of_utc: datetime
) -> list[uuid.UUID]:
    rows = session.scalars(
        select(OddsQuote)
        .where(
            OddsQuote.fixture_id == fixture_id,
            OddsQuote.captured_at <= as_of_utc,
        )
        .order_by(OddsQuote.captured_at.desc())
        .limit(50)
    ).all()
    return [row.id for row in rows]


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FeatureExtractionError(f"{name} must be timezone-aware")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
