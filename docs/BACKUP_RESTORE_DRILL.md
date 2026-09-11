# Disposable backup/restore drill

Backup creation and gzip/header verification do not prove that a backup can be
restored. Run the drill against a local disposable database after creating a
backup:

```powershell
docker compose up -d db
.venv\Scripts\python.exe scripts\backup_db.py
.venv\Scripts\python.exe scripts\restore_drill.py --backup backups\<backup>.sql.gz
```

The drill requires the configured database URL to use `localhost`, `127.0.0.1`,
or `::1`, and the target database name to look disposable (the default is
`qwantej_restore_drill`). It drops and recreates only that exact target, restores
with `psql` and `ON_ERROR_STOP`, checks the Alembic version and fixture table,
then drops the target again. Use `--keep-target` only when inspecting the
disposable result locally.

This is an operational verification, not a production migration. Never point
the source or target at a production host, and never use a production database
name as the target.

## GitHub Actions

The `Disposable backup restore drill` workflow can be started manually with
`workflow_dispatch`. It provisions an ephemeral PostgreSQL 16 service, runs the
same backup and restore commands, verifies cleanup, and records the result in
the workflow summary. Database dumps are not uploaded as workflow artifacts.
