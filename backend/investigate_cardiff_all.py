if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, or_, and_
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.fixture import Fixture
    from datetime import date, timedelta

    async def main():
        await init_db()
        async with AsyncSessionLocal() as db:
            cutoff = date(2026, 8, 1) - timedelta(days=365)
            rows = (await db.execute(
                select(Fixture)
                .where(and_(
                    Fixture.event_date >= cutoff,
                    Fixture.home_score.is_not(None),
                    or_(Fixture.home_team == "Cardiff MET", Fixture.away_team == "Cardiff MET"),
                ))
                .order_by(Fixture.event_date)
            )).scalars().all()

            print(f"All Cardiff MET completed fixtures in 365-day window ({len(rows)} total):")
            for f in rows:
                side = "HOME" if f.home_team == "Cardiff MET" else "AWAY"
                scored = f.home_score if side == "HOME" else f.away_score
                conceded = f.away_score if side == "HOME" else f.home_score
                print(f"  {f.event_date}  {side}  {f.home_team} vs {f.away_team}  {f.home_score}-{f.away_score}  (scored={scored}, conceded={conceded})  [{f.league} / {f.country}]")

    asyncio.run(main())
