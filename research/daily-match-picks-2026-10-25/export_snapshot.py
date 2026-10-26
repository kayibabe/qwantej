"""Read-only extract for reconstructing Daily Match Picks by historical date."""
import asyncio,json
from pathlib import Path
from sqlalchemy import text
from app.database import engine
from app.services.settlement import evaluate_selection

SQL="""
SELECT p.id,p.match_id,p.market,p.selection,p.q_score,p.model_probability,
 p.q_grade::text AS q_grade,p.model_run_id,p.model_version,
 p.source_odds_id,p.source_odds_at,p.source_decimal_odds AS odds,
 p.source_odds_provenance,p.created_at,p.as_of_at,p.decision_at,
 m.kickoff_at,m.status::text AS status,m.home_goals,m.away_goals,
 (m.kickoff_at AT TIME ZONE 'Africa/Blantyre')::date AS day
FROM predictions p JOIN matches m ON m.id=p.match_id
WHERE p.q_score>=70 AND p.source_decimal_odds>=2 AND p.source_decimal_odds<3
AND m.kickoff_at < '2026-10-25 22:00:00+00'
ORDER BY p.created_at DESC,p.id DESC
"""
async def main():
 engine.echo=False
 async with engine.connect() as conn:
  await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
  captured=(await conn.execute(text('SELECT CURRENT_TIMESTAMP'))).scalar()
  rows=[dict(r) for r in (await conn.execute(text(SQL))).mappings()]
  for r in rows:
   r['outcome']=None
   if r['status']=='FINISHED' and r['home_goals'] is not None and r['away_goals'] is not None:
    try:r['outcome']=evaluate_selection(r['selection'],r['home_goals'],r['away_goals']).value
    except ValueError:
     try:r['outcome']=evaluate_selection(r['market'],r['home_goals'],r['away_goals']).value
     except ValueError:r['outcome']='unsupported'
  Path('/tmp/daily_match_picks_snapshot.json').write_text(json.dumps({'captured_at':str(captured),'rows':rows},default=str))
  print(json.dumps({'captured_at':str(captured),'rows':len(rows)}))
 await engine.dispose()
asyncio.run(main())
