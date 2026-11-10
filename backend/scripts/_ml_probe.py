import asyncio
from datetime import date
from app.database import AsyncSessionLocal
from app.services.model_learning import _load_learning_examples

async def main():
    async with AsyncSessionLocal() as db:
        rows = await _load_learning_examples(db, date(2026,3,15), date(2026,9,10), "0.3.0")
        print("train rows:", len(rows))
        rows2 = await _load_learning_examples(db, date(2026,9,11), date(2026,10,10), "0.3.0")
        print("val rows:", len(rows2))

asyncio.run(main())
