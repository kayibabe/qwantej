"""Integration checks in a disposable isolated PostgreSQL schema, never live rows."""
import asyncio
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.database import engine, Base
from app.models import Competition, Team, Match, MatchStatus, Prediction, QGrade, SweetSpotEvent
from app.services.sweet_spot import tick, report, append


async def main():
    engine.echo=False
    schema='test_sweet_spot_'+uuid4().hex
    async with engine.connect() as conn:
        try:
            await conn.execute(text(f'CREATE SCHEMA {schema}'))
            await conn.execute(text(f'SET search_path TO {schema}'))
            await conn.run_sync(Base.metadata.create_all)
            def migrate(sync):
                path=Path('/app/migrations/versions/b208d5e9f3a2_sweet_spot_events.py')
                spec=importlib.util.spec_from_file_location('migration',path)
                mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                with Operations.context(MigrationContext.configure(sync)):
                    mod.upgrade()
                    mod.upgrade()  # Baseline/checkfirst compatibility.
            await conn.run_sync(migrate)
            await conn.commit()
            async with AsyncSession(bind=conn, expire_on_commit=False) as db:
                now=datetime.now(timezone.utc)
                kickoff=max(now+timedelta(days=2),datetime(2026,10,20,tzinfo=timezone.utc))
                c=Competition(api_football_id=1,name='Test',country='Test'); db.add(c); await db.flush()
                h=Team(api_football_id=1,name='Home',competition_id=c.id)
                a=Team(api_football_id=2,name='Away',competition_id=c.id)
                db.add_all([h,a]); await db.flush()
                matches=[Match(api_football_id=i,competition_id=c.id,home_team_id=h.id,away_team_id=a.id,
                               kickoff_at=kickoff,season='2026') for i in [1,2,3]]
                db.add_all(matches); await db.flush()
                def prediction(match,q,created):
                    return Prediction(match_id=match.id,market='away_win',selection='away_win',q_score=q,q_grade=QGrade.A,
                        model_version='test',model_probability=.6,model_agreement=.1,source_decimal_odds=2.5,
                        created_at=created,decision_at=now-timedelta(minutes=1),source_odds_at=now-timedelta(minutes=2),
                        feature_snapshot={'test':True},source_odds_provenance={'bookmaker':'Test','source_type':'test'})
                db.add_all([prediction(matches[0],65,now-timedelta(minutes=1)),
                            prediction(matches[1],50,now-timedelta(minutes=1))])
                await db.flush()
                first=await tick(db); assert first['captured']==2 and first['qualified']==1,first
                db.add(prediction(matches[1],90,now)); await db.flush()
                again=await tick(db); assert again['captured']==0,again
                events=(await db.execute(select(SweetSpotEvent).where(SweetSpotEvent.kind=='decision'))).scalars().all()
                assert len(events)==2 and sum(e.payload['qualified'] for e in events)==1
                # Settlement revisions preserve the original capture, including a correction reverting to pending.
                matches[0].status=MatchStatus.FINISHED; matches[0].home_goals=0; matches[0].away_goals=1
                await db.flush(); await tick(db)
                r=await report(db); assert r['summary']['profit']==1.5 and r['summary']['settled']==1
                matches[0].home_goals=2; await db.flush(); await tick(db)
                r=await report(db); assert r['summary']['profit']==-1
                matches[0].status=MatchStatus.POSTPONED; await db.flush(); await tick(db)
                assert (await report(db))['summary']['settled']==0
                assert len((await db.execute(select(SweetSpotEvent).where(SweetSpotEvent.kind=='settlement'))).scalars().all())==3
                # Database rejects evidence rewrites and late qualification even outside the service.
                for query in ["UPDATE sweet_spot_events SET kind='tampered'", 'DELETE FROM sweet_spot_events']:
                    try:
                        async with db.begin_nested(): await db.execute(text(query))
                    except Exception as exc:
                        assert 'append-only' in str(exc)
                    else: raise AssertionError('Evidence rewrite unexpectedly succeeded')
                try:
                    async with db.begin_nested():
                        await append(db,'late-test','decision',dict(qualified=True,kickoff_at=now.isoformat()))
                except Exception as exc:
                    assert 'after kickoff' in str(exc)
                else: raise AssertionError('Late capture unexpectedly succeeded')
                await db.rollback()
            print('PASS: isolated schema migration, capture, first-prediction exclusion, retry idempotency, settlement/corrections, immutability, pre-kickoff DB guard')
        finally:
            await conn.rollback()
            await conn.execute(text('SET search_path TO public'))
            await conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
            await conn.commit()


asyncio.run(main())
