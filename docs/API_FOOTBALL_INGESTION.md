# API Football Point in Time Ingestion

The API-Football adapter is the acquisition path for the first bounded
walk-forward dataset. It canonicalizes provider identifiers, records every
fixture and statistics response as a point-in-time `stats_snapshots` row, and
archives pre-match bookmaker prices as immutable `odds_quotes`. It does not run
a model or treat retrospectively fetched match results as pre-kickoff features.

## Configuration

Set `API_FOOTBALL_KEY` only in the uncommitted `.env` file or deployment secret
store. `API_FOOTBALL_BASE_URL` defaults to the v3 HTTPS endpoint and
`API_FOOTBALL_TIMEOUT_SECONDS` defaults to 30. The client authenticates with the
`x-apisports-key` request header; the credential is never placed in a URL or
provider error message.

API-Football uses a common response wrapper with `errors`, `paging`, and
`response`, and its pre-match odds history is short-lived. The scheduled loader
therefore needs to capture prices prospectively rather than assume old prices
can be reconstructed later. See the provider's
[API-Football v3 getting-started guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide).

## Transactional service boundary

```python
from datetime import UTC, date, datetime

from backend.core.config import get_settings
from backend.core.db import session_scope
from backend.services.api_football_client import ApiFootballClient
from backend.services.api_football_ingestion import ingest_walk_forward_window

settings = get_settings()
client = ApiFootballClient.from_settings(settings)

with session_scope() as session:
    summary = ingest_walk_forward_window(
        session,
        client,
        league_id=39,
        season=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 9, 30),
        captured_at=datetime.now(UTC),
        include_fixture_statistics=True,
    )
```

The caller owns the outer commit. Each ingestion operation uses a savepoint, so
an invalid provider record, broken canonical mapping, or conflicting fixture
identity rolls back that batch. Exact fixture/statistics captures and odds
quotes are deduplicated on retry.

## Point in time safeguards

- Provider team, competition, season, and fixture IDs exist only in
  `source_mappings`; modelling code receives canonical UUIDs.
- The request receipt time is the `as_of_timestamp` for fixture/statistics
  observations. Provider odds use their own `update` timestamp.
- Fixture identity conflicts fail closed. Legitimate status, result, venue, or
  kickoff revisions create an immutable `audit_events` record.
- A finished fixture cannot regress to a non-final state.
- The feature-store service separately rejects any observation after its
  decision cutoff and rejects every cutoff at or after kickoff.
- Odds returned for fixtures outside the requested walk-forward window are
  ignored rather than creating unmapped or out-of-scope records.
- Only approved market mappings (`1X2`, `TOTALS`, `BTTS`, and
  `DOUBLE_CHANCE`) enter canonical odds storage. Unsupported provider markets
  are counted in the ingestion summary and recorded in `audit_events`; they are
  never silently passed through under provider-specific names.

## Remaining experiment boundary

The loader makes a reproducible dataset possible; it does not make the first
walk-forward experiment valid by itself. The experiment starts only after a
documented league, season, feature version, capture schedule, minimum sample,
baseline, and train/test windows are selected and enough genuinely pre-kickoff
odds observations have accumulated. Historical fixture results fetched today
may serve as outcomes or training history, but their receipt timestamps prevent
them from masquerading as historical pre-kickoff feature observations.
