if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.odds import MarketSnapshot

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            snaps = (await db.execute(
                select(MarketSnapshot)
                .where(MarketSnapshot.fixture_id == 43765)
                .where(MarketSnapshot.market_type == "Correct Score")
            )).scalars().all()

            print(f"CS snapshots: {len(snaps)}")
            for s in sorted(snaps, key=lambda x: x.bookmaker or ""):
                print(f"  [{s.bookmaker}] {s.odds}")

    asyncio.run(main())
