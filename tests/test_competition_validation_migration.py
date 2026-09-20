"""Executable tests for the corrective validated-competition migration."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from backend.models.migrations.versions.c9d1e4f7a2b5_repair_validated_production_competitions import (  # noqa: E501
    downgrade,
    upgrade,
)


def _create_schema(conn) -> None:
    conn.execute(sa.text("CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT NOT NULL)"))
    conn.execute(
        sa.text(
            "CREATE TABLE competitions (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "validated BOOLEAN NOT NULL DEFAULT 0)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE TABLE source_mappings (provider_id TEXT NOT NULL, entity_type TEXT NOT NULL, "
            "external_id TEXT NOT NULL, canonical_id TEXT NOT NULL)"
        )
    )


def _insert_mapping(conn, *, provider_name: str, external_id: str) -> str:
    provider_id = str(uuid.uuid4())
    competition_id = str(uuid.uuid4())
    conn.execute(
        sa.text("INSERT INTO providers (id, name) VALUES (:id, :name)"),
        {"id": provider_id, "name": provider_name},
    )
    conn.execute(
        sa.text("INSERT INTO competitions (id, name, validated) VALUES (:id, :name, 0)"),
        {"id": competition_id, "name": f"League {external_id}"},
    )
    conn.execute(
        sa.text(
            "INSERT INTO source_mappings (provider_id, entity_type, external_id, canonical_id) "
            "VALUES (:provider_id, 'competition', :external_id, :canonical_id)"
        ),
        {
            "provider_id": provider_id,
            "external_id": external_id,
            "canonical_id": competition_id,
        },
    )
    return competition_id


def _run_migration(conn, operation) -> None:
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        operation()


def test_repair_migration_validates_only_the_approved_api_football_scope(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path}/competition-repair.db")
    with engine.begin() as conn:
        _create_schema(conn)
        approved = _insert_mapping(conn, provider_name="API-Football", external_id="39")
        unapproved = _insert_mapping(conn, provider_name="API-Football", external_id="262")
        wrong_provider = _insert_mapping(
            conn, provider_name="api-football-unofficial", external_id="78"
        )

    with engine.begin() as conn:
        _run_migration(conn, upgrade)

    with engine.connect() as conn:
        assert conn.scalar(
            sa.text("SELECT validated FROM competitions WHERE id = :id"), {"id": approved}
        )
        assert not conn.scalar(
            sa.text("SELECT validated FROM competitions WHERE id = :id"), {"id": unapproved}
        )
        assert not conn.scalar(
            sa.text("SELECT validated FROM competitions WHERE id = :id"), {"id": wrong_provider}
        )


def test_repair_migration_downgrade_restores_the_prior_false_scope(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path}/competition-repair-down.db")
    with engine.begin() as conn:
        _create_schema(conn)
        approved = _insert_mapping(conn, provider_name="API-Football", external_id="140")
        _run_migration(conn, upgrade)
        assert conn.scalar(
            sa.text("SELECT validated FROM competitions WHERE id = :id"), {"id": approved}
        )
        _run_migration(conn, downgrade)

    with engine.connect() as conn:
        assert not conn.scalar(
            sa.text("SELECT validated FROM competitions WHERE id = :id"), {"id": approved}
        )
