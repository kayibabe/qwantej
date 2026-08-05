if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.signal import Signal
    from app.models.fixture import Fixture
    from app.models.odds import MarketSnapshot

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            fix_id = 43765

            fix = (await db.execute(select(Fixture).where(Fixture.id == fix_id))).scalars().first()
            sig = (await db.execute(select(Signal).where(Signal.fixture_id == fix_id))).scalars().first()

            print("=== FIXTURE ===")
            for c in fix.__table__.columns:
                v = getattr(fix, c.name, None)
                if v is not None:
                    print(f"  {c.name}: {v}")

            print("\n=== SIGNAL ===")
            for c in sig.__table__.columns:
                v = getattr(sig, c.name, None)
                if v is not None:
                    print(f"  {c.name}: {v}")

            snaps = (await db.execute(
                select(MarketSnapshot).where(MarketSnapshot.fixture_id == fix_id)
            )).scalars().all()

            print(f"\n=== MARKET SNAPSHOTS ({len(snaps)}) ===")
            for s in snaps:
                print(f"  [{s.market_type}] {s.bookmaker}: {s.odds}")

    asyncio.run(main())
