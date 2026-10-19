"""Reproducible exploratory singles simulation; no database writes."""
import json, math, csv, sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import numpy as np

ROOT = Path('research/rejection-ledger-2026-10-18')
raw = json.loads((ROOT/'predictions.json').read_text(encoding='utf-8-sig'))
ledger = json.loads((ROOT/'ledger.json').read_text(encoding='utf-8-sig'))
lookup = {r['id']: r for r in ledger}
if '--ledger' in sys.argv:
    raw=[{**r,'edge':lookup[r['id']]['ledger_edge']} for r in raw if r['id'] in lookup]
    ROOT=ROOT/'current-ledger'; ROOT.mkdir(exist_ok=True)
def dt(v): return datetime.fromisoformat(v) if v else None
def outcome(r):
    h,a=r['home_goals'],r['away_goals']; m=r['market']
    if r['status'] in ('POSTPONED','CANCELLED'): return 0
    if r['status']!='FINISHED' or h is None or a is None: return None
    if m.startswith('over_'): w=h+a>float(m[5:])
    elif m.startswith('under_'): w=h+a<float(m[6:])
    elif m=='btts_yes': w=h>0 and a>0
    elif m=='btts_no': w=h==0 or a==0
    elif m=='home_win': w=h>a
    elif m=='away_win': w=a>h
    elif m=='draw': w=h==a
    elif m=='double_chance_1x': w=h>=a
    elif m=='double_chance_x2': w=a>=h
    elif m=='dnb_home': return 0 if h==a else (1 if h>a else -1)
    elif m=='dnb_away': return 0 if h==a else (1 if a>h else -1)
    else: raise ValueError(m)
    return 1 if w else -1

excluded=Counter(); rows=[]; seen=set()
for r in raw:
    key=(r['match_id'],r['market'])
    if key in seen: excluded['later_repeat']+=1; continue
    seen.add(key)
    if not r['odds'] or r['odds']<=1: excluded['missing_odds']+=1; continue
    decision=dt(r['decision_at']) or dt(r['created_at']); quote=dt(r['source_odds_at']); kick=dt(r['kickoff_at'])
    if dt(r['created_at'])>=kick or decision>=kick or not quote or quote>decision or quote>=kick or r['as_of_at']:
        excluded['timing_or_replay']+=1; continue
    if (r['source_odds_provenance'] or {}).get('is_fallback'): excluded['fallback']+=1; continue
    result=outcome(r)
    if result is None: excluded['unresolved']+=1; continue
    r.update(result=result, profit=(r['odds']-1 if result==1 else result), day=(kick+timedelta(hours=2)).date().isoformat(), quote_age=(decision-quote).total_seconds()/3600)
    rows.append(r)

days=sorted({r['day'] for r in rows}); cutoff=days[int(len(days)*.7)]
# Fixed pre-outcome priority: higher Q, then earlier capture, then prediction ID.
rows.sort(key=lambda r:(-r['q_score'],r['created_at'],r['id']))
def unique(rs):
    used=set(); out=[]
    for r in rs:
        if r['match_id'] not in used: used.add(r['match_id']); out.append(r)
    return out
def stats(rs, bootstrap=False):
    n=len(rs); w=sum(r['result']==1 for r in rs); l=sum(r['result']==-1 for r in rs); v=n-w-l
    p=sum(r['profit'] for r in rs); resolved=w+l
    s=dict(n=n,matches=len({r['match_id'] for r in rs}),wins=w,losses=l,voids=v,hit=100*w/resolved if resolved else None,roi=100*p/n if n else None,profit=p,days=len({r['day'] for r in rs}),avg_odds=sum(r['odds'] for r in rs)/n if n else None)
    if bootstrap and n:
        ds=sorted({r['day'] for r in rs}); profits=np.array([sum(r['profit'] for r in rs if r['day']==d) for d in ds]); counts=np.array([sum(r['day']==d for r in rs) for d in ds]); ix=np.random.default_rng(20261018).integers(0,len(ds),(5000,len(ds))); b=100*profits[ix].sum(1)/counts[ix].sum(1); s['roi_day_bootstrap_95']=np.percentile(b,[2.5,97.5]).tolist()
        seq=sorted(rs,key=lambda r:(r['kickoff_at'],r['id'])); curve=np.r_[0,np.cumsum([r['profit'] for r in seq])]; s['max_drawdown_units']=float(np.max(np.maximum.accumulate(curve)-curve)); streak=longest=0
        for r in seq:
            streak=streak+1 if r['result']==-1 else (0 if r['result']==1 else streak); longest=max(streak,longest)
        s['longest_loss_streak']=longest
        s['roi_5pct_winnings_haircut']=100*sum((r['odds']-1)*.95 if r['result']==1 else r['result'] for r in rs)/n
    return s

