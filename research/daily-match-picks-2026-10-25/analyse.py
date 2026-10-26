"""Replay Daily Match Picks as-of each CAT calendar date, then sweep filters."""
import collections,datetime as dt,hashlib,itertools,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
source=json.loads((ROOT/'snapshot.json').read_text())
raw=source['rows']
parse=dt.datetime.fromisoformat
dates=[f'2026-10-{day:02d}' for day in range(1,26)]
MIN_Q=70; MIN_ODDS=2; MAX_ODDS=3; MIN_HIT=.50; MIN_ROI=.30; MAX_QUOTE_AGE=dt.timedelta(hours=3); MAX_INFO_AGE=dt.timedelta(hours=2)
def valid(r):
    try:
        kickoff=parse(r['kickoff_at']); quote=parse(r['source_odds_at']); info=parse(r['decision_at'] or r['as_of_at'] or r['created_at'])
        provenance=r['source_odds_provenance'] or {}
        return bool(r['source_odds_id'] and provenance.get('bookmaker') and provenance.get('is_fallback') is False
          and r['odds'] is not None and MIN_ODDS<=r['odds']<MAX_ODDS
          and r['q_score']>=MIN_Q
          and info<kickoff and quote<kickoff and quote<=info
          and dt.timedelta(0)<=info-quote<=MAX_INFO_AGE
          and info-quote<=MAX_QUOTE_AGE)
    except (TypeError,ValueError): return False
for r in raw:
    if r['outcome']=='void': continue
    r['valid']=valid(r)

def summarize(rs):
    decided=[r for r in rs if r['outcome'] in ('won','lost')]
    wins=sum(r['outcome']=='won' for r in decided); n=len(decided)
    pnl=sum(r['odds']-1 if r['outcome']=='won' else -1 for r in decided)
    return {'selections':len(rs),'n':n,'matches':len({r['match_id'] for r in decided}),
      'days':len({r['day'] for r in decided}),'wins':wins,'losses':n-wins,
      'hit':100*wins/n if n else None,'profit':pnl,'roi':100*pnl/n if n else None,
      'mean_odds':sum(r['odds'] for r in decided)/n if n else None}

daily=[]; picks=[]; qualified_by_day={}; histories_by_day={}
for day in dates:
    # Mirrors the API: most recent valid prediction per unique match/market/selection,
    # considering completed fixtures strictly before the target CAT calendar date.
    hist={}
    for r in raw:
        if r['day']>=day or r['status']!='FINISHED' or r['outcome'] not in ('won','lost') or not r['valid']: continue
        key=(r['match_id'],r['market'],r['selection'])
        if key not in hist: hist[key]=r
    grouped=collections.defaultdict(list)
    for r in hist.values(): grouped[r['market']].append(r)
    market_stats={}
    for market,items in grouped.items():
        s=summarize(items)
        s['market']=market
        s['qualifies']=bool(s['hit'] is not None and s['hit']/100>MIN_HIT and s['roi'] is not None and s['roi']/100>MIN_ROI)
        market_stats[market]=s
    qualified={m for m,s in market_stats.items() if s['qualifies']}
    qualified_by_day[day]=sorted(qualified)
    histories_by_day[day]=market_stats
    today={}
    for r in raw: # raw is newest-first, as in the daily service's query
        if r['day']!=day or r['market'] not in qualified or r['status'] not in {'SCHEDULED','LIVE','FINISHED','POSTPONED','CANCELLED'}: continue
        key=(r['match_id'],r['market'],r['selection'])
        if key in today: continue
        if not valid(r): continue
        today[key]=r
    for r in today.values(): picks.append(r)
    daily.append({'day':day,'qualified_markets':sorted(qualified),'historical_market_count':len(market_stats),
      'candidate_selections':len(today),'candidate_matches':len({r['match_id'] for r in today.values()}),
      'settled':summarize(list(today.values()))})

settled=[r for r in picks if r['outcome'] in ('won','lost')]
pool=summarize(settled)
q_lows=[70,75,80,85,90]
q_highs=[None,80,85,90,95]
odds_lows=[None,2.1,2.25,2.5,2.75]
odds_highs=[None,2.25,2.5,2.75,3.0]
markets=sorted({r['market'] for r in settled})
market_options=[('All qualifying markets',None)]+[(m,m) for m in markets]
def evaluate(row,market,ql,qh,ol,oh):
    return (market is None or row['market']==market) and row['q_score']>=ql and (qh is None or row['q_score']<=qh) and (ol is None or row['odds']>=ol) and (oh is None or row['odds']<=oh)

combinations=[]
for market_name,market in market_options:
 for ql,qh,ol,oh in itertools.product(q_lows,q_highs,odds_lows,odds_highs):
    if qh is not None and qh<ql or oh is not None and ol is not None and oh<=ol: continue
    cohort=[r for r in settled if evaluate(r,market,ql,qh,ol,oh)]
    if not cohort: continue
    s=summarize(cohort)
    q_label=f'Q {ql}+' if qh is None else f'Q {ql}–{qh}'
    odds_label=('odds '+(f'≥{ol:g}' if ol is not None else '')+
      ('–' if ol is not None and oh is not None else '')+(f'≤{oh:g}' if oh is not None else ''))
    s.update({'filter':market_name+f'; {q_label}'+(f'; {odds_label}' if ol is not None or oh is not None else ''),
      'market':market_name,'q_min':ql,'q_max':qh,'odds_min':ol,'odds_max':oh})
    s['early']=summarize([r for r in cohort if r['day']<='2026-10-19'])
    s['late']=summarize([r for r in cohort if r['day']>='2026-10-20'])
    combinations.append(s)
