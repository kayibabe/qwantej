if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.odds import MarketSnapshot
    from app.services.signal_engine import _build_poisson_odds, _latest_snapshots
    import app.engines.poisson as poi_engine

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            snaps_raw = (await db.execute(
                select(MarketSnapshot).where(MarketSnapshot.fixture_id == 43765)
            )).scalars().all()

            snaps = _latest_snapshots(snaps_raw)
            poi_odds, poi_signal_odds = _build_poisson_odds(snaps)

            print(f"poi_odds keys (sample): {list(poi_odds.keys())[:10]}")
            print(f"s00 (0-0 odds): {poi_odds.get('s00')}")
            print(f"s10 (1-0 odds): {poi_odds.get('s10')}")
            print(f"s20 (2-0 odds): {poi_odds.get('s20')}")
            print(f"s30 (3-0 odds): {poi_odds.get('s30')}")
            print(f"s40 (4-0 odds): {poi_odds.get('s40')}")
            print(f"s50 (5-0 odds): {poi_odds.get('s50')}")

            poi_result = poi_engine.analyse_fixture(
                fixture_id=43765,
                odds=poi_odds,
                signal_odds=poi_signal_odds,
                form_lambdas=None,
            )
            print(f"\npoi_result: {poi_result}")
            if poi_result:
                for attr in dir(poi_result):
                    if not attr.startswith("_"):
                        print(f"  {attr}: {getattr(poi_result, attr)}")

    asyncio.run(main())
