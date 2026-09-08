"""DB-backed feature extraction: load historical results → compute features.

Uses backend.models for persistence and qwantej.features.engineering for
the pure, leakage-free computation. The caller controls the point-in-time
cut via *as_of*: only fixtures with kickoff_utc < as_of and status=finished
are included in the training set.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Fixture, OddsQuote, StatsSnapshot
from qwantej.features.engineering import (
    HistoricalResult,
    MatchFeatures,
    compute_match_features,
)

FIXTURE_SNAPSHOT_SOURCE = "api-football:fixtures"


@dataclass(frozen=True)
class HistoricalFixtureResult:
    """A fixture result proven by an immutable provider snapshot."""

    fixture_id: uuid.UUID
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    kickoff_utc: datetime
    home_goals: int
    away_goals: int
    observed_at: datetime


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
) -> tuple[MatchFeatures, list[uuid.UUID], list[uuid.UUID], list[HistoricalFixtureResult]]:
    """Extract features for *fixture* from the DB, using only data before *as_of*.

    Returns ``(MatchFeatures, stats_snapshot_ids, odds_quote_ids, historical_rows_settled)``.
    ``stats_snapshot_ids`` and ``odds_quote_ids`` are the odds/stats source rows used;
    ``historical_rows_settled`` are immutable provider-backed result records
    whose results were fed to the ELO and Poisson computation — pass them to
    ``historical_training_hash()`` to embed a content-addressed digest in the
    feature snapshot.

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

    # Load fixtures in the same competition before as_of.  The competition
    # scope prevents cross-league data leakage (different leagues have
    # different goal distributions and strength pools).  Do not use the
    # mutable Fixture.status/goals columns here: only immutable provider
    # snapshots captured by as_of may supply a historical result.
    historical_fixtures = session.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == fixture.competition_id,
            Fixture.kickoff_utc < as_of_utc,
            Fixture.id != fixture.id,
        )
        .order_by(Fixture.kickoff_utc, Fixture.id)
    ).all()

    historical_rows_settled = [
        result
        for row in historical_fixtures
        if (result := fixture_result_as_of(session, row, as_of=as_of_utc)) is not None
    ]
    historical = [
        HistoricalResult(
            home_team_id=str(row.home_team_id),
            away_team_id=str(row.away_team_id),
            home_goals=row.home_goals,
            away_goals=row.away_goals,
            kickoff_utc=row.kickoff_utc,
        )
        for row in historical_rows_settled
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
    return features, stats_ids, odds_ids, historical_rows_settled


def historical_training_hash(fixture_rows: Sequence[object]) -> str:
    """SHA-256 hex digest of training results, including observation time.

    For point-in-time results each entry includes the immutable snapshot
    capture time.  The legacy ``Fixture`` shape remains supported for existing
    feature snapshots that predate snapshot-backed result lineage.
    """
    entries = sorted(
        _training_hash_entry(row)
        for row in fixture_rows
    )
    payload = "\n".join(entries).encode()
    return hashlib.sha256(payload).hexdigest()


def fixture_result_as_of(
    session: Session, fixture: Fixture, *, as_of: datetime
) -> HistoricalFixtureResult | None:
    """Return the latest certified result known by *as_of*, if any."""

    _require_aware(as_of, "as_of")
    as_of_utc = as_of.astimezone(UTC)
    kickoff = _as_utc(fixture.kickoff_utc)
    rows = session.scalars(
        select(StatsSnapshot)
        .where(
            StatsSnapshot.fixture_id == fixture.id,
            StatsSnapshot.source == FIXTURE_SNAPSHOT_SOURCE,
            StatsSnapshot.as_of_timestamp <= as_of_utc,
        )
        .order_by(StatsSnapshot.as_of_timestamp.desc(), StatsSnapshot.id.desc())
    ).all()
    for snapshot in rows:
        result = _snapshot_result(snapshot, fixture)
        if result is not None and result.observed_at > kickoff:
            return result
    return None


def fixture_result_observed_after_kickoff(
    session: Session, fixture: Fixture
) -> HistoricalFixtureResult | None:
    """Return the first certified final result observed after kickoff."""

    kickoff = _as_utc(fixture.kickoff_utc)
    rows = session.scalars(
        select(StatsSnapshot)
        .where(
            StatsSnapshot.fixture_id == fixture.id,
            StatsSnapshot.source == FIXTURE_SNAPSHOT_SOURCE,
            StatsSnapshot.as_of_timestamp > kickoff,
        )
        .order_by(StatsSnapshot.as_of_timestamp, StatsSnapshot.id)
    ).all()
    for snapshot in rows:
        result = _snapshot_result(snapshot, fixture)
        if result is not None:
            return result
    return None


def _snapshot_result(snapshot: StatsSnapshot, fixture: Fixture) -> HistoricalFixtureResult | None:
    from qwantej.fixtures import parse_fixture

    payload = snapshot.payload
    record = payload.get("record") if isinstance(payload, dict) else None
    if not isinstance(record, dict):
        return None
    try:
        parsed = parse_fixture(record)
    except (TypeError, ValueError):
        return None
    if parsed.status != "finished" or parsed.home_goals is None or parsed.away_goals is None:
        return None
    return HistoricalFixtureResult(
        fixture_id=fixture.id,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
        kickoff_utc=_as_utc(fixture.kickoff_utc),
        home_goals=parsed.home_goals,
        away_goals=parsed.away_goals,
        observed_at=_as_utc(snapshot.as_of_timestamp),
    )


def _training_hash_entry(row: object) -> str:
    row_id = getattr(row, "fixture_id", getattr(row, "id", None))
    home_goals = getattr(row, "home_goals", None)
    away_goals = getattr(row, "away_goals", None)
    observed_at = getattr(row, "observed_at", None)
    if observed_at is None:
        return f"{row_id}:{home_goals or 0}:{away_goals or 0}"
    return (
        f"{row_id}:{home_goals}:{away_goals}:"
        f"{_as_utc(observed_at).isoformat()}"
    )


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
