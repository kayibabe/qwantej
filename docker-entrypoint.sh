#!/bin/sh
set -e

# If a gzipped staged upload exists, decompress it first. The slim base image has
# no gunzip, so use Python (always present) to inflate it to /data/Qwantej.db.new.
if [ -f /data/Qwantej.db.new.gz ]; then
    echo "Decompressing staged DB upload (/data/Qwantej.db.new.gz)..."
    python -c "import gzip, shutil; src=open('/data/Qwantej.db.new.gz','rb'); dst=open('/data/Qwantej.db.new','wb'); shutil.copyfileobj(gzip.GzipFile(fileobj=src), dst); dst.close(); src.close()"
    rm -f /data/Qwantej.db.new.gz
    echo "Decompress complete."
fi

# If a staged DB upload exists, install it before starting the app.
# Upload process: sftp put → /data/Qwantej.db.new(.gz) → restart → swap here.
if [ -f /data/Qwantej.db.new ]; then
    echo "Installing staged DB upload (/data/Qwantej.db.new)..."
    rm -f /data/Qwantej.db
    mv /data/Qwantej.db.new /data/Qwantej.db
    echo "DB swap complete."
fi

# If the database exists but is malformed (e.g. interrupted SFTP upload), remove it
# so SQLAlchemy recreates it cleanly on startup.
if [ -f /data/Qwantej.db ]; then
    python -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('/data/Qwantej.db')
    result = conn.execute('PRAGMA integrity_check').fetchone()
    conn.close()
    if result[0] != 'ok':
        sys.exit(1)
except Exception:
    sys.exit(1)
" || {
        echo "WARNING: /data/Qwantej.db is malformed — removing so the app can start fresh"
        rm /data/Qwantej.db
    }
fi

exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