combinations.sort(key=lambda x:(-(x['roi'] or -math.inf),-x['n'],x['filter']))

def bootstrap(cohort,reps=5000):
    groups=collections.defaultdict(lambda:[0.,0])
    for r in cohort:
        groups[r['match_id']][0]+=r['odds']-1 if r['outcome']=='won' else -1
        groups[r['match_id']][1]+=1
    if len(groups)<2:return None
    arr=np.array(list(groups.values())); rng=np.random.default_rng(20261025)
    sample=arr[rng.integers(0,len(arr),size=(reps,len(arr)))].sum(axis=1)
    return [round(float(x),2) for x in np.percentile(100*sample[:,0]/sample[:,1],[2.5,97.5])]

by_market=[]
for market in markets:
 cohort=[r for r in settled if r['market']==market]; s=summarize(cohort)
 by_market.append({'market':market,**s,'roi_cluster_ci95':bootstrap(cohort)})
by_market.sort(key=lambda r:-(r['roi'] if r['roi'] is not None else -math.inf))
qualified_union=sorted({m for ms in qualified_by_day.values() for m in ms})
raw_duplicate_groups=collections.defaultdict(int)
for r in raw:
 if r['day'] in dates: raw_duplicate_groups[(r['day'],r['match_id'],r['market'],r['selection'])]+=1
duplicate_rows=sum(n-1 for n in raw_duplicate_groups.values() if n>1)
eligible_day={r['day'] for r in picks}
audit={'captured_at':source['captured_at'],'snapshot_sha256':hashlib.sha256((ROOT/'snapshot.json').read_bytes()).hexdigest(),
 'date_from':dates[0],'date_to':dates[-1],'timezone':'Africa/Blantyre','raw_rows':len(raw),
 'duplicate_prediction_rows_in_extract':duplicate_rows,'candidate_picks':len(picks),'settled_candidates':len(settled),
 'settled_metrics':pool,'void_candidates':sum(r['outcome']=='void' for r in picks),
 'unsettled_candidates':sum(r['outcome'] is None for r in picks), 'source_row_days':len({r['day'] for r in raw}),
 'picked_days':len(eligible_day),'qualified_markets_union':qualified_union,
 'formula':{'history_q_min':MIN_Q,'history_odds_min':MIN_ODDS,'history_odds_max_exclusive':MAX_ODDS,
 'min_info_fresh_hours':2,'min_quote_age_hours':3,'market_hit_strictly_above_percent':50,'market_roi_strictly_above_percent':30,
 'daily_min_q':MIN_Q,'daily_odds_min':MIN_ODDS,'daily_odds_max_exclusive':MAX_ODDS},
 'market_only':by_market,'top_raw':combinations[:20],
 'top_supported':[r for r in combinations if r['n']>=30 and r['matches']>=25 and r['days']>=5][:20],
 'top_100':[r for r in combinations if r['n']>=100][:12],
 'top_early':[r for r in sorted(combinations,key=lambda x:(-(x['early']['roi'] or -math.inf),-x['early']['n'])) if r['early']['n']>=30 and r['early']['matches']>=25 and r['early']['days']>=5][:15],
 'daily':daily,'baseline_ci':bootstrap(settled)}
audit['top_supported_ci95']=[]
for combo in audit['top_supported'][:8]:
 cohort=[r for r in settled if evaluate(r,combo['market'] if combo['market']!='All qualifying markets' else None,
   combo['q_min'],combo['q_max'],combo['odds_min'],combo['odds_max'])]
 audit['top_supported_ci95'].append({'filter':combo['filter'],'roi_cluster_ci95':bootstrap(cohort)})
(ROOT/'summary.json').write_text(json.dumps(audit,indent=2))
(ROOT/'combinations.json').write_text(json.dumps(combinations,indent=2))
(ROOT/'daily_picks.json').write_text(json.dumps(picks,indent=2))
print(json.dumps({k:audit[k] for k in ('captured_at','raw_rows','duplicate_prediction_rows_in_extract','candidate_picks','settled_candidates','settled_metrics','void_candidates','unsettled_candidates','picked_days','qualified_markets_union')},indent=2))
print('MARKETS')
for r in by_market: print(r['market'],r['n'],r['wins'],r['losses'],round(r['hit'],1) if r['hit'] else None,round(r['roi'],1) if r['roi'] is not None else None,r['roi_cluster_ci95'])
print('TOP SAMPLE')
for r in audit['top_supported'][:12]: print(r['filter'],r['n'],r['wins'],r['losses'],round(r['hit'],1),round(r['roi'],1),round(r['early']['roi'],1) if r['early']['roi'] is not None else None,round(r['late']['roi'],1) if r['late']['roi'] is not None else None)
