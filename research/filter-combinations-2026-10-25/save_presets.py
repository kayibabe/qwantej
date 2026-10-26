"""Save the six user-requested research filters through the app's validated handler."""
import asyncio
import json
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models import User, UserMatchFilterPreset
from app.api.v1.match_filters import MatchFilterCriteria, MatchFilterPresetCreate, save_match_filter_preset, list_match_filter_presets
from app.services.market_catalog import get_market_definition

async def main():
    engine.echo=False
    away=get_market_definition('away_win').display_name
    btts=get_market_definition('btts_no').display_name
    specs=[
        ('All eligible candidates | Q >=75', {}),
        ('Away win | Q 75-80 | Probability <=70% | Odds <=5',dict(market=away,max_q_score=80,max_probability=.7,max_odds=5)),
        ('Away win | Q 75-80 | Odds 2-5',dict(market=away,max_q_score=80,min_odds=2,max_odds=5)),
        ('BTTS No | Q >=75 | Probability <=70%',dict(market=btts,max_probability=.7)),
        ('All markets | Q 75-80 | Probability 60-70% | Odds 2-3',dict(max_q_score=80,min_probability=.6,max_probability=.7,min_odds=2,max_odds=3)),
        ('BTTS No | Q >=75',dict(market=btts)),
    ]
    expected={name:MatchFilterCriteria(**criteria).model_dump() for name,criteria in specs}
    async with AsyncSessionLocal() as db:
        user=(await db.execute(select(User).where(User.email=='cmhango@gmail.com'))).scalar_one()
        existing=await list_match_filter_presets(db=db,user=user)
        for name,criteria in expected.items():
            matches=[r for r in existing if r.name==name]
            if matches:
                assert len(matches)==1 and matches[0].criteria==criteria, f'Conflicting existing filter: {name}'
                continue
            await save_match_filter_preset(payload=MatchFilterPresetCreate(name=name,criteria=criteria),db=db,user=user)
        await db.commit()
    async with AsyncSessionLocal() as db:
        user=(await db.execute(select(User).where(User.email=='cmhango@gmail.com'))).scalar_one()
        saved=await list_match_filter_presets(db=db,user=user)
        found=[r for r in saved if r.name in expected]
        assert len(found)==6
        for r in found: assert r.criteria==expected[r.name]
        print(json.dumps({'verified_account':user.email,'saved_filters':[{'id':r.id,'name':r.name,'criteria':r.criteria} for r in found]},indent=2))
    await engine.dispose()

asyncio.run(main())
