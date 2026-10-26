"""Independently reapply representative rules and check all report calculations."""
import ast
import json
import re
import subprocess
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent
rows=json.loads((root/'eligible_selections.json').read_text())
results=json.loads((root/'combinations.json').read_text())
markets={r['market'] for r in rows}; competitions={r['competition'] for r in rows}
fields={k:np.array([r[k] if r[k] is not None else np.nan for r in rows]) for k in ['q_score','model_probability','odds','edge']}
wins=np.array([r['outcome']=='won' for r in rows]); losses=np.array([r['outcome']=='lost' for r in rows])
profit=np.where(wins,fields['odds']-1,np.where(losses,-1,0))
scope_cache={}
for result in results:
    parts=result['filter'].split('; '); scope=parts[0]
    if scope not in scope_cache:
        if scope=='All markets / competitions': mask=np.ones(len(rows),dtype=bool)
        elif scope in markets: mask=np.array([r['market']==scope for r in rows])
        elif scope in competitions: mask=np.array([r['competition']==scope for r in rows])
        else:
            market,league=scope.split(' / ',1)
            mask=np.array([r['market']==market and r['competition']==league for r in rows])
        scope_cache[scope]=mask
    mask=scope_cache[scope].copy()
    for part in parts[1:]:
        for clause in part.split(', '):
            field,op,value=re.fullmatch(r'(\w+) ([≥≤]) ([\d.]+)%?',clause).groups()
            value=float(value)/(100 if field in ('model_probability','edge') else 1)
            mask &= fields[field]>=value if op=='≥' else fields[field]<=value
    assert int(mask.sum())==result['n'],result['filter']
    assert int(wins[mask].sum())==result['wins']
    assert int(losses[mask].sum())==result['losses']
    assert abs(float(profit[mask].sum())-result['profit'])<1e-5
    assert abs(float(profit[mask].mean())*100-result['roi'])<1e-7
for path in root.glob('*.py'): ast.parse(path.read_text(encoding='utf-8'))
page=(root/'report.html').read_text(encoding='utf-8')
js=page.split('<script>',1)[1].split('</script>',1)[0]
mock="""const elements={};global.document={getElementById:id=>elements[id]??(elements[id]={value:({minN:'50',minM:'30',minD:'7',sort:'roi',query:''}[id]||''),addEventListener:()=>{}})};
"""
checks="""if(!elements.body.innerHTML.includes('away_win'))throw Error('Initial table missing leader'); elements.query.value='btts_no';draw();if(!elements.body.innerHTML.includes('btts_no'))throw Error('Search failed');elements.query.value='impossible_filter';draw();if(current.length!==0)throw Error('Empty-state failed');console.log('HTML table initialization, search, and empty state passed');"""
subprocess.run(['node','-e',mock+js+checks],check=True) if len(js)<20000 else subprocess.run(['node'],input=mock+js+checks,text=True,encoding='utf-8',check=True)
print(f'Independently verified membership, wins, losses, profit and ROI for all {len(results):,} representative combinations.')
