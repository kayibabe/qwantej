from __future__ import annotations

import gzip
import subprocess
from pathlib import Path

import pytest

from scripts.restore_drill import _restore_sql, _validate_target, run_restore_drill


def _conn(*, host: str = "localhost", dbname: str = "qwantej") -> dict[str, str]:
    return {
        "host": host,
        "port": "5433",
        "dbname": dbname,
        "user": "qwantej",
        "password": "password",
    }


def test_validate_target_requires_loopback() -> None:
    with pytest.raises(ValueError, match="loopback"):
        _validate_target(_conn(host="db.example.com"), "qwantej_restore_drill")


def test_validate_target_requires_disposable_name() -> None:
    with pytest.raises(ValueError, match="must be named"):
        _validate_target(_conn(), "unsafe_target")


def test_validate_target_rejects_source_database() -> None:
    with pytest.raises(ValueError, match="differ"):
        _validate_target(_conn(), "qwantej")


def test_restore_drill_requires_existing_backup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_restore_drill(
            backup_path=tmp_path / "missing.sql.gz",
            database_url="postgresql+psycopg://qwantej:password@localhost:5433/qwantej",
        )


def test_restore_sql_decompresses_before_psql(tmp_path: Path, monkeypatch) -> None:
    backup = tmp_path / "backup.sql.gz"
    with gzip.open(backup, "wb") as dump:
        dump.write(b"-- PostgreSQL database dump\nCREATE TABLE demo (id int);\n")
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("scripts.restore_drill.subprocess.run", fake_run)
    _restore_sql(backup, _conn(), "qwantej_restore_drill", "psql")
    assert calls[0][1]["input"].startswith(b"-- PostgreSQL database dump")
