import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'signals' ORDER BY ordinal_position"))
        cols = [row[0] for row in r.all()]
        print("SIGNALS COLUMNS:", cols)
        r2 = await db.execute(text("SELECT COUNT(*) FROM signals"))
        print("SIGNALS COUNT:", r2.scalar())

asyncio.run(check())
