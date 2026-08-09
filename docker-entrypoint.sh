#!/bin/sh
set -e

# Run any pending Alembic schema migrations before starting the server.
# On a brand-new database this is a no-op (init_db creates tables on first boot).
# On an existing database this applies any new migrations since the last deploy.
echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
