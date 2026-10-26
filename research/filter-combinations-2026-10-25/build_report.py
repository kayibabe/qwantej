import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
s=json.loads((ROOT/'summary.json').read_text())
combinations=json.loads((ROOT/'combinations.json').read_text())
def f(x): return '—' if x is None else f'{x:.2f}'
def table(rs):
    text='| Filter | Selections | Matches | Wins–losses | Hit rate | Profit (units) | ROI |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for r in rs:
        text+=f"| {r['filter']} | {r['n']} | {r['matches']} | {r['wins']}–{r['losses']} | {f(r['hit'])}% | {f(r['profit'])} | {f(r['roi'])}% |\n"
    return text

report=f"""# Match explorer filter analysis: 1–25 October 2026

Snapshot: {s['captured_at']} UTC (20:42 CAT on 25 October). Today is incomplete.

The broad Q ≥75 candidate pool lost **2.10%** at one unit per selection. The best observed combination with at least 50 selections, 30 distinct matches and seven active dates returned **24.90%**, but its uncertainty interval includes a loss. No reliable future winner has been established.

## Coverage and audit

- 1,776 feed rows; 107 exact duplicate rows removed; zero conflicting duplicates.
- 1,669 unique match/market/selection candidates across 591 matches.
- 1,609 selections across 572 finished matches. All-settled hit rate: {s['all_settled_hit']:.2f}%.
- 123 finished selections excluded from the priced analysis because captured bookmaker provenance was insufficient. They are not treated as losses.
- Main priced sample: 1,486 selections, 531 matches, 20 active dates; 864 wins, 622 losses, no settled voids.
- Unfinished: 24 live selections (six matches), 17 scheduled (seven matches), and 19 postponed (six matches). Postponed rows are outside this played-match study.
- No eligible page candidates were found for 2–6 October. This is the retained candidate feed, not all football fixtures in those dates.
- All included prediction insertion times, run completion times and quote times precede kickoff; quotes must also precede the recorded decision/information time, have decimal odds >1, an odds-source ID, a named bookmaker and explicit non-fallback provenance.
- 60 otherwise valid prices were older than three hours at decision time. Excluding them leaves {s['fresh_3h']['n']} selections, {s['fresh_3h']['hit']:.2f}% hit rate and {s['fresh_3h']['roi']:.2f}% ROI.

## Calculation

One unit on every qualifying **single selection**, using its stored source decimal odds. Win profit = odds −1; loss = −1; a settled void returns the stake and has zero profit. ROI = total net profit / total stakes ×100; hit rate = wins / (wins + losses) ×100. These are hypothetical gross returns before tax, commission, rejected bets or price availability, not placed-bet accounting and not accumulator returns. Multiple selections on a match are separate stakes and can be correlated.

## Best combinations with minimum sample coverage

Every row below already includes Q ≥75. Probability and edge values are percentages. Threshold endpoints are inclusive. Minimum coverage is a screening rule, not proof of statistical reliability.

{table(s['top_supported'][:8])}

The leading away-win combination has 59 selections, 25 wins and 34 losses, +14.69 units. Its 95% fixture-cluster bootstrap ROI interval is **−13.29% to +65.98%**. The bootstrap resamples whole matches (5,000 replications, fixed seed) to preserve within-match dependence. Intervals are descriptive and **not corrected for searching millions of combinations**, league/day dependence or model drift.

The unrestricted maximum is +700% from a single winning selection. It is not a useful strategy ranking.

## Combinations with at least 100 selections, 30 matches and seven dates

{table(s['top_100'])}

## Market-only comparison

{table(s['markets'])}

Under 1.5 and draw have the largest market-only ROI but only four and five selections respectively. Among markets with at least 50 selections, BTTS No leads at +8.35% (152 selections); its 95% fixture-cluster interval is −8.15% to +25.01%. Under 4.5 has an 84.08% hit rate but only +0.79% ROI, demonstrating why hit rate alone is insufficient.

## Later-date diagnostic

The first 70% of eligible active dates are 1–19 October; later dates are 20–25 October. Rank on the earlier segment with at least 50 selections, 30 matches and seven dates. Later results below were not used as the ranking score. This is a retrospective diagnostic, not an untouched prospective validation: all records already exist, the grid is exploratory, and equivalent filters are deduplicated using full-period membership.

| Filter | Earlier n | Earlier ROI | Later n | Later ROI |
|---|---:|---:|---:|---:|
"""
for r in s['train_selected'][:6]:
    report+=f"| {r['filter']} | {r['train']['n']} | {f(r['train']['roi'])}% | {r['test']['n']} | {f(r['test']['roi'])}% |\n"
