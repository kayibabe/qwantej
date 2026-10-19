"""Read-only full prediction export for rejection-ledger research."""
import asyncio, json
import sys
from sqlalchemy import text
from app.database import AsyncSessionLocal, engine

async def main():
    engine.echo = False
    async with AsyncSessionLocal() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        if '--ledger' in sys.argv:
            from app.services.accumulator_builder import AccumulatorBuilder, active_ticket_specs, market_priced, selection_rejection_reasons, _research_market_rejection_reasons
            from app.models import TicketType
            dates = (await db.execute(text("SELECT DISTINCT target_date FROM model_runs WHERE status='COMPLETED' ORDER BY target_date"))).scalars().all()
            output = []
            for day in dates:
                builder = AccumulatorBuilder(db)
                run = await builder._resolve_model_run(day, None)
                spec = next(s for s in active_ticket_specs() if s.ticket_type == TicketType.SAFE)
                learning = (run.config_snapshot or {}).get('learning', {})
                gates = await builder._load_calibration_gates(day, run.model_version, learning.get('base_model_version') or learning.get('requested_model_version'))
                items = []
                for leg in await builder._load_all_legs(day, run.id):
                    if spec.pricing == 'market' and leg.fair_probability is not None and leg.best_odds > 0:
                        leg = market_priced(leg)
                    reasons = _research_market_rejection_reasons(leg, spec) + selection_rejection_reasons(leg, spec, gates)
                    if reasons:
                        items.append(dict(leg=leg, reason_codes=reasons))
                output.extend(dict(id=i['leg'].prediction_id, date=str(day), reasons=i['reason_codes'], ledger_edge=i['leg'].edge, ledger_odds=i['leg'].best_odds) for i in items)
            print(json.dumps(output, default=str))
            return
        rows = (await db.execute(text('''
          SELECT p.id, p.match_id, p.market, p.selection, p.model_version,
            p.q_score, p.edge, p.model_probability, p.model_agreement,
            p.source_decimal_odds odds, p.source_odds_at, p.created_at,
            p.decision_at, p.as_of_at, p.recommendation_status,
            p.recommendation_reasons, p.source_odds_provenance,
            m.kickoff_at, m.status, m.home_goals, m.away_goals,
            c.name competition, p.model_run_id
          FROM predictions p JOIN matches m ON m.id=p.match_id
          JOIN competitions c ON c.id=m.competition_id
          WHERE NOT m.excluded_from_models
          ORDER BY m.kickoff_at, p.created_at, p.id
        '''))).mappings().all()
        print(json.dumps([dict(r) for r in rows], default=str))

asyncio.run(main())
