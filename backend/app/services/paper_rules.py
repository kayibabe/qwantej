"""Frozen prospective paper rules: goals overs, home win, band-mix disagreements.

Each rule is a separate pre-registered paper experiment on the same
outcome-blind pattern as the away-win sweet-spot tracker: first stored
prediction per fixture, capture strictly before kickoff, fresh bookmaker
quote with provenance, append-only ledger with SHA-256 integrity, flat one
unit per pick, and no path to publication or staking. Rules were motivated by
settled research evidence (see each rule's `rationale`) but every capture is
prospective from `earliest_kickoff_date`; historical numbers are never
replayed into the ledger.

Adding a rule means adding an entry to RULES. Existing rule parameters are
frozen: the protocol row is verified on every run and any drift raises.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math

from sqlalchemy import select, text
from app.models.paper_rule import PaperRuleEvent
from app.models import Match
from app.services.sweet_spot import digest, metrics as cohort_metrics, parse

CAT = timezone(timedelta(hours=2))
MAX_QUOTE_AGE = timedelta(hours=3)
ADVISORY_LOCK_ID = 20851966

_COMMON = dict(
    mode='paper_only', stake_units=1, maximum_quote_age_hours=3,
    selection='First stored matching prediction per fixture; no replacements',
    evidence_requirements='Explicit decision time, original features and named source; no replay/fallback; all captures before kickoff',
    review_policy='All review requirements must be met. No automatic promotion. No interim threshold changes.',
)

# Historical numbers in `rationale` are the research evidence that motivated
# each frozen rule; they are descriptive of the past, not guarantees.
RULES: dict[str, dict] = {
    'over45-q70-odds200-300-v1': dict(
        market='over_4.5', q_min=70, odds_min_inclusive=2.0, odds_max_exclusive=3.0,
        earliest_kickoff_date='2026-11-08', minimum_review_date='2027-02-01',
        required_settled=100, required_matchdays=20,
        rationale=('Settled Daily Picks (from 2026-10-01, Q>=70, odds 2.00-3.00): Over 4.5 at '
                   '52.4% ROI / 58.3% hit over 12 selections; historical market ranking 49.4% ROI '
                   'over 14 picks; both meet the walk-forward accumulator gates.'),
        **_COMMON,
    ),
    'over25-q70-odds200-300-v1': dict(
        market='over_2.5', q_min=70, odds_min_inclusive=2.0, odds_max_exclusive=3.0,
        earliest_kickoff_date='2026-11-08', minimum_review_date='2027-02-01',
        required_settled=150, required_matchdays=25,
        rationale=('Settled Daily Picks: Over 2.5 at 22.3% ROI / 56.5% hit over 46 selections; '
                   'historical market ranking 23.3% ROI over 51 picks ("larger sample").'),
        **_COMMON,
    ),
    'home-q65-odds180-300-v1': dict(
        market='home_win', q_min=65, odds_min_inclusive=1.8, odds_max_exclusive=3.0,
        earliest_kickoff_date='2026-11-08', minimum_review_date='2027-02-01',
        required_settled=200, required_matchdays=30,
        rationale=('Broad by-market view: Home win is the only positive market (+3.2% ROI over '
                   '1,706 settled selections). Symmetric mirror of the frozen away-win rule, whose '
                   'recent window has decayed below zero.'),
        **_COMMON,
    ),
    'mix-q8590-mkt6570-v1': dict(
        model_band=[0.85, 0.90], market_band=[0.65, 0.70],
        earliest_kickoff_date='2026-11-08', minimum_review_date='2027-02-01',
        required_settled=60, required_matchdays=15,
        rationale=('QwanEj x Market disagreement cell 85-90 x 65-70: +8.2% ROI over 48 settled '
                   'picks (70.8% hit). Model moderately confident where the market prices lower.'),
        **_COMMON,
    ),
    'mix-q7075-mktlt50-v1': dict(
        model_band=[0.70, 0.75], market_band=[0.0, 0.50],
        earliest_kickoff_date='2026-11-08', minimum_review_date='2027-02-01',
        required_settled=100, required_matchdays=20,
        rationale=('Contrarian disagreement cell 70-75 x <50: +8.7% ROI over 157 settled picks '
                   '(45.9% hit). Model sees value the market prices below 50%.'),
        **_COMMON,
    ),
}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _base_reasons(row, now):
    """Checks shared by every rule. Outcomes are never inspected here."""
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
    elif now - quote > MAX_QUOTE_AGE:
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
    if row.get('excluded_from_models'):
        result.append('fixture_excluded_from_models')
    if row.get('match_status') != 'SCHEDULED':
        result.append('fixture_not_scheduled')
    return result


def _predicate_reasons(rule_key: str, row) -> list:
    """The frozen per-rule hypothesis predicates."""
    rule = RULES[rule_key]
    result = []
    odds = row.get('odds')
    if 'market' in rule:
        q_min = rule['q_min']
        q_score = row.get('q_score')
        if not _is_number(q_score) or not (q_min <= q_score <= 100):
            result.append(f'q_below_{q_min}_or_invalid')
        if (not _is_number(odds) or not (rule['odds_min_inclusive'] <= odds < rule['odds_max_exclusive'])):
            result.append('odds_outside_range')
    else:
        model_p = row.get('model_probability')
        m_lo, m_hi = rule['model_band']
        if not _is_number(model_p) or not (m_lo <= model_p < m_hi):
            result.append('model_probability_outside_band')
        implied = 1.0 / odds if _is_number(odds) and odds > 1 else None
        k_lo, k_hi = rule['market_band']
        if implied is None or not (k_lo <= implied < k_hi):
            result.append('market_implied_outside_band')
    return result


async def _append(db, key, kind, payload):
    db.add(PaperRuleEvent(event_key=key, kind=kind, payload=payload, sha256=digest(payload)))
    await db.flush()


async def _tick_rule(db, rule_key: str, now: datetime) -> dict:
    rule = RULES[rule_key]
    protocol_key = f'protocol:{rule_key}'
    protocol = await db.scalar(select(PaperRuleEvent).where(PaperRuleEvent.event_key == protocol_key))
    if protocol is None:
        await _append(db, protocol_key, 'protocol', {**rule, 'rule': rule_key, 'activated_at': now.isoformat()})
    else:
        expected = {k: protocol.payload.get(k) for k in rule}
        if expected != rule or digest(protocol.payload) != protocol.sha256:
            raise ValueError(f'Frozen protocol mismatch for {rule_key}: refusing to change the experiment')

    start = datetime.combine(date.fromisoformat(rule['earliest_kickoff_date']), datetime.min.time(), tzinfo=CAT)
    params = {'start': start, 'horizon': now + timedelta(days=7), 'rule': rule_key}
    if 'market' in rule:
        lateral = """LEFT JOIN LATERAL (SELECT * FROM predictions p WHERE p.match_id=m.id AND p.market=:market
                       ORDER BY p.created_at,p.id LIMIT 1) p ON TRUE"""
        params['market'] = rule['market']
    else:
        m_lo, m_hi = rule['model_band']
        k_lo, k_hi = rule['market_band']
        lateral = """LEFT JOIN LATERAL (SELECT * FROM predictions p WHERE p.match_id=m.id
                       AND p.model_probability >= :m_lo AND p.model_probability < :m_hi
                       AND p.source_decimal_odds IS NOT NULL
                       AND 1.0/p.source_decimal_odds >= :k_lo AND 1.0/p.source_decimal_odds < :k_hi
                       ORDER BY p.created_at,p.id LIMIT 1) p ON TRUE"""
        params.update(m_lo=m_lo, m_hi=m_hi, k_lo=k_lo, k_hi=k_hi)
    opportunities = (await db.execute(text(f'''
        SELECT m.id match_id, m.kickoff_at, m.status match_status, m.excluded_from_models,
               h.name home_team, a.name away_team, c.name competition,
               p.id prediction_id, p.created_at, p.decision_at, p.source_odds_at,
               p.as_of_at, p.q_score, p.source_decimal_odds odds, p.model_version,
               p.edge model_edge, p.model_probability, p.market, p.selection,
               p.feature_snapshot, p.source_odds_provenance
        FROM matches m JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
        JOIN competitions c ON c.id=m.competition_id
        {lateral}
        WHERE m.kickoff_at >= :start AND m.kickoff_at <= :horizon
          AND NOT EXISTS (SELECT 1 FROM paper_rule_events e WHERE e.event_key='decision:' || :rule || ':' || m.id::text)
        ORDER BY m.kickoff_at, m.id
    '''), params)).mappings().all()

    captured = qualified = 0
    for row in opportunities:
        captured_at = await db.scalar(select(text('clock_timestamp()')))
        if row['prediction_id'] is None and row['kickoff_at'] > captured_at:
            continue
        payload = json.loads(json.dumps(dict(row), default=str))
        rejected = _base_reasons(payload, captured_at) + _predicate_reasons(rule_key, payload)
        payload.update(captured_at=captured_at.isoformat(), rule=rule_key, rule_version=rule_key,
                       qualified=not rejected, reasons=rejected,
                       day=row['kickoff_at'].astimezone(CAT).date().isoformat())
        await _append(db, f'decision:{rule_key}:{row["match_id"]}', 'decision', payload)
        captured += 1
        qualified += not rejected

    # Generic JSON has no .astext comparator; filter by rule in Python like
    # the sweet-spot tracker does. Order is preserved for settlement latest-wins.
    decisions = [e for e in (await db.execute(select(PaperRuleEvent).where(
        PaperRuleEvent.kind == 'decision'))).scalars().all() if e.payload.get('rule') == rule_key]
    settlements = [e for e in (await db.execute(select(PaperRuleEvent).where(
        PaperRuleEvent.kind == 'settlement').order_by(PaperRuleEvent.id))).scalars().all()
        if e.payload.get('rule') == rule_key]
    latest = {r.payload['match_id']: r.payload for r in settlements}
    ids = [r.payload['match_id'] for r in decisions if r.payload['qualified']]
    matches = {}
    if ids:
        matches = {m.id: m for m in (await db.execute(select(Match).where(Match.id.in_(ids)))).scalars().all()}
    settled = 0
    for event in decisions:
        p = event.payload
        if not p['qualified'] or p['match_id'] not in matches:
            continue
        m = matches[p['match_id']]
        result = 'pending'
        if m.status.value.upper() == 'FINISHED' and m.home_goals is not None and m.away_goals is not None:
            from app.services.settlement import evaluate_selection
            from app.models import SelectionResult
            try:
                outcome = evaluate_selection(p.get('selection'), m.home_goals, m.away_goals)
            except ValueError:
                try:
                    outcome = evaluate_selection(p.get('market'), m.home_goals, m.away_goals)
                except ValueError:
                    outcome = SelectionResult.VOID
            result = {SelectionResult.WON: 'won', SelectionResult.LOST: 'lost'}.get(outcome, 'pending')
        body = dict(rule=rule_key, match_id=m.id, status=m.status.value,
                    home_goals=m.home_goals, away_goals=m.away_goals,
                    result=result, profit=(p['odds'] - 1 if result == 'won' else -1 if result == 'lost' else None))
        prior = latest.get(m.id)
        if prior and all(prior.get(k) == v for k, v in body.items()):
            continue
        if not prior and result == 'pending':
            continue
        revision = (prior or {}).get('revision', 0) + 1
        body.update(revision=revision, observed_at=now.isoformat())
        await _append(db, f'settlement:{rule_key}:{m.id}:{revision}', 'settlement', body)
        settled += 1
    slot = int(now.timestamp()) // 300
    if not await db.scalar(select(PaperRuleEvent.id).where(PaperRuleEvent.event_key == f'run:{rule_key}:{slot}')):
        await _append(db, f'run:{rule_key}:{slot}', 'run', dict(
            rule=rule_key, at=now.isoformat(), day=now.astimezone(CAT).date().isoformat(),
            captured=captured, qualified=qualified, settlement_events=settled))
    return dict(rule=rule_key, captured=captured, qualified=qualified, settlement_events=settled, mode='paper_only')


async def tick(db):
    await db.execute(text(f'SELECT pg_advisory_xact_lock({ADVISORY_LOCK_ID})'))
    now = await db.scalar(select(text('clock_timestamp()')))
    results = []
    for rule_key in RULES:
        results.append(await _tick_rule(db, rule_key, now))
    return {'rules': results, 'mode': 'paper_only'}


def build_report(events, now, rule_key: str) -> dict:
    rule = RULES[rule_key]
    own = [e for e in events if e.payload.get('rule') == rule_key or e.event_key == f'protocol:{rule_key}']
    for e in own:
        if digest(e.payload) != e.sha256:
            raise ValueError(f'Ledger integrity check failed for {rule_key}')
    protocols = [e.payload for e in own if e.kind == 'protocol']
    decisions = [e.payload for e in own if e.kind == 'decision']
    latest = {e.payload['match_id']: e.payload for e in own if e.kind == 'settlement'}
    runs = [e.payload for e in own if e.kind == 'run']
    picks = [{**p, **latest.get(p['match_id'], {'result': 'pending', 'profit': None})}
             for p in decisions if p['qualified']]
    summary = cohort_metrics(picks)
    by_day = defaultdict(list)
    for p in picks:
        if p['result'] != 'pending':
            by_day[p['day']].append(p)
    today = now.astimezone(CAT).date()
    first = date.fromisoformat(rule['earliest_kickoff_date'])
    run_days = {r['day'] for r in runs}
    days = []
    for i in range(max(0, (today - first).days + 1)):
        day = (first + timedelta(days=i)).isoformat()
        days.append(dict(day=day, collection_observed=day in run_days, **cohort_metrics([p for p in picks if p['day'] == day])))
    health = ('not_started' if not runs
              else 'current' if now - parse(runs[-1]['at']) <= timedelta(minutes=15) else 'stale')
    return dict(
        rule=rule_key, mode='paper_only', promotion_ready=False,
        protocol=protocols[0] if protocols else {**rule, 'rule': rule_key},
        collection_status=health, last_run=runs[-1] if runs else None,
        summary=summary, rationale=rule['rationale'],
        review_due=(today >= date.fromisoformat(rule['minimum_review_date'])
                    and summary['settled'] >= rule['required_settled']
                    and summary['matchdays'] >= rule['required_matchdays']),
        review_requirements=dict(minimum_review_date=rule['minimum_review_date'],
                                 required_settled=rule['required_settled'],
                                 required_matchdays=rule['required_matchdays']),
        exclusions=dict(Counter(r for p in decisions for r in p['reasons'])),
        observed_opportunities=len(decisions),
        missing_results=sum(p['result'] == 'pending' and parse(p['kickoff_at']) < now - timedelta(hours=6) for p in picks),
        days=days,
        picks=sorted(picks, key=lambda p: p['kickoff_at'], reverse=True),
        limitations=[
            'Coverage includes fixtures known to this database, not all football fixtures.',
            'Historical rationale numbers motivated the rule but play no part in its prospective ledger.',
            'Postponed/cancelled picks remain unresolved, not assumed refunded.',
            'Simulated entry odds; execution and actual costs unverified.',
        ],
    )


async def rule_report(db, rule_key: str) -> dict:
    events = (await db.execute(select(PaperRuleEvent).order_by(PaperRuleEvent.id))).scalars().all()
    return build_report(events, datetime.now(timezone.utc), rule_key)


async def list_summaries(db) -> list:
    events = (await db.execute(select(PaperRuleEvent).order_by(PaperRuleEvent.id))).scalars().all()
    now = datetime.now(timezone.utc)
    summaries = []
    for rule_key, rule in RULES.items():
        report = build_report(events, now, rule_key)
        summaries.append(dict(
            rule=rule_key,
            mode='paper_only',
            hypothesis='market' if 'market' in rule else 'band_mix',
            market=rule.get('market'),
            rationale=rule['rationale'],
            collection_status=report['collection_status'],
            summary=report['summary'],
            review_due=report['review_due'],
            observed_opportunities=report['observed_opportunities'],
        ))
    return summaries
