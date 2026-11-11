"""Clear CLV values that cannot be a genuine closing line.

The historical backlog was written before the strict ordering guard existed:
65.6% of rows have `closing == source` with a closing timestamp at or before
the entry timestamp. Those are not zero-CLV observations; they are invalid.

Dry-run by default. Pass `--apply` to null the closing fields, which makes the
invalid rows unusable rather than silently zero.

Run inside the backend container:
    python scripts/invalidate_stale_clv.py            # count only
    python scripts/invalidate_stale_clv.py --apply    # clear them
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.database import AsyncSessionLocal
from app.services.clv import invalidate_stale_clv


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        result = await invalidate_stale_clv(db, apply=args.apply)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