report+="""
## What was searched

The page permits continuously variable numeric bounds, so literally every input combination is unbounded. This report exhaustively scans a declared grid, not every possible decimal threshold:

- Market: all, or each available market.
- Competition: all, or each available competition; also crossed with market.
- Q-score: underlying minimum 75; optional lower and upper cutoffs at 80, 85, 90.
- Model probability: optional lower and upper cutoffs at 60%, 70%, 80%, 90%.
- Odds: optional lower and upper cutoffs at 1.5, 2, 3, 5.
- Minimum edge: unset, 0%, 5%, 10%, 20%.
- All valid interval pairs use inclusive bounds. Equal lower/upper point intervals are omitted. Unset bounds are included.
- Finished status is fixed. Sorting changes order, not returns. Search text and favourites are not swept: there is no preserved pre-match favourite/search history, and arbitrary team-name subsets invite hindsight selection.

There are **4,882,500 grid combinations** across 434 nonempty market/competition scopes, producing **20,176 distinct nonempty selection sets**. Equivalent filters are represented by the simplest encountered expression. The interactive table exposes all distinct sets, including small samples; its default screen requires 50 selections, 30 matches and seven dates. Rows overlap, so their profits must never be added together.

## Critical page findings and suggested changes

1. **Incomplete loading:** the screenshot shows 100 of 188 candidates. Filters and summaries run on loaded rows. Fetch the full server-side filtered universe before showing historical performance.
2. **Duplicate inflation:** the feed's latest-run join can return duplicate predictions for the same match/market/selection. Deduplicate deterministically before counts and performance calculations.
3. **Ambiguous qualification:** Q ≥75 is a research threshold, not evidence that an accumulator leg passed calibration, odds freshness, context or other publication gates. Label this pool “Q-score candidates”.
4. **Different admin universe:** current source intersects the admin list with a daily ROI shortlist. This report uses the full candidate feed matching the screenshot's Q ≥75 description, not a retrospective application of the admin screen. Show the active universe explicitly.
5. **Missing date-range performance:** add date range, selection count, unique match count, won/lost/void, priced coverage, hit rate, net units and ROI to the page. Separate unsettled rows and expose excluded-price reasons.
6. **Avoid automatic promotion:** retain the present qualification gates. Freeze a short list of simple hypotheses (such as BTTS No and the away-win subset) and evaluate new matches at captured pre-match odds before considering a policy change. Do not choose another threshold every time a later batch loses.
7. **Selection counts are not match counts:** display both. Multiple bets on one match can make a sample look larger and more diversified than it is.

## Scope limitations and reproducibility

This reproduces the current historical `/selections/qualified` feed: latest completed model run per match/market, run target date equal to the Malawi kickoff date, Q ≥75, non-excluded fixtures. It does not reconstruct every candidate that might have appeared and later disappeared in a prior refresh, user-specific favourites, historic admin screens, or exact historical UI loading order. Archived created-at timestamps do not independently prove end-user visibility or executable bookmaker prices. Results use the database's recorded final scores without external re-verification. Matches on 25 October were still in progress at extraction.

The raw database transaction is repeatable-read and read-only. No results, odds, selections, strategy settings, app source or qualification gates were changed. Reproduction: copy `export_snapshot.py` to the backend container, run with `PYTHONPATH=/app`, copy `/tmp/filter_snapshot.json` back as `snapshot.json`, then run `analyse.py` and `build_report.py`. The export snapshot also contains earlier dates for audit, but analysis is explicitly limited to 1–25 October.

Files: `snapshot.json` (raw evidence), `eligible_selections.json` (priced analysis rows), `summary.json`, `combinations.json`, `report.html` (interactive table), and the three Python scripts. The summary records the raw snapshot SHA-256. Dependencies: existing backend SQLAlchemy/settlement modules for export; Python and NumPy for analysis.
"""
report+='\n## Numeric filters in isolation\n\nEvery row retains the baseline Q ≥75 and all markets/competitions.\n\n'+table(s['one_dimension'])
(ROOT/'REPORT.md').write_text(report,encoding='utf-8')
data=json.dumps(combinations,separators=(',',':')).replace('</','<\\/')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>October filter analysis</title>
<style>body{font:15px system-ui,sans-serif;background:#f4f7fb;color:#17243b;margin:32px}h1{margin-bottom:8px}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{background:white;padding:20px;border-radius:12px;min-width:180px}.card b{display:block;font-size:28px}label{display:inline-block;margin:12px 18px 12px 0}input,select,button{font:inherit;padding:8px;border:1px solid #bbc7d7;border-radius:6px}input[type=number]{width:70px}#query{width:320px;max-width:85vw}.wrap{overflow:auto;background:white;border-radius:10px}table{border-collapse:collapse;width:100%}th,td{text-align:right;padding:11px;border-bottom:1px solid #e3e9f0;white-space:nowrap}td:first-child,th:first-child{text-align:left;white-space:normal;min-width:330px}th{background:#e5edf8}.negative{color:#a32a31}.positive{color:#08684c}p{max-width:1100px;line-height:1.55}.warning{background:#fff2d6;padding:15px;border-radius:8px}button{cursor:pointer}</style>
<h1>Which October filters returned a profit?</h1><p>1–25 October 2026 • Snapshot 25 October, 20:42 CAT • Q ≥75 • One unit per single selection</p>
<div class="cards"><div class="card">Priced selections<b>1,486</b>531 finished matches</div><div class="card">Overall hit rate<b>58.14%</b>864 wins / 622 losses</div><div class="card">Overall ROI<b class="negative">−2.10%</b>−31.25 units</div><div class="card">Grid search<b>4,882,500</b>20,176 distinct selection sets</div></div>
<p class="warning"><strong>Exploratory results, not a validated strategy.</strong> The earlier-period leader dropped from +28.90% to −17.88% on later dates. The highest full-period filter passing the default sample screen has +24.90% ROI but a 95% interval of −13.29% to +65.98%. Small samples and repeated searching can produce impressive winners by chance.</p>
<p>Removed 107 exact duplicates and excluded 123 settled selections with insufficient quote provenance. Live, scheduled and postponed matches are outside this table. Today is incomplete. <a href="REPORT.md">Read full methods and page critique</a> · <a href="summary.json">Summary data</a> · <a href="combinations.json">All combinations (JSON)</a></p>
<label>Search filter <input id="query" placeholder="e.g. btts_no or odds"></label><label>Minimum selections <input id="minN" type="number" min="1" value="50"></label><label>Minimum matches <input id="minM" type="number" min="1" value="30"></label><label>Minimum dates <input id="minD" type="number" min="1" value="7"></label><label>Sort <select id="sort"><option value="roi">Full-period ROI</option><option value="n">Sample size</option><option value="hit">Hit rate</option><option value="train">Earlier ROI</option><option value="test">Later ROI</option></select></label>
<p id="count"></p><div class="wrap"><table><thead><tr><th>Filter (Q ≥75 always)</th><th>Selections</th><th>Matches</th><th>Dates</th><th>W / L</th><th>Hit rate</th><th>Net units</th><th>ROI</th><th>Earlier n / ROI</th><th>Later n / ROI</th></tr></thead><tbody id="body"></tbody></table></div><p><button id="prev">Previous</button> <span id="page"></span> <button id="next">Next</button></p><p>Earlier: 1–19 October. Later: 20–25 October. Numeric probability cutoffs are percentages; edge cutoffs are percentage points. Thresholds are inclusive. Equivalent filters share one representative row. Filters overlap: do not sum their profits.</p>
<script>const rows=DATA;let page=0,current=[];const $=id=>document.getElementById(id);const fmt=x=>x==null?'—':x.toFixed(2);const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function draw(){const q=$('query').value.toLowerCase();current=rows.filter(r=>r.n>=+$('minN').value&&r.matches>=+$('minM').value&&r.days>=+$('minD').value&&r.filter.toLowerCase().includes(q));const key=$('sort').value;const val=r=>key==='train'||key==='test'?(r[key].roi??-Infinity):r[key];current.sort((a,b)=>val(b)-val(a)||b.n-a.n);page=Math.max(0,Math.min(page,Math.ceil(current.length/50)-1));$('count').textContent=current.length.toLocaleString()+' distinct selection sets match your screen';$('body').innerHTML=current.slice(page*50,page*50+50).map(r=>`<tr><td>${esc(r.filter)}</td><td>${r.n}</td><td>${r.matches}</td><td>${r.days}</td><td>${r.wins} / ${r.losses}</td><td>${fmt(r.hit)}%</td><td>${fmt(r.profit)}</td><td class="${r.roi<0?'negative':'positive'}">${fmt(r.roi)}%</td><td>${r.train.n} / ${fmt(r.train.roi)}%</td><td>${r.test.n} / ${fmt(r.test.roi)}%</td></tr>`).join('');$('page').textContent=`Page ${page+1} of ${Math.max(1,Math.ceil(current.length/50))}`;$('prev').disabled=page===0;$('next').disabled=(page+1)*50>=current.length;}['query','minN','minM','minD','sort'].forEach(id=>$(id).addEventListener('input',()=>{page=0;draw()}));$('prev').onclick=()=>{page--;draw()};$('next').onclick=()=>{page++;draw()};draw();</script></html>'''.replace('DATA',data)
(ROOT/'report.html').write_text(page,encoding='utf-8')
print('Created REPORT.md and report.html')
