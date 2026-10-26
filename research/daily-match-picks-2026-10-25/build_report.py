import html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
s=json.loads((ROOT/'summary.json').read_text())
def pct(x):return '—' if x is None else f'{x:.1f}%'
def amount(x):return '—' if x is None else f'{x:+.2f}'
def table(rows,market=False):
 out='| Market / filter | Selections | Won | Lost | Hit rate | Net units | ROI | Earlier ROI | Later ROI |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
 for r in rows:
  out+=f"| {r['filter'] if not market else r['market']} | {r['n']} | {r['wins']} | {r['losses']} | {pct(r['hit'])} | {amount(r['profit'])} | {pct(r['roi'])} | {pct(r['early']['roi']) if 'early' in r else '—'} | {pct(r['late']['roi']) if 'late' in r else '—'} |\n"
 return out
markets=[{'market':r['market'],**r} for r in s['market_only']]
report=f"""# Daily Match Picks: 1–25 October 2026

Data snapshot: {s['captured_at']} UTC ({(s['captured_at'])}). The 25 October slate was still underway when captured.

## Finding

The replayed Daily Match Picks produced **{s['candidate_picks']} selections over {s['picked_days']} active dates**. Of these, {s['settled_candidates']} had settled: **{s['settled_metrics']['wins']} wins and {s['settled_metrics']['losses']} losses**, a {pct(s['settled_metrics']['hit'])} hit rate. One unit staked on each settled pick returned **{amount(s['settled_metrics']['profit'])} units / {pct(s['settled_metrics']['roi'])} ROI**. Five of the picks from 25 October were unresolved at extraction and are excluded from this settled-pick result.

The highest full-sample combination passing the screening rule (at least 30 settled picks, 25 distinct matches and five active dates) was **all historically qualifying markets, Q 75–80, odds ≤2.75**: {s['top_supported'][0]['n']} picks, {s['top_supported'][0]['wins']} wins and {s['top_supported'][0]['losses']} losses; ROI {pct(s['top_supported'][0]['roi'])}. The fixture-resampled 95% interval is {s['top_supported_ci95'][0]['roi_cluster_ci95'][0]:.1f}% to {s['top_supported_ci95'][0]['roi_cluster_ci95'][1]:.1f}%, so this small-sample edge is uncertain. Searching thousands of overlapping filters makes the strongest observed result more likely to be a chance winner.

## Daily Match Picks rules reconstructed

For each target date, the API looks only at prior settled matches to qualify each market. Historical selections require Q ≥70, captured odds from 2.00 up to (but not including) 3.00, a named bookmaker and non-fallback source, a valid pre-kickoff quote, and a prediction timestamp before kickoff. Quote freshness at the decision must be within the configured two hours; the route also applies a three-hour maximum. A market qualifies only if historical hit rate is **strictly greater than 50%** and flat-stake ROI is **strictly greater than 30%**. Daily candidates use those qualifying markets, the same Q and odds bounds, and valid captured pre-kickoff bookmaker prices. In the screenshot the visible controls were Minimum Q = 70 and Grade = All; this analysis uses that view.

I replayed this process date by date, so a future result cannot qualify an earlier day’s market. For each date and match/market/selection, I used the latest valid prediction, then settled it against the score in the local database. I counted single selections with a flat one-unit stake: a win returns odds −1 net units; a loss −1 unit. ROI is total net units / settled stakes. These are reconstructed paper results, not confirmed placed wagers or executable-price accounting.

## Market performance within the reconstructed daily picks

{table(markets,True)}

Over 4.5 leads at +100.4%, but it has only five picks (four wins). Its 95% match-resampled interval spans {markets[0]['roi_cluster_ci95'][0]:.1f}% to {markets[0]['roi_cluster_ci95'][1]:.1f}%. Over 2.5 has 23 picks and +31.2% ROI, with an interval of {next(r for r in markets if r['market']=='over_2.5')['roi_cluster_ci95'][0]:.1f}% to {next(r for r in markets if r['market']=='over_2.5')['roi_cluster_ci95'][1]:.1f}%. The intervals are broad; neither establishes a dependable market edge. (Rows are sorted by full-period ROI.)

## Best Q-score / odds filters across historically qualifying markets

This sweep varies Q lower/upper bounds and odds bands inside the page’s existing Q ≥70 and 2.00–<3.00 base range, across all qualifying markets or one market at a time. The default screen requires 30 settled selections, 25 distinct matches and five active dates. Table columns “Earlier” and “Later” show performance before 20 October and from 20–25 October.

{table(s['top_supported'][:12])}

The period split is descriptive, not a clean prospective test: filters are searched retrospectively over the whole data set. For example, a rule’s later ROI may change sharply when the last few results settle. Keep these filters in research until frozen and checked against genuinely new picks.

## Small sample leaders

{table(s['top_raw'][:8])}

Raw rankings can put a market with one or five selections first. Treat the sample screen as a guard against the most extreme cases, not as a guarantee of statistical reliability. Confidence intervals here resample whole matches (5,000 replicates, fixed seed); they do not account for the extensive filter search, date clustering, model updates or price execution.

## Coverage and limits

- The database snapshot contained {s['raw_rows']} Q ≥70 predictions with prices in the Daily Match Picks odds band, over historical rows available before 25 October CAT end of day. Historical rows were deduplicated per fixture, market and selection using the latest valid pre-match prediction, mirroring the route.
- The reconstructed daily feed yielded {s['candidate_picks']} picks on {s['picked_days']} dates. Dates without picks are not missing losses; they had no market/prediction satisfying the reconstructed gates.
- The 25 October view had {next(x for x in s['daily'] if x['day']=='2026-10-25')['candidate_selections']} picks; {next(x for x in s['daily'] if x['day']=='2026-10-25')['settled']['n']} were settled at snapshot time. The other five remain open and are not scored as losses.
- Results use the locally stored match scores, prediction timestamps and captured odds. I did not independently verify scores or bookmaker execution outside this database.
- Markets and filters overlap; do not add their returns together. Search results are exploratory and do not justify changing qualification thresholds or publication rules.

## Reproduction

`export_snapshot.py` makes a read-only repeatable-read database extract; `analyse.py` performs the as-of-date replay and filter sweep; `build_report.py` creates this report and `report.html`. `snapshot.json` is the raw extract, `daily_picks.json` contains the reconstructed candidates, `summary.json` has the audit metrics, and `combinations.json` contains the full nonempty grid. SHA-256: `{s['snapshot_sha256']}`.
"""
(ROOT/'REPORT.md').write_text(report,encoding='utf-8')
rows=json.dumps(s['top_supported'],separators=(',',':')).replace('</','<\\/')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily Match Picks analysis</title><style>body{font:15px system-ui,sans-serif;margin:30px;background:#f4f7fb;color:#17243b}h1{margin-bottom:5px}.warning,.card,.wrap{background:white;border-radius:10px;padding:16px;margin:12px 0}.warning{background:#fff2d6;line-height:1.5}.cards{display:flex;flex-wrap:wrap;gap:12px}.card{min-width:170px}.card b{display:block;font-size:25px}.wrap{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #e1e8f0;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left;white-space:normal;min-width:350px}.negative{color:#a32a31}.positive{color:#08684c}p{line-height:1.55;max-width:1100px}</style><h1>Daily Match Picks: October performance</h1><p>1–25 October 2026 · Q ≥70 · odds 2.00 to below 3.00 · as-of-date market qualification</p><div class="cards"><div class="card">Settled picks<b>85</b>over 18 active dates</div><div class="card">Wins / losses<b>42 / 43</b>Hit 49.4%</div><div class="card">Net units / ROI<b>+14.69 / +17.28%</b>one unit per settled pick</div><div class="card">Unresolved today<b>5</b>excluded from settled ROI</div></div><p class="warning"><b>Highest useful screen:</b> all qualifying markets, Q 75–80, odds ≤2.75 — 37 picks, 21W–16L, +32.8% ROI. Its 95% match-bootstrap interval crosses zero (see full report). Full search and limited sample make this exploratory, not validated profitability.</p><p><a href="REPORT.md">Full methodology and analysis</a> · <a href="summary.json">Summary data</a> · <a href="combinations.json">All combinations</a></p><label>Search filter <input id="query" placeholder="market, Q or odds"></label><div class="wrap"><table><thead><tr><th>Combination</th><th>Settled n</th><th>W–L</th><th>Hit</th><th>Units</th><th>ROI</th><th>Earlier ROI</th><th>Later ROI</th></tr></thead><tbody id="body"></tbody></table></div><script>const data=DATA;const q=document.getElementById('query'),body=document.getElementById('body');function draw(){const a=data.filter(x=>x.n>=30&&x.matches>=25&&x.days>=5&&x.filter.toLowerCase().includes(q.value.toLowerCase())).slice(0,100);body.innerHTML=a.map(x=>`<tr><td>${x.filter}</td><td>${x.n}</td><td>${x.wins}–${x.losses}</td><td>${x.hit.toFixed(1)}%</td><td>${x.profit>=0?'+':''}${x.profit.toFixed(2)}</td><td class="${x.roi>=0?'positive':'negative'}">${x.roi.toFixed(1)}%</td><td>${x.early.roi==null?'—':x.early.roi.toFixed(1)+'%'}</td><td>${x.late.roi==null?'—':x.late.roi.toFixed(1)+'%'}</td></tr>`).join('')}q.addEventListener('input',draw);draw();</script></html>'''.replace('DATA',rows)
(ROOT/'report.html').write_text(page,encoding='utf-8')
print('Created report.html and REPORT.md')
