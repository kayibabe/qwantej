"""Nightly logical database backups with validation and retention.

The forward paper experiments are append-only, so their only durable record is
the database. The stack has disappeared from the Docker engine before; a named
volume survives a container loss but not a prune, a disk fault, or a bad
migration. This module makes one validated dump per night, prunes old ones, and
records the outcome where the operational monitor can see it.

``pg_dump`` is invoked with the client matching the server major. A dump that
fails validation is deleted rather than left looking like a good backup.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuditEvent
from app.services.automation_alerts import (
    record_automation_alert,
    resolve_automation_alert_by_dedupe_key,
)

BACKUP_ALERT_KEY = "pipeline:database_backup"
BACKUP_STALE_ALERT_KEY = "pipeline:database_backup_stale"
BACKUP_GLOB = "qwantej_*.dump"
_STAMP = re.compile(r"_(\d{8}T\d{6}Z)\.dump$")


class BackupError(RuntimeError):
    """A backup did not produce a validated dump."""


def _to_libpq_url(url: str) -> str:
    """pg_dump/pg_restore don't understand the +asyncpg driver suffix."""
    return re.sub(r"^postgres(?:ql)?\+[a-z0-9_]+://", "postgresql://", url)


def _redact(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "?"
    db = (parts.path or "/?").lstrip("/") or "?"
    return f"{host}/{db}"


def _server_major(dsn: str) -> int | None:
    """Read the target server major so dumps use a matching client toolchain."""
    psql = shutil.which("psql")
    if psql is None:
        return None
    proc = subprocess.run(
        [psql, dsn, "--no-psqlrc", "--tuples-only", "--no-align", "--command",
         "SHOW server_version_num"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip()) // 10000
    except ValueError:
        return None


def _matching_tool(name: str, server_major: int) -> str | None:
    """Prefer the versioned PostgreSQL client matching the target server."""
    versioned = Path(f"/usr/lib/postgresql/{server_major}/bin") / name
    if versioned.is_file():
        return str(versioned)
    executable = shutil.which(name)
    if executable is None:
        return None
    proc = subprocess.run([executable, "--version"], capture_output=True, text=True)
    match = re.search(r"\b(\d+)\.", proc.stdout)
    return executable if proc.returncode == 0 and match and int(match.group(1)) == server_major else None


def create_dump(*, url: str, output_dir: str | Path, label: str) -> dict:
    """Write and validate one custom-format dump. Raises :class:`BackupError`."""
    dsn = _to_libpq_url(url)
    target = _redact(dsn)
    server_major = _server_major(dsn)
    if server_major is None:
        raise BackupError("could not identify the database server version with psql")
    pg_dump = _matching_tool("pg_dump", server_major)
    pg_restore = _matching_tool("pg_restore", server_major)
    if pg_dump is None or pg_restore is None:
        missing = "pg_dump" if pg_dump is None else "pg_restore"
        raise BackupError(
            f"matching PostgreSQL {server_major} client '{missing}' is not installed"
        )

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label)
    dump_path = directory / f"qwantej_{safe_label}_{stamp}.dump"

    started = datetime.now(timezone.utc)
    proc = subprocess.run(
        [pg_dump, "--format=custom", "--no-owner", "--no-privileges",
         "--file", str(dump_path), dsn],
        capture_output=True,
        text=True,
    )
    finished = datetime.now(timezone.utc)
    if proc.returncode != 0:
        dump_path.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {proc.stderr.strip()[:500]}")

    listing = subprocess.run(
        [pg_restore, "--list", str(dump_path)], capture_output=True, text=True
    )
    if listing.returncode != 0:
        dump_path.unlink(missing_ok=True)
        raise BackupError(
            f"dump written but failed validation (pg_restore --list): "
            f"{listing.stderr.strip()[:500]}"
        )

    return {
        "target": target,
        "file": str(dump_path),
        "size_bytes": dump_path.stat().st_size,
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "tables_with_data": sum(
            1 for line in listing.stdout.splitlines() if " TABLE DATA " in line
        ),
        "validated": True,
    }


def _dump_stamp(path: Path) -> datetime:
    match = _STAMP.search(path.name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def prune_backups(
    output_dir: str | Path,
    *,
    retention_days: int,
    minimum_keep: int,
    now: datetime | None = None,
) -> dict:
    """Delete old dumps without ever deleting the newest ``minimum_keep``.

    Retention is time-based rather than count-based so a burst of manual dumps
    cannot evict the nightly history, and a quiet period cannot leave a gap.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    files = sorted(Path(output_dir).glob(BACKUP_GLOB), key=_dump_stamp, reverse=True)
    if len(files) <= minimum_keep:
        return {"deleted": [], "kept": len(files)}
    deleted = []
    for path in files[minimum_keep:]:
        if _dump_stamp(path) < cutoff:
            path.unlink(missing_ok=True)
            deleted.append(path.name)
    return {"deleted": deleted, "kept": len(files) - len(deleted)}


def latest_backup_at(output_dir: str | Path) -> datetime | None:
    """Newest dump on disk, regardless of whether the DB recorded it."""
    files = list(Path(output_dir).glob(BACKUP_GLOB))
    return max((_dump_stamp(path) for path in files), default=None)


async def record_backup_outcome(
    db: AsyncSession, *, summary: dict | None, error: str | None
) -> None:
    """Persist the outcome so the monitor can spot a backup that never ran."""
    if error is None and summary is not None:
        db.add(AuditEvent(
            entity_type="database",
            entity_id="backup",
            event_type="backup_completed",
            actor="scheduler",
            reason="nightly logical backup",
            payload=summary,
        ))
        await resolve_automation_alert_by_dedupe_key(db, BACKUP_ALERT_KEY)
        await resolve_automation_alert_by_dedupe_key(db, BACKUP_STALE_ALERT_KEY)
    else:
        db.add(AuditEvent(
            entity_type="database",
            entity_id="backup",
            event_type="backup_failed",
            actor="scheduler",
            reason=(error or "unknown error")[:2000],
            payload={},
        ))
        await record_automation_alert(
            db,
            dedupe_key=BACKUP_ALERT_KEY,
            task_name="database_backup",
            title="Nightly database backup failed",
            detail=(
                f"The nightly logical backup did not produce a validated dump: "
                f"{error}. The forward ledger is currently unprotected."
            ),
            severity="error",
        )
    await db.flush()


async def run_scheduled_backup(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """Dump, validate, prune, and record. Never leaves a failed dump behind.

    Never raises for an operational failure: the outcome (and any alert) is
    committed with the session, so a caller's rollback cannot erase the record
    of a failure. Callers decide whether to retry from ``status``.
    """
    summary: dict | None = None
    error: str | None = None
    try:
        summary = await asyncio.to_thread(
            create_dump,
            url=settings.database_url,
            output_dir=settings.database_backup_dir,
            label="scheduled",
        )
        pruned = await asyncio.to_thread(
            prune_backups,
            settings.database_backup_dir,
            retention_days=settings.database_backup_retention_days,
            minimum_keep=settings.database_backup_minimum_keep,
            now=now,
        )
        summary["pruned"] = pruned
        latest = await asyncio.to_thread(
            latest_backup_at, settings.database_backup_dir
        )
        summary["latest_on_disk"] = latest.isoformat() if latest else None
    except Exception as exc:  # noqa: BLE001 - the alert needs any failure reason
        error = str(exc) or exc.__class__.__name__
    await record_backup_outcome(db, summary=summary, error=error)
    if error is not None:
        return {"status": "failed", "error": error}
    return {"status": "ok", **summary}


async def backup_age_hours(db: AsyncSession, now: datetime | None = None) -> float | None:
    """Hours since the last successful backup recorded in the database."""
    now = now or datetime.now(timezone.utc)
    latest = await db.scalar(
        select(AuditEvent.created_at)
        .where(
            AuditEvent.entity_type == "database",
            AuditEvent.event_type == "backup_completed",
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return (now - latest.astimezone(timezone.utc)).total_seconds() / 3600
