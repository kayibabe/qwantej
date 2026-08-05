if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select, or_, and_
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.fixture import Fixture
    from datetime import date, timedelta

    async def main():
        await init_db()
        team = "Cardiff MET"
        before_date = date(2026, 8, 1)
        cutoff = before_date - timedelta(days=90)

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Fixture)
                .where(and_(
                    Fixture.event_date < before_date,
                    Fixture.event_date >= cutoff,
                    Fixture.home_score.is_not(None),
                    Fixture.away_score.is_not(None),
                    or_(Fixture.home_team == team, Fixture.away_team == team),
                ))
                .order_by(Fixture.event_date.desc())
                .limit(10)
            )).scalars().all()

            print(f"Cardiff MET recent fixtures (before {before_date}, window {cutoff} to {before_date}):")
            print(f"{'Date':<12} {'Home':<25} {'Away':<25} {'Score':<8} {'Goals for Cardiff'}")
            print("-" * 80)
            for f in rows:
                if f.home_team == team:
                    scored = f.home_score
                    conceded = f.away_score
                else:
                    scored = f.away_score
                    conceded = f.home_score
                score_str = f"{f.home_score}-{f.away_score}"
                print(f"{str(f.event_date):<12} {f.home_team[:24]:<25} {f.away_team[:24]:<25} {score_str:<8} scored={scored}")

            if not rows:
                print("No fixtures found")
                # check any fixtures at all
                all_rows = (await db.execute(
                    select(Fixture)
                    .where(or_(Fixture.home_team == team, Fixture.away_team == team))
                    .order_by(Fixture.event_date.desc())
                    .limit(10)
                )).scalars().all()
                print(f"\nAll Cardiff MET fixtures in DB:")
                for f in all_rows:
                    print(f"  {f.event_date} {f.home_team} vs {f.away_team} {f.home_score}-{f.away_score} status={f.status}")

    asyncio.run(main())