result=dict(raw_rows=len(raw),unique_match_markets=len(seen),ledger_rows=len(ledger),ledger_reasons=Counter(reason for r in ledger for reason in r['reasons']),excluded=excluded,eligible=len(rows),date_range=[days[0],days[-1]],test_start=cutoff,all_market_baseline=stats(rows),one_match_baseline=stats(unique(rows),True),markets={m:stats([r for r in rows if r['market']==m]) for m in sorted({r['market'] for r in rows})})
records=[]; tested=0
for market in ['ALL']+sorted({r['market'] for r in rows}):
 for q in [0,40,50,60,65,70,75,80,85]:
  for lo,hi in [(1.01,100),(1.2,1.6),(1.4,2),(1.5,2.5),(1.8,3),(2,4),(3,10)]:
   base=[r for r in rows if (market=='ALL' or r['market']==market) and r['q_score']>=q and lo<=r['odds']<hi]
   for edge in [None,-.1,-.05,0,.02,.05,.1,.15]:
    for age in [3,24,1e9]:
     tested+=1
     chosen=unique([r for r in base if (edge is None or r['edge'] is not None and r['edge']>=edge) and r['quote_age']<=age])
     train=[r for r in chosen if r['day']<cutoff]; test=[r for r in chosen if r['day']>=cutoff]
     if len(train)<40: continue
     records.append(dict(market=market,q_min=q,odds_min=lo,odds_max=hi,edge_min=edge,quote_age_max=age,train=stats(train),test=stats(test)))
records.sort(key=lambda r:(r['train']['roi'],-r['q_min']),reverse=True)
result['grid_tested']=tested; result['grid_with_40_train']=len(records)
result['top_train']=records[:15]
result['both_positive_40train_20test']=[r for r in records if r['train']['roi']>0 and r['test']['n']>=20 and r['test']['roi']>0][:15]
if records:
    best=records[0]
    chosen=unique([r for r in rows if (best['market']=='ALL' or r['market']==best['market']) and r['q_score']>=best['q_min'] and best['odds_min']<=r['odds']<best['odds_max'] and (best['edge_min'] is None or r['edge'] is not None and r['edge']>=best['edge_min']) and r['quote_age']<=best['quote_age_max']])
    result['winner_detail']={part:stats([r for r in chosen if (r['day']<cutoff)==(part=='train')],True) for part in ['train','test']}
    result['winner_picks']=chosen
result['q_bands']={str(lo):stats(unique([r for r in rows if lo<=r['q_score']<hi])) for lo,hi in [(0,40),(40,50),(50,60),(60,70),(70,80),(80,90),(90,101)]}
result['edge_bands']={str(lo):stats(unique([r for r in rows if r['edge'] is not None and lo<=r['edge']<hi])) for lo,hi in [(-10,-.05),(-.05,0),(0,.05),(.05,.1),(.1,.2),(.2,10)]}
result['ledger_overlap_first_capture']=sum(r['id'] in lookup for r in rows)
result['ledger_edge_difference_count']=sum(abs(r['edge']-lookup[r['id']]['ledger_edge'])>1e-8 for r in rows if r['id'] in lookup and r['edge'] is not None and lookup[r['id']]['ledger_edge'] is not None)
result['odds_bands']={f'{lo}-{hi}':stats(unique([r for r in rows if lo<=r['odds']<hi])) for lo,hi in [(1,1.2),(1.2,1.5),(1.5,1.8),(1.8,2),(2,3),(3,5),(5,100)]}
result['candidate_sensitivity']={}
for q in [60,65,70]:
 for lo,hi in [(1.5,3),(1.8,3),(2,3),(1.8,4)]:
  for edge in [None,-.05,0,.02]:
   chosen=unique([r for r in rows if r['market']=='away_win' and r['q_score']>=q and lo<=r['odds']<hi and r['quote_age']<=3 and (edge is None or r['edge'] is not None and r['edge']>=edge)])
   result['candidate_sensitivity'][f'Q>={q}; {lo}<=odds<{hi}; edge>={edge}']={part:stats([r for r in chosen if (r['day']<cutoff)==(part=='train')]) for part in ['train','test']}
if records:
    picks=result['winner_picks']
    result['candidate_by_competition']={c:stats([r for r in picks if r['competition']==c]) for c in sorted({r['competition'] for r in picks})}
    result['candidate_by_version']={c:stats([r for r in picks if r['model_version']==c]) for c in sorted({r['model_version'] for r in picks})}
with (ROOT/'eligible-selections.csv').open('w',newline='',encoding='utf8') as f:
    fields=['id','match_id','day','market','selection','q_score','odds','edge','home_goals','away_goals','result','rejection_check','profit','model_version','quote_age']
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for r in rows:
        v={k:r.get(k) for k in fields}; v['rejection_check']={1:'Failed',-1:'Passed',0:'Void'}[r['result']] if r['id'] in lookup else 'Not in reconstructed ledger'; w.writerow(v)
(ROOT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
with (ROOT/'sweep.csv').open('w',newline='',encoding='utf8') as f:
    flattened=[{**{k:v for k,v in r.items() if k not in ('train','test')},**{part+'_'+k:v for part in ['train','test'] for k,v in r[part].items()}} for r in records]
    if flattened:
        writer=csv.DictWriter(f,fieldnames=list(flattened[0])); writer.writeheader(); writer.writerows(flattened)
print(json.dumps({k:result[k] for k in ['eligible','grid_tested','test_start','winner_detail']},indent=2))
