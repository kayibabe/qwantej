"""Append a reviewed external result when the primary fixture feed is stale."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    AuditActor,
    AuditEvent,
    AuditEventType,
    Fixture,
    FixtureStatus,
    Prediction,
    Settlement,
    StatsSnapshot,
    StatsSubjectType,
)


class VerifiedFixtureResultError(ValueError):
    """An external result cannot safely be reconciled to the fixture."""


def ingest_verified_fixture_result(
    session: Session,
    *,
    fixture_id: uuid.UUID,
    home_goals: int,
    away_goals: int,
    source_url: str,
    observed_at: datetime,
) -> bool:
    """Record a human-reviewed final result without rewriting settled history.

    This is a controlled fallback for fixtures where the configured provider
    continues to report NS after kickoff. It updates the canonical result only
    while the fixture is unresolved, appends the source observation and audit
    event, and leaves settlement to the existing settlement worker path.
    """
    _require_score(home_goals, "home_goals")
    _require_score(away_goals, "away_goals")
    _require_aware(observed_at)
    source = urlsplit(source_url)
    if source.scheme != "https" or not source.hostname or source.username or source.password:
        raise VerifiedFixtureResultError("source_url must be a public HTTPS URL")
    source_host = source.hostname.lower()
    snapshot_source = f"verified-result:{source_host}"
    if len(snapshot_source) > 80:
        raise VerifiedFixtureResultError("source hostname is too long")

    fixture = session.get(Fixture, fixture_id)
    if fixture is None:
        raise VerifiedFixtureResultError("fixture does not exist")
    if fixture.status is FixtureStatus.FINISHED:
        if (fixture.home_goals, fixture.away_goals) == (home_goals, away_goals):
            return False
        raise VerifiedFixtureResultError(
            "a finished fixture result cannot be replaced by this import"
        )

    prediction_ids = select(Prediction.id).where(Prediction.fixture_id == fixture.id)
    prior_settlement = session.scalar(
        select(Settlement.id)
        .where(
            Settlement.subject_type == "prediction",
            Settlement.subject_id.in_(prediction_ids),
        )
        .limit(1)
    )
    if prior_settlement is not None:
        raise VerifiedFixtureResultError(
            "fixture already has settlements; use the governed settlement-correction path"
        )

    observed_at_utc = observed_at.astimezone(UTC)
    kickoff_utc = fixture.kickoff_utc
    if kickoff_utc.tzinfo is None:
        kickoff_utc = kickoff_utc.replace(tzinfo=UTC)
    payload = {
        "endpoint": "verified-fixture-result",
        "record": {
            "fixture": {
                "id": str(fixture.id),
                "date": kickoff_utc.astimezone(UTC).isoformat(),
                "status": {"short": "FT", "long": "Match Finished", "elapsed": 90},
            },
            "goals": {"home": home_goals, "away": away_goals},
        },
        "source": {"host": source_host, "url": source_url},
    }
    existing_snapshot = session.scalar(
        select(StatsSnapshot).where(
            StatsSnapshot.fixture_id == fixture.id,
            StatsSnapshot.source == snapshot_source,
            StatsSnapshot.as_of_timestamp == observed_at_utc,
        )
    )
    if existing_snapshot is not None:
        if existing_snapshot.payload != payload:
            raise VerifiedFixtureResultError(
                "the same result capture timestamp contains conflicting evidence"
            )
        return False

    before = {
        "status": fixture.status.value,
        "home_goals": fixture.home_goals,
        "away_goals": fixture.away_goals,
    }
    fixture.status = FixtureStatus.FINISHED
    fixture.home_goals = home_goals
    fixture.away_goals = away_goals
    session.add(
        StatsSnapshot(
            subject_type=StatsSubjectType.FIXTURE,
            fixture_id=fixture.id,
            as_of_timestamp=observed_at_utc,
            payload=payload,
            source=snapshot_source,
        )
    )
    session.add(
        AuditEvent(
            event_type=AuditEventType.DATA_REVISION,
            actor=AuditActor.SYSTEM,
            actor_ref="verified-fixture-result-import",
            action="ingest_verified_external_fixture_result",
            summary="Recorded a reviewed final result from an external match report",
            entity_type="fixtures",
            entity_id=fixture.id,
            payload={
                "before": before,
                "after": {
                    "status": FixtureStatus.FINISHED.value,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                },
                "source_host": source_host,
                "source_url": source_url,
                "observed_at": observed_at_utc.isoformat(),
            },
            occurred_at=observed_at_utc,
        )
    )
    session.flush()
    return True


def _require_score(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise VerifiedFixtureResultError(f"{name} must be a non-negative integer")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise VerifiedFixtureResultError("observed_at must be timezone-aware")
