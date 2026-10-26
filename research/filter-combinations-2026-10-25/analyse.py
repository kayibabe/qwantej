"""Exhaustive declared-grid research scan. No application/database writes."""
import collections
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
source = json.loads((ROOT/'snapshot.json').read_text())
rows = [r for r in source['rows'] if '2026-10-01' <= r['day'] <= '2026-10-25']
raw_count=len(rows)
dedup={}
conflicts=0
for r in rows:
    key=(r['match_id'],r['market'],r['selection'])
    if key in dedup:
        conflicts += any(r[k]!=dedup[key][k] for k in r if k!='id')
    if key not in dedup or r['id']>dedup[key]['id']: dedup[key]=r
rows=list(dedup.values())
D = lambda x: dt.datetime.fromisoformat(x) if x else None

def reasons(r):
    out=[]
    kickoff=D(r['kickoff_at']); created=D(r['created_at']); quote=D(r['source_odds_at'])
    decision=D(r['decision_at'] or r['as_of_at'] or r['created_at'])
    if created >= kickoff: out.append('inserted_after_kickoff')
    if not r['run_completed_at'] or D(r['run_completed_at']) >= kickoff: out.append('run_not_completed_before_kickoff')
    if decision >= kickoff: out.append('decision_after_kickoff')
    if not quote or quote >= kickoff or quote > decision: out.append('invalid_quote_timing')
    if not r['odds'] or not math.isfinite(r['odds']) or r['odds'] <= 1: out.append('invalid_odds')
    provenance=r['source_odds_provenance'] or {}
    if not r['source_odds_id'] or not provenance.get('bookmaker') or provenance.get('is_fallback') is not False:
        out.append('unverified_quote_provenance')
    return out

for r in rows: r['exclusions']=reasons(r)
settled=[r for r in rows if r['outcome'] in ('won','lost','void')]
eligible=[r for r in settled if not r['exclusions']]
assert len({(r['match_id'],r['market'],r['selection']) for r in eligible})==len(eligible)
dates=sorted({r['day'] for r in eligible})
split=dates[max(0,int(len(dates)*.7)-1)]
N=len(eligible)
ALL=(1<<N)-1
def mask_where(fn):
    return sum(1<<i for i,r in enumerate(eligible) if fn(r))
TRAIN=mask_where(lambda r:r['day']<=split)
TEST=ALL^TRAIN
cache={}
def stats(mask):
    if mask in cache: return cache[mask]
    records=[]; v=mask
    while v:
        bit=v&-v; records.append(eligible[bit.bit_length()-1]); v-=bit
    n=len(records); w=sum(r['outcome']=='won' for r in records); l=sum(r['outcome']=='lost' for r in records)
    pnl=sum(r['odds']-1 if r['outcome']=='won' else -1 if r['outcome']=='lost' else 0 for r in records)
    result={'n':n,'matches':len({r['match_id'] for r in records}),'days':len({r['day'] for r in records}),
            'wins':w,'losses':l,'voids':n-w-l,'hit':100*w/(w+l) if w+l else None,
            'profit':round(pnl,6),'roi':100*pnl/n if n else None,
            'mean_odds':sum(r['odds'] for r in records)/n if n else None}
    cache[mask]=result
    return result

def intervals(field, boundaries, scale=1):
    options=[(None,None)]
    for low in [None]+boundaries:
        for high in boundaries+[None]:
            if (low,high)==(None,None) or (low is not None and high is not None and low>=high): continue
            options.append((low,high))
    output=[]
    for lo,hi in options:
        mask=mask_where(lambda r: r[field] is not None and (lo is None or r[field]>=lo/scale) and (hi is None or r[field]<=hi/scale))
        label=[]
        if lo is not None: label.append(f'{field} ≥ {lo}')
        if hi is not None: label.append(f'{field} ≤ {hi}')
        output.append((mask,', '.join(label),int(lo is not None)+int(hi is not None)))
    return output

# Endpoints inclusive, exactly as in the page. Q >=75 is always applied upstream.
q=intervals('q_score',[80,85,90])
p=intervals('model_probability',[60,70,80,90],100)
o=intervals('odds',[1.5,2,3,5])
edges=[(ALL,'',0)]+[(mask_where(lambda r,e=e:r['edge'] is not None and r['edge']>=e/100),f'edge ≥ {e}%',1) for e in [0,5,10,20]]
market_masks={k:mask_where(lambda r,k=k:r['market']==k) for k in sorted({r['market'] for r in eligible})}
league_masks={k:mask_where(lambda r,k=k:r['competition']==k) for k in sorted({r['competition'] for r in eligible})}
scopes=[(ALL,'All markets / competitions',0)]
scopes += [(m,k,1) for k,m in market_masks.items()]
scopes += [(m,k,1) for k,m in league_masks.items()]
scopes += [(m&l,f'{mk} / {lk}',2) for mk,m in market_masks.items() for lk,l in league_masks.items() if m&l]
numeric={}
grid_numeric=0
for opts in itertools.product(q,p,o,edges):
    grid_numeric+=1
    mask=ALL
    for item in opts: mask &= item[0]
    if not mask: continue
    label='; '.join(item[1] for item in opts if item[1]); complexity=sum(item[2] for item in opts)
    if mask not in numeric or complexity<numeric[mask][1]: numeric[mask]=(label,complexity)
