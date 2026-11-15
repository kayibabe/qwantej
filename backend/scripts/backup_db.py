"""Take a pg_dump (custom format) of a Postgres database and validate it.

Usage:
    python scripts/backup_db.py [--url URL] [--output-dir DIR] [--label LABEL]

`--url` defaults to $DATABASE_URL. The dump never touches stdout/logs with
the connection string (only the host/db name are printed, for audit trail).

The dump logic lives in ``app.services.database_backup`` so the nightly
scheduled backup and this manual command produce identical, validated output.
Exit code 0 + a JSON summary on stdout means the dump was written AND validated
(the matching pg_restore --list ran clean against it). Any other outcome is a
failure — the partial file is removed rather than left looking like a backup.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from app.services.database_backup import BackupError, create_dump


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output-dir", default="backups")
    parser.add_argument("--label", default="manual")
    args = parser.parse_args()

    if not args.url:
        print("error: no --url given and DATABASE_URL is not set", file=sys.stderr)
        return 2

    print(f"Backing up to {Path(args.output_dir)}", file=sys.stderr)
    try:
        summary = create_dump(url=args.url, output_dir=args.output_dir, label=args.label)
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
