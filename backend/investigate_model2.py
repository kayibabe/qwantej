if __name__ == "__main__":
    import pickle, pathlib, zlib

    def crc_hash(name):
        return zlib.crc32(name.lower().strip().encode()) & 0x7FFFFFFF

    cache = sorted(pathlib.Path(".cache/advanced_models/").glob("*.pkl"))
    if not cache:
        print("No cache"); exit()

    with open(cache[-1], "rb") as f:
        obj = pickle.load(f)

    m = obj._zinb_models.get("premier league")
    print(f"Premier League model: {m}")
    if not m:
        exit()

    cardiff_hash = crc_hash("Cardiff MET")
    print(f"Cardiff MET crc32 hash: {cardiff_hash}")
    print(f"Cardiff MET in _attack: {cardiff_hash in m._attack}")

    if cardiff_hash in m._attack:
        print(f"Cardiff MET attack params: {m._attack[cardiff_hash]}")

    # Find all teams with high attack mu
    print("\nTop 10 attack teams:")
    sorted_teams = sorted(m._attack.items(), key=lambda x: x[1].mu, reverse=True)
    for team_hash, params in sorted_teams[:10]:
        print(f"  hash={team_hash}  mu={params.mu:.4f}")

    # Now check what DB team name maps to each of the top hashes
    import asyncio
    from sqlalchemy import select, or_, text
    from app.core.database import AsyncSessionLocal, init_db
    from app.models.fixture import Fixture
    from datetime import date, timedelta

    async def find_team(h):
        await init_db()
        cutoff = (date(2026, 8, 1) - timedelta(days=365)).isoformat()
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Fixture.home_team, Fixture.away_team)
                .where(text(f"event_date >= '{cutoff}'"))
                .where(Fixture.home_score.is_not(None))
                .distinct()
            )).all()
            teams = set()
            for r in rows:
                teams.add(r[0])
                teams.add(r[1])
            for t in teams:
                if crc_hash(t) == h:
                    return t
        return None

    async def main():
        for team_hash, params in sorted_teams[:10]:
            name = await find_team(team_hash)
            print(f"  hash={team_hash}  mu={params.mu:.4f}  team={name or '?'}")

    print("\nResolving top attack team names:")
    asyncio.run(main())
