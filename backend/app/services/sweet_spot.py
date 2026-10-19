"""Frozen paper experiment: no publication, bets, or historical backfill."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import random

from sqlalchemy import select, text
from app.models.sweet_spot import SweetSpotEvent

CAT = timezone(timedelta(hours=2))
RULE = 'away-q65-odds180-300-v1'
PROTOCOL = dict(rule_version=RULE, mode='paper_only', earliest_kickoff_date='2026-10-19',
    minimum_review_date='2027-01-16', required_settled=300, required_matchdays=30,
    market='away_win', q_min=65, odds_min_inclusive=1.8, odds_max_exclusive=3,
    maximum_quote_age_hours=3, stake_units=1, minimum_edge=None,
    selection='First stored away-win prediction per fixture; no replacements',
    evidence_requirements='Explicit decision time, original features and named source; no replay/fallback; all captures before kickoff',
    review_policy='All three review requirements must be met. No automatic promotion. No interim threshold changes.')


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(payload):
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def parse(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def reasons(row, now):
    """Outcomes are intentionally absent from the capture query and this function."""
    result = []
    kickoff = parse(row['kickoff_at'])
    if kickoff <= now:
        result.append('missed_pre_kickoff_capture')
    if row.get('prediction_id') is None:
        return result + ['missing_prediction']
    created, decision, quote = (parse(row.get(k)) for k in ('created_at', 'decision_at', 'source_odds_at'))
    if not all((created, decision, quote)):
        result.append('missing_timestamps')
    elif not (quote <= decision <= now and created <= now and decision < kickoff and created < kickoff):
        result.append('invalid_timestamp_order')
    elif now - quote > timedelta(hours=3):
        # Entry is made NOW, so quote must still be fresh at actual capture.
        result.append('stale_quote_at_capture')
    if row.get('as_of_at'):
        result.append('replay')
    provenance = row.get('source_odds_provenance') or {}
    if provenance.get('is_fallback'):
        result.append('fallback_odds')
    if not provenance.get('source_type') or not provenance.get('bookmaker'):
        result.append('missing_price_source')
    if not row.get('feature_snapshot') or not row.get('model_version'):
        result.append('missing_model_context')
    for field, predicate, reason in [('q_score', lambda v: 65 <= v <= 100, 'q_below_65_or_invalid'),
                                    ('odds', lambda v: 1.8 <= v < 3, 'odds_outside_range')]:
        v = row.get(field)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not predicate(v):
            result.append(reason)
    if row.get('excluded_from_models'):
        result.append('fixture_excluded_from_models')
    if row.get('match_status') != 'SCHEDULED':
        result.append('fixture_not_scheduled')
    return result


async def append(db, key, kind, payload):
    db.add(SweetSpotEvent(event_key=key, kind=kind, payload=payload, sha256=digest(payload)))
    await db.flush()


async def tick(db):
    # Transaction-scoped lock covers duplicates, task retries and overlapping workers.
    await db.execute(text('SELECT pg_advisory_xact_lock(20851965)'))
    protocol = await db.scalar(select(SweetSpotEvent).where(SweetSpotEvent.event_key == 'protocol'))
    if protocol is None:
        now = await db.scalar(select(text('clock_timestamp()')))
        await append(db, 'protocol', 'protocol', {**PROTOCOL, 'activated_at':now.isoformat()})
    else:
        expected = {k:protocol.payload.get(k) for k in PROTOCOL}
        if expected != PROTOCOL or digest(protocol.payload) != protocol.sha256:
            raise ValueError('Frozen protocol mismatch: refusing to change the experiment')
    now = await db.scalar(select(text('clock_timestamp()')))
    start = datetime(2026, 10, 19, tzinfo=CAT)
    # No outcome columns. LEFT JOIN retains fixtures without predictions.
    opportunities = (await db.execute(text('''
        SELECT m.id match_id, m.kickoff_at, m.status match_status, m.excluded_from_models,
               h.name home_team, a.name away_team, c.name competition,
               p.id prediction_id, p.created_at, p.decision_at, p.source_odds_at,
               p.as_of_at, p.q_score, p.source_decimal_odds odds, p.model_version,
               p.edge model_edge, p.model_probability, p.feature_snapshot, p.source_odds_provenance
        FROM matches m JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        JOIN competitions c ON c.id=m.competition_id
        LEFT JOIN LATERAL (SELECT * FROM predictions p WHERE p.match_id=m.id AND p.market='away_win'
                           ORDER BY p.created_at,p.id LIMIT 1) p ON TRUE
        WHERE m.kickoff_at >= :start AND m.kickoff_at <= :horizon
          AND NOT EXISTS (SELECT 1 FROM sweet_spot_events e WHERE e.event_key='decision:' || m.id::text)
        ORDER BY m.kickoff_at, m.id
    '''), {'start':start, 'horizon':now+timedelta(days=7)})).mappings().all()
    captured = qualified = 0
    for row in opportunities:
        captured_at = await db.scalar(select(text('clock_timestamp()')))
        # Wait for the first prediction; report missing only once kickoff is missed.
        if row['prediction_id'] is None and row['kickoff_at'] > captured_at:
            continue
        payload = json.loads(json.dumps(dict(row), default=str))
        rejected = reasons(payload, captured_at)
        payload.update(captured_at=captured_at.isoformat(), rule_version=RULE,
                       qualified=not rejected, reasons=rejected,
                       day=row['kickoff_at'].astimezone(CAT).date().isoformat())
        # Qualifying snapshots are inserted by a DB-side pre-kickoff guard below.
        await append(db, f"decision:{row['match_id']}", 'decision', payload)
        captured += 1
        qualified += not rejected
    # Settlement is separate from capture. Corrections append; old evidence remains.
    decisions = (await db.execute(select(SweetSpotEvent).where(SweetSpotEvent.kind=='decision'))).scalars().all()
    settlements = (await db.execute(select(SweetSpotEvent).where(SweetSpotEvent.kind=='settlement').order_by(SweetSpotEvent.id))).scalars().all()
    latest = {r.payload['match_id']:r.payload for r in settlements}
    ids = [r.payload['match_id'] for r in decisions if r.payload['qualified']]
    outcomes = {}
    if ids:
        from app.models import Match
        matches = (await db.execute(select(Match).where(Match.id.in_(ids)))).scalars().all()
        outcomes = {m.id:m for m in matches}
    settled = 0
    for event in decisions:
        p = event.payload
        if not p['qualified'] or p['match_id'] not in outcomes:
            continue
        m = outcomes[p['match_id']]
        result = 'pending'
        if m.status.value.upper() == 'FINISHED' and m.home_goals is not None and m.away_goals is not None:
            result = 'won' if m.away_goals > m.home_goals else 'lost'
        body = dict(match_id=m.id, status=m.status.value, home_goals=m.home_goals, away_goals=m.away_goals,
                    result=result, profit=(p['odds']-1 if result=='won' else -1 if result=='lost' else None))
        prior = latest.get(m.id)
        if prior and all(prior.get(k)==v for k,v in body.items()):
            continue
        if not prior and result=='pending':
            continue
        revision = (prior or {}).get('revision', 0)+1
        body.update(revision=revision, observed_at=now.isoformat())
        await append(db, f'settlement:{m.id}:{revision}', 'settlement', body)
        settled += 1
    slot = int(now.timestamp()) // 300
    if not await db.scalar(select(SweetSpotEvent.id).where(SweetSpotEvent.event_key==f'run:{slot}')):
        await append(db, f'run:{slot}', 'run', dict(at=now.isoformat(), day=now.astimezone(CAT).date().isoformat(),
                    captured=captured, qualified=qualified, settlement_events=settled))
    return dict(captured=captured, qualified=qualified, settlement_events=settled, mode='paper_only')


def metrics(rows):
    resolved = [r for r in rows if r['result'] in ('won', 'lost')]
    n = len(resolved)
    profit = sum(r['profit'] for r in resolved)
    curve = peak = drawdown = 0
    for r in sorted(resolved, key=lambda r:(r['kickoff_at'],r['match_id'])):
        curve += r['profit']; peak = max(peak,curve); drawdown = max(drawdown,peak-curve)
    return dict(picks=len(rows), settled=n, pending=len(rows)-n,
                wins=sum(r['result']=='won' for r in resolved), profit=profit,
                roi=100*profit/n if n else None, drawdown=drawdown,
                haircut_roi=100*sum(r['profit']*.95 if r['result']=='won' else r['profit'] for r in resolved)/n if n else None,
                matchdays=len({r['day'] for r in resolved}))


def build_report(events, now):
    for e in events:
        if digest(e.payload) != e.sha256:
            raise ValueError('Ledger integrity check failed')
    protocols = [e.payload for e in events if e.kind=='protocol']
    decisions = [e.payload for e in events if e.kind=='decision']
    latest = {e.payload['match_id']:e.payload for e in events if e.kind=='settlement'}
    runs = [e.payload for e in events if e.kind=='run']
    picks = [{**p, **latest.get(p['match_id'], {'result':'pending','profit':None})} for p in decisions if p['qualified']]
    summary = metrics(picks)
    by_day = defaultdict(list)
    for p in picks:
        if p['result']!='pending': by_day[p['day']].append(p)
    interval = None
    if len(by_day) >= 10:
        clusters = [(sum(p['profit'] for p in ps),len(ps)) for ps in by_day.values()]
        rng = random.Random(20851965); samples=[]
        for _ in range(2000):
            chosen=rng.choices(clusters,k=len(clusters))
            samples.append(100*sum(p for p,n in chosen)/sum(n for p,n in chosen))
        samples.sort(); interval=[samples[49],samples[1949]]
    today = now.astimezone(CAT).date()
    first = date.fromisoformat(PROTOCOL['earliest_kickoff_date'])
    run_days={r['day'] for r in runs}
    days=[]
    for i in range(max(0,(today-first).days+1)):
        day=(first+timedelta(days=i)).isoformat(); ps=[p for p in picks if p['day']==day]
        days.append(dict(day=day, collection_observed=day in run_days, **metrics(ps)))
    health = 'not_started' if not runs else 'current' if now-parse(runs[-1]['at']) <= timedelta(minutes=15) else 'stale'
    return dict(mode='paper_only', promotion_ready=False, protocol=protocols[0] if protocols else PROTOCOL,
        collection_status=health, last_run=runs[-1] if runs else None, summary=summary,
        review_due=today>=date.fromisoformat(PROTOCOL['minimum_review_date']) and summary['settled']>=300 and summary['matchdays']>=30,
        exclusions=dict(Counter(r for p in decisions for r in p['reasons'])), observed_opportunities=len(decisions),
        missing_results=sum(p['result']=='pending' and parse(p['kickoff_at'])<now-timedelta(hours=6) for p in picks),
        roi_interval_95=interval, interval_note='Descriptive day-cluster interval after 10 settled matchdays; not proof of an edge.',
        by_league={k:metrics([p for p in picks if p['competition']==k]) for k in sorted({p['competition'] for p in picks})},
        by_model={k:metrics([p for p in picks if p['model_version']==k]) for k in sorted({p['model_version'] for p in picks})},
        days=days, picks=sorted(picks,key=lambda p:p['kickoff_at'],reverse=True),
        limitations=['Coverage includes fixtures known to this database, not all football fixtures.',
                     'Current collection status does not prove uninterrupted coverage; missing runs and missed captures remain visible.',
                     'Postponed/cancelled picks remain unresolved, not assumed refunded.',
                     'Simulated entry odds; execution and actual costs unverified.'])


async def report(db):
    events=(await db.execute(select(SweetSpotEvent).order_by(SweetSpotEvent.id))).scalars().all()
    return build_report(events, datetime.now(timezone.utc))
