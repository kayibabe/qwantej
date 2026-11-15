"""Nightly backups: retention never evicts the newest dumps, failures alert.

The forward ledger has no other durable copy, so a silently failing backup is
worse than no backup: it looks safe. These tests pin retention and the failure
record.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import database_backup
from app.services.database_backup import BackupError, prune_backups

NOW = datetime(2026, 11, 15, 3, tzinfo=timezone.utc)


def _dump(directory, when, label="scheduled"):
    name = f"qwantej_{label}_{when.strftime('%Y%m%dT%H%M%SZ')}.dump"
    path = directory / name
    path.write_bytes(b"x")
    return path


def test_prune_never_drops_below_the_minimum_keep(tmp_path):
    # All three are far older than retention; the newest two must survive.
    for days in (10, 20, 30):
        _dump(tmp_path, NOW - timedelta(days=days))

    result = prune_backups(tmp_path, retention_days=1, minimum_keep=2, now=NOW)

    remaining = sorted(path.name for path in tmp_path.glob("*.dump"))
    assert result["kept"] == 2
    assert len(remaining) == 2
    assert (NOW - timedelta(days=10)).strftime("%Y%m%dT%H%M%SZ") in remaining[1]
    assert (NOW - timedelta(days=20)).strftime("%Y%m%dT%H%M%SZ") in remaining[0]


def test_prune_deletes_only_dumps_beyond_retention(tmp_path):
    for days in range(8):
        _dump(tmp_path, NOW - timedelta(days=days))
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")

    result = prune_backups(tmp_path, retention_days=4, minimum_keep=2, now=NOW)

    names = {path.name for path in tmp_path.iterdir()}
    assert "notes.txt" in names
    # Days 0..4 are inside retention (day 4 sits exactly on the boundary).
    for days in range(5):
        stamp = (NOW - timedelta(days=days)).strftime("%Y%m%dT%H%M%SZ")
        assert f"qwantej_scheduled_{stamp}.dump" in names
    for days in range(5, 8):
        stamp = (NOW - timedelta(days=days)).strftime("%Y%m%dT%H%M%SZ")
        assert f"qwantej_scheduled_{stamp}.dump" not in names
    assert len(result["deleted"]) == 3


def test_prune_is_a_no_op_below_minimum_keep(tmp_path):
    _dump(tmp_path, NOW - timedelta(days=400))
    result = prune_backups(tmp_path, retention_days=1, minimum_keep=2, now=NOW)
    assert result == {"deleted": [], "kept": 1}


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_failed_backup_returns_failed_and_records_an_alert(monkeypatch):
    alerts, resolved, audits = [], [], []

    async def record(db, **kwargs):
        alerts.append(kwargs)

    async def resolve(db, key):
        resolved.append(key)

    def boom(**kwargs):
        raise BackupError("pg_dump failed: password authentication failed")

    monkeypatch.setattr(database_backup, "record_automation_alert", record)
    monkeypatch.setattr(database_backup, "resolve_automation_alert_by_dedupe_key", resolve)
    monkeypatch.setattr(database_backup, "create_dump", boom)
    db = _FakeDb()

    result = await database_backup.run_scheduled_backup(db)

    assert result["status"] == "failed"
    assert "password authentication failed" in result["error"]
    assert [alert["dedupe_key"] for alert in alerts] == [
        database_backup.BACKUP_ALERT_KEY
    ]
    assert alerts[0]["severity"] == "error"
    assert resolved == []
    assert [event.event_type for event in db.added] == ["backup_failed"]


@pytest.mark.asyncio
async def test_successful_backup_records_and_clears_both_alerts(monkeypatch):
    alerts, resolved, audits = [], [], []

    async def record(db, **kwargs):
        alerts.append(kwargs)

    async def resolve(db, key):
        resolved.append(key)

    def dump(**kwargs):
        return {"validated": True, "file": "qwantej_scheduled_x.dump"}

    monkeypatch.setattr(database_backup, "record_automation_alert", record)
    monkeypatch.setattr(database_backup, "resolve_automation_alert_by_dedupe_key", resolve)
    monkeypatch.setattr(database_backup, "create_dump", dump)
    monkeypatch.setattr(
        database_backup, "prune_backups", lambda *a, **k: {"deleted": [], "kept": 1}
    )
    monkeypatch.setattr(database_backup, "latest_backup_at", lambda *a: NOW)
    db = _FakeDb()

    result = await database_backup.run_scheduled_backup(db)

    assert result["status"] == "ok"
    assert result["validated"] is True
    assert result["latest_on_disk"] == NOW.isoformat()
    assert alerts == []
    assert set(resolved) == {
        database_backup.BACKUP_ALERT_KEY,
        database_backup.BACKUP_STALE_ALERT_KEY,
    }
    assert [event.event_type for event in db.added] == ["backup_completed"]
