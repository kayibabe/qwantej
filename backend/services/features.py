"""Create immutable, replayable point-in-time feature snapshots."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import FeatureSnapshot, Fixture, OddsQuote, StatsSnapshot
from qwantej.audit import canonical_hash
from qwantej.features import FeatureValue, validate_feature_vector


class FeatureSnapshotError(ValueError):
    """Raised when a feature snapshot would violate the frozen PIT contract."""


def create_feature_snapshot(
    session: Session,
    *,
    fixture_id: uuid.UUID,
    feature_version: str,
    as_of_timestamp: datetime,
    features: Mapping[str, FeatureValue],
    stats_snapshot_ids: Sequence[uuid.UUID] = (),
    odds_quote_ids: Sequence[uuid.UUID] = (),
    imputation_policy_version: str,
    code_commit: str,
) -> FeatureSnapshot:
    """Validate source-time eligibility and persist a content-addressed snapshot.

    Exact retries are idempotent. A correction or changed feature vector creates
    a new immutable row with a different hash; an existing row is never updated.
    """

    _require_aware(as_of_timestamp, "as_of_timestamp")
    for name, value in (
        ("feature_version", feature_version),
        ("imputation_policy_version", imputation_policy_version),
        ("code_commit", code_commit),
    ):
        if not value or not value.strip():
            raise FeatureSnapshotError(f"{name} must not be blank")

    normalized_features = validate_feature_vector(features)
    stats_ids = _unique_ids(stats_snapshot_ids, "stats_snapshot_ids")
    odds_ids = _unique_ids(odds_quote_ids, "odds_quote_ids")
    if not stats_ids and not odds_ids:
        raise FeatureSnapshotError("at least one source snapshot or odds quote is required")

    fixture = session.get(Fixture, fixture_id)
    if fixture is None:
        raise FeatureSnapshotError("fixture_id does not exist")
    as_of_utc = _as_utc(as_of_timestamp)
    if as_of_utc >= _as_utc(fixture.kickoff_utc):
        raise FeatureSnapshotError("as_of_timestamp must be before fixture kickoff")

    stats_rows = _load_rows(session, StatsSnapshot, stats_ids, "stats snapshot")
    odds_rows = _load_rows(session, OddsQuote, odds_ids, "odds quote")
    participant_ids = {fixture.home_team_id, fixture.away_team_id}

    for row in stats_rows:
        belongs_to_fixture = row.fixture_id == fixture_id
        belongs_to_team = row.team_id in participant_ids
        if not belongs_to_fixture and not belongs_to_team:
            raise FeatureSnapshotError(
                f"stats snapshot {row.id} does not belong to the fixture or its teams"
            )
        if _as_utc(row.as_of_timestamp) > as_of_utc:
            raise FeatureSnapshotError(f"stats snapshot {row.id} is after as_of_timestamp")
    for row in odds_rows:
        if row.fixture_id != fixture_id:
            raise FeatureSnapshotError(f"odds quote {row.id} belongs to another fixture")
        if _as_utc(row.captured_at) > as_of_utc:
            raise FeatureSnapshotError(f"odds quote {row.id} is after as_of_timestamp")

    source_bundle = _source_bundle(stats_rows, odds_rows)
    source_data_hash = canonical_hash(source_bundle)
    feature_hash = canonical_hash(normalized_features)
    snapshot_payload = {
        "fixture_id": str(fixture_id),
        "feature_version": feature_version,
        "as_of_timestamp": as_of_utc,
        "features": normalized_features,
        "stats_snapshot_ids": [str(row.id) for row in stats_rows],
        "odds_quote_ids": [str(row.id) for row in odds_rows],
        "imputation_policy_version": imputation_policy_version,
        "source_data_hash": source_data_hash,
        "feature_hash": feature_hash,
        "code_commit": code_commit,
    }
    snapshot_hash = canonical_hash(snapshot_payload)

    existing = session.scalar(
        select(FeatureSnapshot).where(FeatureSnapshot.snapshot_hash == snapshot_hash)
    )
    if existing is not None:
        return existing

    snapshot = FeatureSnapshot(
        fixture_id=fixture_id,
        feature_version=feature_version,
        as_of_timestamp=as_of_utc,
        features=normalized_features,
        stats_snapshot_ids=snapshot_payload["stats_snapshot_ids"],
        odds_quote_ids=snapshot_payload["odds_quote_ids"],
        imputation_policy_version=imputation_policy_version,
        source_data_hash=source_data_hash,
        feature_hash=feature_hash,
        snapshot_hash=snapshot_hash,
        code_commit=code_commit,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def feature_snapshot_payload(snapshot: FeatureSnapshot) -> dict[str, Any]:
    """Return the canonical payload hashed into ``snapshot.snapshot_hash``."""

    return {
        "fixture_id": str(snapshot.fixture_id),
        "feature_version": snapshot.feature_version,
        "as_of_timestamp": _as_utc(snapshot.as_of_timestamp),
        "features": snapshot.features,
        "stats_snapshot_ids": snapshot.stats_snapshot_ids,
        "odds_quote_ids": snapshot.odds_quote_ids,
        "imputation_policy_version": snapshot.imputation_policy_version,
        "source_data_hash": snapshot.source_data_hash,
        "feature_hash": snapshot.feature_hash,
        "code_commit": snapshot.code_commit,
    }


def verify_feature_snapshot(session: Session, snapshot: FeatureSnapshot) -> bool:
    """Verify the stored vector, source observations, and complete snapshot hash."""

    try:
        stats_ids = tuple(uuid.UUID(value) for value in snapshot.stats_snapshot_ids)
        odds_ids = tuple(uuid.UUID(value) for value in snapshot.odds_quote_ids)
        stats_rows = _load_rows(session, StatsSnapshot, stats_ids, "stats snapshot")
        odds_rows = _load_rows(session, OddsQuote, odds_ids, "odds quote")
    except (FeatureSnapshotError, TypeError, ValueError):
        return False
    return (
        canonical_hash(snapshot.features) == snapshot.feature_hash
        and canonical_hash(_source_bundle(stats_rows, odds_rows))
        == snapshot.source_data_hash
        and canonical_hash(feature_snapshot_payload(snapshot)) == snapshot.snapshot_hash
    )


def _unique_ids(values: Sequence[uuid.UUID], name: str) -> tuple[uuid.UUID, ...]:
    ids = tuple(values)
    if len(ids) != len(set(ids)):
        raise FeatureSnapshotError(f"{name} contains duplicates")
    return tuple(sorted(ids, key=str))


def _load_rows(session: Session, model: type[Any], ids: Sequence[uuid.UUID], label: str):
    if not ids:
        return ()
    rows = tuple(session.scalars(select(model).where(model.id.in_(ids))).all())
    found = {row.id for row in rows}
    missing = sorted(str(value) for value in set(ids) - found)
    if missing:
        raise FeatureSnapshotError(f"{label} ids do not exist: {', '.join(missing)}")
    return tuple(sorted(rows, key=lambda row: str(row.id)))


def _source_bundle(
    stats_rows: Sequence[StatsSnapshot], odds_rows: Sequence[OddsQuote]
) -> dict[str, list[dict[str, Any]]]:
    return {
        "stats": [
            {
                "id": str(row.id),
                "subject_type": row.subject_type.value,
                "team_id": str(row.team_id) if row.team_id else None,
                "fixture_id": str(row.fixture_id) if row.fixture_id else None,
                "as_of_timestamp": _as_utc(row.as_of_timestamp),
                "payload": row.payload,
                "source": row.source,
            }
            for row in stats_rows
        ],
        "odds": [
            {
                "id": str(row.id),
                "fixture_id": str(row.fixture_id),
                "bookmaker": row.bookmaker,
                "market": row.market,
                "selection": row.selection,
                "line": row.line,
                "decimal_odds": row.decimal_odds,
                "captured_at": _as_utc(row.captured_at),
                "source": row.source,
            }
            for row in odds_rows
        ],
    }


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FeatureSnapshotError(f"{name} must be timezone-aware")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
