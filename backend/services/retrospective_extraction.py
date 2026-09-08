"""Retrospective feature extraction using canonical fixture mutable state.

NOT point-in-time certified.  Uses ``Fixture.home_goals``, ``Fixture.away_goals``,
and ``Fixture.kickoff_utc`` from the canonical mutable ORM rows rather than
requiring an immutable provider snapshot whose ``as_of_timestamp`` precedes the
simulated decision cutoff.

Suitable ONLY for research calibration runs.  Never use for production backtest,
audit records, or published performance metrics.  The canonical mutable columns
can be corrected or updated at any time; results derived from them cannot serve
as evidence of historical model behaviour.

Isolation rules enforced by this extractor:
  - Same competition only (cross-league strength pools differ).
  - ``kickoff_utc`` strictly before the target fixture's kickoff.
  - The target fixture itself excluded.
  - ``home_goals`` and ``away_goals`` both non-null (finished result).
  - Ordered ascending by kickoff_utc then fixture.id (deterministic replay).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Fixture
from qwantej.features.engineering import (
    HistoricalResult,
    MatchFeatures,
    compute_match_features,
)


class RetrospectiveExtractionError(ValueError):
    """Raised when the retrospective extractor cannot produce valid features."""


@dataclass(frozen=True)
class RetrospectiveResult:
    """One historical result sourced from canonical fixture mutable state.

    Not snapshot-certified: the goals values reflect the current DB row,
    not an immutable provider observation captured at a specific point in time.
    """

    fixture_id: object
    home_team_id: object
    away_team_id: object
    kickoff_utc: datetime
    home_goals: int
    away_goals: int


def extract_retrospective_features(
    session: Session,
    fixture: Fixture,
    *,
    n_recent: int = 30,
    k_factor: float = 20.0,
    home_elo_advantage: float = 65.0,
    initial_elo: float = 1500.0,
    league_home_avg_fallback: float = 1.5,
    league_away_avg_fallback: float = 1.2,
) -> tuple[MatchFeatures, list[RetrospectiveResult]]:
    """Return leakage-free features for *fixture* using canonical fixture state.

    Historical results are all finished fixtures in the same competition with
    ``kickoff_utc`` strictly before *fixture.kickoff_utc*.  No snapshot
    timestamp check is performed.

    Returns ``(MatchFeatures, historical_results)`` where ``historical_results``
    is the ordered list of results fed to the feature computation — pass it to
    ``retrospective_fixture_hash()`` to build a provenance fingerprint.

    Raises RetrospectiveExtractionError if home/away team ids are identical or
    if ``fixture.kickoff_utc`` is not timezone-aware.
    """
    kickoff = _as_utc(fixture.kickoff_utc)

    prior_rows = session.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == fixture.competition_id,
            Fixture.kickoff_utc < kickoff,
            Fixture.id != fixture.id,
            Fixture.home_goals.is_not(None),
            Fixture.away_goals.is_not(None),
        )
        .order_by(Fixture.kickoff_utc, Fixture.id)
    ).all()

    settled: list[RetrospectiveResult] = []
    for row in prior_rows:
        if row.home_goals is None or row.away_goals is None:
            continue
        settled.append(
            RetrospectiveResult(
                fixture_id=row.id,
                home_team_id=row.home_team_id,
                away_team_id=row.away_team_id,
                kickoff_utc=_as_utc(row.kickoff_utc),
                home_goals=row.home_goals,
                away_goals=row.away_goals,
            )
        )

    historical: list[HistoricalResult] = [
        HistoricalResult(
            home_team_id=str(row.home_team_id),
            away_team_id=str(row.away_team_id),
            home_goals=row.home_goals,
            away_goals=row.away_goals,
            kickoff_utc=row.kickoff_utc,
        )
        for row in settled
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

    return features, settled


def retrospective_fixture_hash(results: list[RetrospectiveResult]) -> str:
    """Deterministic SHA-256 content hash of retrospective fixture inputs.

    Encodes fixture id, goals, and kickoff for each training observation so
    any change to the canonical mutable rows produces a different fingerprint.
    Used as the ``data_snapshot_ref`` suffix in research experiment records.
    """
    entries = sorted(
        f"{r.fixture_id}:{r.home_goals}:{r.away_goals}:{_as_utc(r.kickoff_utc).isoformat()}"
        for r in results
    )
    payload = "\n".join(entries).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
