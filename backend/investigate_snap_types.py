if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.odds import MarketSnapshot

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(MarketSnapshot.market_type, func.count())
                .where(MarketSnapshot.fixture_id == 43765)
                .group_by(MarketSnapshot.market_type)
                .order_by(func.count().desc())
            )).all()
            for mt, cnt in rows:
                print(f"  {cnt:4d}  {mt}")

    asyncio.run(main())
