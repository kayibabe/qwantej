"""Read-only, repeatable snapshot of the Match explorer's full daily candidate feed."""
import asyncio
import json
from pathlib import Path
from sqlalchemy import text
from app.database import engine
from app.services.settlement import evaluate_selection

SQL = """
WITH ranked AS (
 SELECT p.id, p.match_id, p.market, p.selection, p.model_run_id,
 p.model_version, p.q_score, p.model_probability, p.edge,
 p.source_decimal_odds AS odds, p.source_odds_at, p.source_odds_id,
 p.source_odds_provenance, p.created_at, p.as_of_at, p.decision_at,
 r.completed_at AS run_completed_at,
 m.kickoff_at, m.status, m.home_goals, m.away_goals,
 (m.kickoff_at AT TIME ZONE 'Africa/Blantyre')::date AS day,
 c.name AS competition,
 max(p.model_run_id) OVER (PARTITION BY p.match_id,p.market) AS latest_run
 FROM predictions p JOIN matches m ON m.id=p.match_id
 JOIN model_runs r ON r.id=p.model_run_id
 JOIN competitions c ON c.id=m.competition_id
 WHERE r.status='COMPLETED'
 AND r.target_date=(m.kickoff_at AT TIME ZONE 'Africa/Blantyre')::date
 AND m.excluded_from_models=false
 AND m.kickoff_at < '2026-10-25 22:00:00+00'
)
SELECT * FROM ranked WHERE model_run_id=latest_run AND q_score>=75
ORDER BY kickoff_at,id
"""

async def main():
    engine.echo = False
    async with engine.connect() as conn:
        await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        captured = (await conn.execute(text('SELECT CURRENT_TIMESTAMP'))).scalar()
        rows = [dict(r) for r in (await conn.execute(text(SQL))).mappings()]
        for r in rows:
            r['outcome'] = None
            if r['status']=='FINISHED' and r['home_goals'] is not None and r['away_goals'] is not None:
                try:
                    r['outcome'] = evaluate_selection(r['market'],r['home_goals'],r['away_goals']).value
                except ValueError:
                    r['outcome'] = 'unsupported'
        Path('/tmp/filter_snapshot.json').write_text(json.dumps({'captured_at':str(captured),'rows':rows},default=str))
        print(json.dumps({'captured_at':str(captured),'rows':len(rows)}))
    await engine.dispose()

asyncio.run(main())
