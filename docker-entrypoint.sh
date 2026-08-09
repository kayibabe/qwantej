#!/bin/sh
set -e

# Tables are created by init_db() in the FastAPI lifespan on first boot.
# No Alembic — schema changes go through app/core/migrations.py.
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
