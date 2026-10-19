"""Read-only singles audit. Run from repository root; outputs are never overwritten.

Uses only Python's standard library locally and the existing Docker backend's
SQLAlchemy runtime for a single read-only snapshot. No application policy changes.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess

CAT = timezone(timedelta(hours=2))
CUTOFF = '2026-10-11'  # Retain the already-examined historical split.
EXPORT = '''
import asyncio, json
from sqlalchemy import text
from app.database import AsyncSessionLocal, engine
async def main():
    engine.echo = False
    async with AsyncSessionLocal() as db:
        await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        rows = (await db.execute(text("""
          SELECT p.id, p.match_id, p.market, p.selection, p.model_version,
            p.q_score, p.q_grade, p.edge, p.model_probability,
            p.source_decimal_odds odds, p.source_odds_at, p.created_at,
            p.decision_at, p.as_of_at, p.source_odds_provenance,
            p.feature_snapshot, p.recommendation_status,
            m.kickoff_at, m.status, m.home_goals, m.away_goals,
            c.name competition, h.name home_team, a.name away_team
          FROM predictions p JOIN matches m ON m.id=p.match_id
          JOIN competitions c ON c.id=m.competition_id
          JOIN teams h ON h.id=m.home_team_id JOIN teams a ON a.id=m.away_team_id
          WHERE NOT m.excluded_from_models
          ORDER BY p.created_at, p.id
        """))).mappings().all()
        print(json.dumps([dict(r) for r in rows], default=str))
asyncio.run(main())
'''


def dt(value):
    return datetime.fromisoformat(value) if value else None


def outcome(row):
    if row['status'] != 'FINISHED':
        return None  # Do not assume postponed/cancelled means bookmaker refund.
    h, a, market = row['home_goals'], row['away_goals'], row['market']
    if h is None or a is None:
        return None
    if market.startswith(('over_', 'under_')):
        threshold = float(market.split('_', 1)[1])
        if threshold % 1 != .5:
            raise ValueError('Only half-goal totals supported')
        won = h + a > threshold if market.startswith('over_') else h + a < threshold
    elif market in ('dnb_home', 'dnb_away'):
        if h == a:
            return 0
        won = h > a if market == 'dnb_home' else a > h
    else:
        won = {'home_win': h > a, 'away_win': a > h, 'draw': h == a,
               'btts_yes': h > 0 and a > 0, 'btts_no': h == 0 or a == 0,
               'double_chance_1x': h >= a, 'double_chance_x2': a >= h,
               'double_chance_12': h != a}.get(market)
        if won is None:
            raise ValueError('Unsupported market: ' + market)
    return 1 if won else -1


def prepare(raw, as_at):
    seen, eligible, excluded = set(), [], Counter()
    for row in sorted(raw, key=lambda r: (r['created_at'], r['id'])):
        r = dict(row)
        key = r['match_id'], r['market'], r['selection']
        if key in seen:
            excluded['later_repeat'] += 1
            continue
        seen.add(key)  # Never substitute a later favourable quote for the first one.
        odds = r['odds']
        created, kickoff = dt(r['created_at']), dt(r['kickoff_at'])
        decision, quote = dt(r['decision_at']) or created, dt(r['source_odds_at'])
        if not odds or odds <= 1:
            excluded['missing_or_invalid_odds'] += 1
        elif r['as_of_at'] or not quote or not (quote <= decision < kickoff and created < kickoff):
            excluded['timing_or_replay'] += 1
        elif (r['source_odds_provenance'] or {}).get('is_fallback'):
            excluded['fallback_odds'] += 1
        elif kickoff.astimezone(CAT).date() >= as_at.astimezone(CAT).date():
            excluded['current_or_future_day'] += 1
        elif outcome(r) is None:
            excluded['no_final_result'] += 1
        else:
            r['result'] = outcome(r)
            r['profit'] = odds - 1 if r['result'] == 1 else r['result']
            r['day'] = kickoff.astimezone(CAT).date().isoformat()
            r['quote_age_hours'] = (decision - quote).total_seconds() / 3600
            r['complete_context'] = bool(r['feature_snapshot']) and bool(r['decision_at'])
            eligible.append(r)
    assert sum(excluded.values()) + len(eligible) == len(raw)
    return eligible, excluded


def stats(rows):
    n = len(rows)
    w = sum(r['result'] == 1 for r in rows)
    losses = sum(r['result'] == -1 for r in rows)
    p = sum(r['profit'] for r in rows)
    return dict(n=n, matches=len({r['match_id'] for r in rows}), wins=w, losses=losses,
                voids=n-w-losses, days=len({r['day'] for r in rows}),
                hit=100*w/(w+losses) if w+losses else None,
                roi=100*p/n if n else None, profit=p,
                haircut_roi=100*sum((r['odds']-1)*.95 if r['result']==1 else r['result'] for r in rows)/n if n else None)


def split_stats(rows):
    return {'earlier': stats([r for r in rows if r['day'] < CUTOFF]),
            'later': stats([r for r in rows if r['day'] >= CUTOFF])}


def uncertainty(rows):
    if not rows:
        return None
    groups = defaultdict(list)
    for r in rows:
        groups[r['day']].append(r)
    clusters = [(sum(r['profit'] for r in v), len(v)) for v in groups.values()]
    rng = random.Random(20261018)
    samples = []
    for _ in range(5000):
        selected = rng.choices(clusters, k=len(clusters))
        samples.append(100*sum(p for p, n in selected)/sum(n for p, n in selected))
    samples.sort()
    return [samples[124], samples[4874]]


def candidate(r):
    return r['market']=='away_win' and r['q_score']>=65 and 1.8<=r['odds']<3 and r['quote_age_hours']<=3


def pct(value):
    return 'n/a' if value is None else f'{value:+.2f}%'


def table(records):
    lines = ['| Group | Earlier N | Earlier ROI | Later N | Later win rate | Later ROI |',
             '|---|---:|---:|---:|---:|---:|']
    for label, s in records:
        a, b = s['earlier'], s['later']
        lines.append(f"| {label} | {a['n']} | {pct(a['roi'])} | {b['n']} | {pct(b['hit'])} | {pct(b['roi'])} |")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Replay an existing raw.json instead of exporting')
    parser.add_argument('--as-at', help='ISO UTC timestamp, required when replaying a snapshot')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.snapshot and not args.as_at:
        parser.error('--snapshot requires the original --as-at timestamp')
    as_at = dt(args.as_at) if args.as_at else datetime.now(timezone.utc)
    dest = args.output or Path('research') / ('sweet-spot-' + as_at.strftime('%Y%m%dT%H%M%SZ'))
    dest.mkdir(parents=True, exist_ok=False)
    if args.snapshot:
        raw_text = args.snapshot.read_text(encoding='utf-8')
    else:
        proc = subprocess.run(['docker', 'exec', '-i', 'qwantej-backend-1', 'python', '-'],
                              input=EXPORT, text=True, encoding='utf-8', capture_output=True, check=True)
        raw_text = proc.stdout
    raw = json.loads(raw_text)
    (dest/'raw.json').write_text(raw_text, encoding='utf-8')
    rows, excluded = prepare(raw, as_at)
    markets = sorted({r['market'] for r in rows})
    market_table = [(m, split_stats([r for r in rows if r['market']==m])) for m in markets]
    # Broad, fixed bins. No optimisation of boundaries against these results.
    bands = [(1, 1.5), (1.5, 2), (2, 3), (3, float('inf'))]
    comparisons = []
    for m in markets:
        for lo, hi in bands:
            selected = [r for r in rows if r['market']==m and lo<=r['odds']<hi]
            comparisons.append((f'{m}; odds [{lo}, {hi})', split_stats(selected)))
    picks = [r for r in rows if candidate(r)]
    later = [r for r in picks if r['day']>=CUTOFF]
    q_table = [(f'away_win; Q [{lo}, {hi})', split_stats([r for r in rows if r['market']=='away_win' and lo<=r['q_score']<hi]))
               for lo, hi in [(0, 50), (50, 60), (60, 70), (70, 80), (80, 101)]]
    sensitivity = []
    for q, upper in [(60, 3), (65, 3), (70, 3), (65, 4)]:
        chosen = [r for r in rows if r['market']=='away_win' and r['q_score']>=q and 1.8<=r['odds']<upper and r['quote_age_hours']<=3]
        sensitivity.append((f'away_win; Q>={q}; odds [1.8,{upper}); quote <=3h', split_stats(chosen)))
    calibration = []
    for m in markets:
        for lo in range(0, 100, 10):
            rs = [r for r in rows if r['market']==m and r['day']>=CUTOFF and r['result']!=0 and lo/100<=r['model_probability']<(lo+10)/100 + (1e-12 if lo==90 else 0)]
            if rs:
                calibration.append(dict(market=m, probability_band=f'{lo}-{lo+10}%', n=len(rs),
                    predicted_pct=100*sum(r['model_probability'] for r in rs)/len(rs), observed_pct=100*sum(r['result']==1 for r in rs)/len(rs)))
    result = dict(as_at=as_at.isoformat(), source_sha256=hashlib.sha256(raw_text.encode()).hexdigest(),
                  raw_rows=len(raw), exclusions=dict(excluded), eligible=stats(rows),
                  date_range=[min(r['day'] for r in rows), max(r['day'] for r in rows)] if rows else [],
                  complete_context_count=sum(r['complete_context'] for r in rows),
                  missing_provider_count=sum(not (r['source_odds_provenance'] or {}).get('source_type') for r in rows),
                  candidate=split_stats(picks), candidate_later_interval=uncertainty(later),
                  candidate_complete_context=split_stats([r for r in picks if r['complete_context']]),
                  candidate_by_day={d:stats([r for r in picks if r['day']==d]) for d in sorted({r['day'] for r in picks})},
                  candidate_by_competition={c:split_stats([r for r in picks if r['competition']==c]) for c in sorted({r['competition'] for r in picks})},
                  candidate_by_model={v:split_stats([r for r in picks if r['model_version']==v]) for v in sorted({r['model_version'] for r in picks})},
                  market_comparison=dict(market_table), market_odds_comparison=dict(comparisons),
                  q_comparison=dict(q_table), sensitivity=dict(sensitivity), calibration=calibration)
    for name, content in [('analysis.json', result), ('candidate-picks.json', picks)]:
        (dest/name).write_text(json.dumps(content, indent=2), encoding='utf-8')
    protocol = dict(rule_version='away-q65-odds180-300-v1', frozen_at=as_at.isoformat(),
        status='PAPER ONLY; prospective collection is not scheduled by this script',
        earliest_kickoff_date=(as_at.astimezone(CAT).date()+timedelta(days=1)).isoformat(),
        market='away_win', q_min=65, odds_min_inclusive=1.8, odds_max_exclusive=3,
        maximum_quote_age_hours=3, minimum_edge=None, stake_units=1,
        selection='First stored prediction per match/market/selection; never substitute later captures',
        required_evidence=['Pre-kickoff decision and capture', 'Quote <= decision; no fallback or replay',
                           'Persist original features, model version, source and rule version',
                           'Capture qualifying and excluded opportunities before kickoff',
                           'Report missing decisions/results and changed model regimes separately'],
        minimum_review_date=(as_at.astimezone(CAT).date()+timedelta(days=90)).isoformat(),
        review_requires={'settled_fixtures':300, 'distinct_matchdays':30},
        review_policy='Review only after date and both counts are met; these are planning floors, not proof. No interim rule tuning. Report net ROI, day-cluster uncertainty, drawdown, coverage, and model/league concentration. No automatic promotion to real-money use.')
    (dest/'paper-protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    report = f'''# Match and market sweet-spot audit

**Finding: no validated sweet spot.** Away win / Q >=65 / odds [1.80,3.00) / quote age <=3h remains a historical paper-test hypothesis. This audit does not discover an independently validated new policy.

Snapshot: {as_at.isoformat()}. Completed CAT days only: {result['date_range']}.
Raw rows: {len(raw):,}. Eligible market observations: {len(rows):,}; distinct fixtures: {result['eligible']['matches']:,}.

## Candidate

{table([('Frozen historical candidate', result['candidate']), ('Candidate with explicit decision + stored features', result['candidate_complete_context'])])}

Later ROI day-cluster descriptive 95% interval: {result['candidate_later_interval']}. Later ROI with 5% reduction of winnings: {pct(result['candidate']['later']['haircut_roi'])}. This haircut is a scenario, not measured execution cost.

## What the comparison means

- Earlier = before {CUTOFF}; later = {CUTOFF} onwards, excluding today's incomplete day. These historical periods have already been examined in the existing rejection-ledger study. Neither is an untouched holdout. No new ranking or tuning on later results.
- First stored prediction per match/market/selection only; no replacing missing prices with later prices. Prices, decisions and captures must precede kickoff; quote <= decision. The database creation timestamp may represent transaction start and precede the decision timestamp. Replay/fallback odds are excluded. Read-only database transaction; source hash in analysis.json.
- Flat one-unit singles, using recorded entry odds. Wins pay odds minus one, losses minus one, DNB draws refund. Postponed/cancelled games are excluded, not assumed refunded. No accumulators. Counts across markets overlap and must not be added as independent matches.
- Only {result['complete_context_count']:,}/{len(rows):,} eligible observations have both explicit decision timestamps and nonempty stored features. Missing provider labels: {result['missing_provider_count']:,}. Timestamp checks do not certify upstream training data, feature completeness, bookmaker execution, or recovered legacy-data integrity.
- Match conditions here are limited to recorded pre-match Q, market, price, quote age, league and model version. Historical injuries, lineups or form cannot be recreated safely from today's values. Q is not a probability.
- Candidate uncertainty resamples whole matchdays, 5,000 draws, fixed seed. Few days, historical search bias and cross-day dependence limit interpretation; it is not a guarantee or a multiple-testing-adjusted interval.

## Markets

{table(market_table)}

## Market and odds bands

Fixed broad bins, descriptive only. Small cells are not recommendations.

{table(comparisons)}

## Quality bands within away wins

{table(q_table)}

## Sensitivity of the existing hypothesis

{table(sensitivity)}

## Calibration and fixture evidence

analysis.json contains later-period predicted versus observed win rates in fixed 10-point probability bins, separately by market; per-day, per-league and model-version candidate results; and exclusion counts. Small bins cannot establish calibration. candidate-picks.json contains the exact fixture names, input timestamps, prices, scores and outcomes for independent review.

## Frozen future test

paper-protocol.json records the fixed rule and start boundary ({protocol['earliest_kickoff_date']}, CAT). The planned review is no earlier than {protocol['minimum_review_date']} and only after 300 settled fixtures across 30 matchdays. Those are planning floors, not evidence of profitability. Do not change thresholds in response to interim results. No automated collection or application policy was changed by this audit.

Exclusions: {json.dumps(dict(excluded), sort_keys=True)}.

## Reproduction

Run `rtk proxy python backend/scripts/sweet_spot_audit.py` from the repository root for a fresh read-only snapshot. To reproduce this exact audit, use `--snapshot <this-folder>/raw.json --as-at {as_at.isoformat()} --output <new-folder>`. Output folders must not already exist.
'''
    (dest/'REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({'output':str(dest.resolve()), **{k:result[k] for k in ['raw_rows','eligible','date_range','complete_context_count','candidate','candidate_later_interval']}}, indent=2))


if __name__ == '__main__':
    main()