unique={}
for scope,sl,sc in scopes:
    for numeric_mask,(nl,nc) in numeric.items():
        mask=scope&numeric_mask
        if not mask: continue
        if mask not in unique or sc+nc<unique[mask][1]: unique[mask]=(sl+('; '+nl if nl else ''),sc+nc)
results=[]
for mask,(label,complexity) in unique.items():
    results.append({'filter':label,'complexity':complexity,**stats(mask),'train':stats(mask&TRAIN),'test':stats(mask&TEST),'_mask':mask})
results.sort(key=lambda r:(-r['roi'],-r['n'],r['complexity']))
def boot(mask):
    records=[r for i,r in enumerate(eligible) if mask&(1<<i)]
    groups=collections.defaultdict(lambda:[0.,0])
    for r in records:
        groups[r['match_id']][0]+=r['odds']-1 if r['outcome']=='won' else -1 if r['outcome']=='lost' else 0
        groups[r['match_id']][1]+=1
    if len(groups)<2:return None
    arr=np.array(list(groups.values())); rng=np.random.default_rng(20261025)
    sample=arr[rng.integers(0,len(arr),size=(5000,len(arr)))].sum(axis=1)
    return [round(float(x),2) for x in np.percentile(100*sample[:,0]/sample[:,1],[2.5,97.5])]
def clean(r,ci=False):
    out={k:v for k,v in r.items() if k!='_mask'}
    if ci: out['roi_cluster_ci95']=boot(r['_mask'])
    return out
supported=[r for r in results if r['n']>=50 and r['matches']>=30 and r['days']>=7]
discovery=sorted([r for r in results if r['train']['n']>=50 and r['train']['matches']>=30 and r['train']['days']>=7],key=lambda r:(-r['train']['roi'],-r['train']['n'],r['complexity']))
market_table=[{'filter':k,**stats(m),'train':stats(m&TRAIN),'test':stats(m&TEST),'_mask':m} for k,m in market_masks.items()]
market_table.sort(key=lambda r:-r['roi'])
audit={'captured_at':source['captured_at'],'snapshot_sha256':hashlib.sha256((ROOT/'snapshot.json').read_bytes()).hexdigest(),
       'raw_feed_rows':raw_count,'duplicate_rows_removed':raw_count-len(rows),'conflicting_duplicates':conflicts,
       'date_from':'2026-10-01','date_to':'2026-10-25','timezone':'Africa/Blantyre','candidates':len(rows),
       'matches':len({r['match_id'] for r in rows}),'status_selections':dict(collections.Counter(r['status'] for r in rows)),
       'status_matches':dict(collections.Counter(next(r['status'] for r in rows if r['match_id']==i) for i in {r['match_id'] for r in rows})),
       'settled':len(settled),'excluded_settled':len(settled)-len(eligible),
       'exclusion_reasons':dict(collections.Counter(e for r in settled for e in r['exclusions'])),
       'baseline':stats(ALL),'train_through':split,'test_from':next((d for d in dates if d>split),None),
       'dates_available':dates,'numeric_grid_count':grid_numeric,'scopes':len(scopes),'grid_combinations':grid_numeric*len(scopes),
       'unique_nonempty_selection_sets':len(results),
       'stale_quotes_over_3h':sum((D(r['decision_at'] or r['as_of_at'] or r['created_at'])-D(r['source_odds_at'])).total_seconds()>10800 for r in eligible),
       'top_supported':[clean(r,True) for r in supported[:15]],'top_raw':[clean(r) for r in results[:10]],
       'train_selected':[clean(r,True) for r in discovery[:10]],'markets':[clean(r,True) for r in market_table],
       'baseline_ci':boot(ALL),
       'all_settled_hit':100*sum(r['outcome']=='won' for r in settled)/sum(r['outcome'] in ('won','lost') for r in settled),
       'fresh_3h':stats(mask_where(lambda r:(D(r['decision_at'] or r['as_of_at'] or r['created_at'])-D(r['source_odds_at'])).total_seconds()<=10800)),
       'top_100':[clean(r,True) for r in [x for x in supported if x['n']>=100][:5]],
       'one_dimension':[{'filter':label or 'Baseline',**stats(mask)} for options in [q,p,o,edges] for mask,label,c in options if label and mask],
       'daily':[{'day':day,**stats(mask_where(lambda r,day=day:r['day']==day))} for day in dates],
       'today':stats(mask_where(lambda r:r['day']=='2026-10-25'))}
(ROOT/'summary.json').write_text(json.dumps(audit,indent=2))
(ROOT/'combinations.json').write_text(json.dumps([clean(r) for r in results],separators=(',',':')))
(ROOT/'eligible_selections.json').write_text(json.dumps(eligible,indent=2))
print(json.dumps(audit,indent=2))
