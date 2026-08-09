"""
CLI runner for the Phase 1A historical-warehouse ETL loaders.

Run from the backend/ directory:

  # Load all Football-Data.co.uk seasons (2019–2024) into the warehouse
  python -m scripts.etl.run_etl --source fdcuk

  # Load specific seasons and leagues
  python -m scripts.etl.run_etl --source fdcuk --seasons 2023 2024 --leagues E0 SP1 D1

  # Enrich existing rows with StatsBomb xG
  python -m scripts.etl.run_etl --source statsbomb

  # Load OpenFootball results (supplements missing fixtures)
  python -m scripts.etl.run_etl --source openfootball --seasons 2022 2023 2024

  # Load all sources in sequence
  python -m scripts.etl.run_etl --source all --seasons 2020 2021 2022 2023 2024

  # Dev/smoke-test: limit StatsBomb to 50 matches
  python -m scripts.etl.run_etl --source statsbomb --max-matches 50

Options:
  --source        fdcuk | statsbomb | openfootball | all
  --seasons       List of season start years (e.g. 2022 2023 2024)
  --leagues       Football-Data division codes for fdcuk only (default: all)
  --max-matches   StatsBomb only: stop after N matches (default: unlimited)
  --no-cache      Re-download files even if cached
  --dry-run       Parse and print counts without writing to DB
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure backend/ is on the path when running as a module
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("etl.runner")


async def run(args: argparse.Namespace) -> None:
    sources = (
        ["fdcuk", "statsbomb", "openfootball"]
        if args.source == "all"
        else [args.source]
    )

    async with AsyncSessionLocal() as db:
        for source in sources:
            total = await _run_source(db, source, args)
            logger.info("=== %s: %d rows upserted ===", source.upper(), total)


async def _run_source(db: AsyncSession, source: str, args: argparse.Namespace) -> int:
    use_cache = not getattr(args, "no_cache", False)

    if source == "fdcuk":
        from scripts.etl.football_data_co_uk import FootballDataCoUkLoader
        loader = FootballDataCoUkLoader()
        seasons = [int(s) for s in args.seasons] if args.seasons else None
        divisions = args.leagues if args.leagues else None
        return await loader.load(db, seasons=seasons, divisions=divisions, use_cache=use_cache)

    elif source == "statsbomb":
        from scripts.etl.statsbomb import StatsBombLoader
        loader = StatsBombLoader()
        max_matches = int(args.max_matches) if args.max_matches else None
        return await loader.load(db, use_cache=use_cache, max_matches=max_matches)

    elif source == "openfootball":
        from scripts.etl.openfootball import OpenFootballLoader
        loader = OpenFootballLoader()
        seasons = [int(s) for s in args.seasons] if args.seasons else None
        comps = args.leagues if args.leagues else None
        return await loader.load(db, seasons=seasons, competitions=comps, use_cache=use_cache)

    else:
        logger.error("Unknown source: %s", source)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwantej historical warehouse ETL")
    parser.add_argument(
        "--source",
        required=True,
        choices=["fdcuk", "statsbomb", "openfootball", "all"],
        help="Data source to load",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        help="Season start years (e.g. 2022 2023 2024)",
    )
    parser.add_argument(
        "--leagues",
        nargs="+",
        help="Division/competition codes (fdcuk: E0, SP1 … | openfootball: en.1, de.1 …)",
    )
    parser.add_argument(
        "--max-matches",
        dest="max_matches",
        help="StatsBomb: stop after this many matches",
    )
    parser.add_argument(
        "--no-cache",
        dest="no_cache",
        action="store_true",
        help="Re-download files even if cached",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Parse without writing to DB (not yet implemented)",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.warning("--dry-run is not yet implemented; aborting")
        sys.exit(1)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
