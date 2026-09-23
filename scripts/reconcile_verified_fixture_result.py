"""Import a reviewed external result and pass it through normal settlement.

Example (only after verifying the source report):
    python scripts/reconcile_verified_fixture_result.py \
        --fixture-id <uuid> --home-goals 1 --away-goals 0 \
        --source-url https://example.org/match-report \
        --observed-at 2026-09-23T20:00:00+00:00

The script appends a result snapshot and audit event. It refuses to replace a
finished or already-settled result; corrections use the separate governed path.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from uuid import UUID

from backend.core.db import session_scope
from backend.services.verified_fixture_results import ingest_verified_fixture_result
from backend.workers.settlement_worker import run_settlement


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-id", required=True, type=UUID)
    parser.add_argument("--home-goals", required=True, type=int)
    parser.add_argument("--away-goals", required=True, type=int)
    parser.add_argument("--source-url", required=True)
    parser.add_argument(
        "--observed-at",
        type=datetime.fromisoformat,
        default=datetime.now(UTC),
        help="Timezone-aware ISO-8601 observation time; defaults to now in UTC.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with session_scope() as session:
        changed = ingest_verified_fixture_result(
            session,
            fixture_id=args.fixture_id,
            home_goals=args.home_goals,
            away_goals=args.away_goals,
            source_url=args.source_url,
            observed_at=args.observed_at,
        )
        settlement = run_settlement(session, now=args.observed_at.astimezone(UTC))
    print(
        json.dumps(
            {
                "fixture_updated": changed,
                "settled_predictions": settlement.total_settled,
                "settlement_errors": settlement.total_errors,
            }
        )
    )


if __name__ == "__main__":
    main()
