"""Render the saved simulation into an auditable Markdown report and CSV."""
import csv
import json
import math
import re
from pathlib import Path

root = Path('research/rejection-ledger-2026-10-18')
a = json.loads((root/'current-ledger/analysis.json').read_text())
b = json.loads((root/'analysis.json').read_text())

def pct(x): return 'Unavailable' if x is None else f'{x:+.2f}%'
def line(name,s):
    return f"| {name} | {s['n']} | {s['wins']} | {s['losses']} | {s['voids']} | {s['hit']:.2f}% | {pct(s['roi'])} | {s['profit']:+.2f} |"
def table(items):
    return '\n'.join(['| Combination / period | Selections | Wins / rejection failed | Losses / rejection passed | Void | Hit rate | ROI | Profit (units) |','|---|---:|---:|---:|---:|---:|---:|---:|']+[line(k,v) for k,v in items if v['n']])

# Independently verify winner results directly against exported final scores.
picks=a['winner_picks']
assert len({r['match_id'] for r in picks})==len(picks)
for part in ('train','test'):
    rs=[r for r in picks if (r['day']<'2026-10-11')==(part=='train')]
    profit=sum(0 if r['status'] in ('POSTPONED','CANCELLED') else (r['odds']-1 if r['away_goals']>r['home_goals'] else -1) for r in rs)
    assert math.isclose(profit,a['winner_detail'][part]['profit'],abs_tol=1e-9)
    assert all(r['market']=='away_win' and r['q_score']>=65 and 1.8<=r['odds']<3 for r in rs)
for cohort in (a,b):
    for s in [cohort['one_match_baseline'],cohort['all_market_baseline'],*cohort['markets'].values()]:
        assert s['wins']+s['losses']+s['voids']==s['n']
        assert math.isclose(s['roi'],s['profit']/s['n']*100,abs_tol=1e-9)

main=[('Highest Q per match; all dates',a['one_match_baseline']),('Over 1.5; all dates',a['markets']['over_1.5']),('Under 4.5; all dates',a['markets']['under_4.5']),('Away win, Q>=65, 1.80<=odds<3; earlier period',a['winner_detail']['train']),('Same combination; later period',a['winner_detail']['test'])]
parts=['# Transparent rejection ledger: combination analysis',
'Snapshot: 18 October 2026. Status: historical simulation; no validated live selection policy.',
'## Finding',
'The strongest training-period candidate with at least 40 selections was away win, Q-score >=65, decimal odds >=1.80 and <3.00, with no minimum edge requirement. Quotes were no more than 3 hours old at prediction time. The later-period return was positive, but the sample is small, uncertainty spans losses, and nearby thresholds do not perform consistently. There is no demonstrated dependable sweet spot yet.',
'## The six requested fields',
'| Field | How it was used |\n|---|---|\n| Selection | Separate market/selection types, plus an all-market strategy |\n| Q-score | Thresholds and score bands; it is not a calibrated win probability |\n| Odds | Entry decimal odds ranges and actual winning payouts |\n| Edge | Multiple thresholds; ledger market edge and stored model edge analysed separately |\n| Match result | Final score determines won, lost or void |\n| Rejection check | Lost = passed rejection; won = failed rejection; void is neutral |',
'Match result and rejection check evaluate the combinations. They are not pre-match filters and are not two independent predictive signals.',
'## Data and simulation method',
'- Read-only database transaction; no application policy, stored prediction, ticket or database record was changed. Research scripts and local artifacts were added only.\n- Source export: 46,400 prediction rows, including repeated runs. First-capture comparator: 14,256 distinct match/market pairs; 32,144 later repeats removed. Missing first-capture odds were not replaced using later prices.\n- Current-rule ledger reconstruction: 17,008 rows before duplicate and eligibility filtering. After filtering: 9,408 priced resolved/void market selections across 672 distinct fixtures. This is more than the 500-row UI cap and spans multiple dates.\n- Ledger reconstruction uses the latest completed model run for each target date, as the endpoint does, then keeps the earliest occurrence of each match/market in that reconstructed set. It is NOT an immutable record of what was rejected on the original decision day.\n- First-capture comparator uses all predictions, independent of current ledger membership: 9,646 priced resolved/void selections across 689 fixtures.\n- Eligible predictions and quotes have pre-kickoff timestamps, quote time no later than decision time, no replay as_of marker, no flagged fallback odds, decimal odds >1, and known results. Timestamp checks do not independently certify the original provider data or exclude every possible upstream model-training leak.\n- Dates: 14 September through 18 October 2026, CAT. Earlier period: before 11 October; later period: 11–18 October. This split was determined from available dates before ranking strategies. 18 October remains a partial day; unresolved games are excluded.\n- Every strategy takes at most one selection per fixture, choosing highest Q, then earlier capture, then prediction ID. Single-market strategies naturally have one selection per fixture. Separate strategy tables can overlap and must not be added together.\n- Flat one-unit singles. Win profit = odds minus one; loss = minus one; void = zero. Hit rate = wins/(wins+losses). ROI = net profit/all staked units, including refunded void stakes in the denominator. No compounding, accumulators, tax, bookmaker limits or execution guarantees.\n- Grid per cohort: 15 selection scopes (14 priced markets plus all-market), 9 Q thresholds, 7 odds ranges, 8 edge floors including no filter, and 3 quote-age caps = 22,680 parameter settings. Many settings select identical rows, so this is not 22,680 independent tests. DNB markets had no eligible priced first-capture rows.\n- Training eligibility: at least 40 selections; 3,654 ledger settings qualified. Ranking used earlier-period ROI only. Later-period results and sensitivity checks remain exploratory, not a prospective experiment.',
'## Main results',table(main),
'The later-period candidate had 21 passed rejections and 15 failed rejections: rejection accuracy was 58.33%, yet selecting those matches earned 2.52 units. Rejecting all of them would therefore have sacrificed 2.52 simulated units. This illustrates why rejection accuracy alone is insufficient: the 15 winning prices outweighed 21 losses.',
'Conversely, selecting the highest-Q ledger option per match lost 53.16 units. Rejecting that particular strategy avoided that simulated loss, even though 416 individual winners were rejected.',
'## Confidence and fragility',
'- Candidate later period: 36 fixtures on only 7 active dates; +7.00% ROI. A 5,000-resample day-cluster bootstrap gives an approximate 95% ROI interval of -22.84% to +38.81%. This interval is descriptive, unstable with so few days, and not corrected for searching many strategies.\n- Maximum observed later-period drawdown: 5 units; longest losing sequence: 5. Neither is a future worst-case bound.\n- Reducing winnings by 5% lowers later-period ROI to +3.73%; this is a payout sensitivity scenario, not an estimate of actual costs.\n- First-capture comparator independently recovers the same training-selected filter: earlier 40 selections, +43.48%; later 39 selections, +18.41%. Its later ROI interval is -13.45% to +65.80%. The cohorts overlap heavily, so this is a provenance sensitivity check, not independent confirmation.\n- The apparent winner was selected from thousands of historical settings. Its training ROI is subject to selection bias. Even the later sample is too short to establish durable profitability.',
'## Nearby Q and odds settings',
'All rows below use away win, no edge floor, quote age <=3 hours. These are sensitivity diagnostics, not additional validated strategies.',
'| Q minimum | Odds range | Earlier N | Earlier ROI | Later N | Later ROI |\n|---|---|---:|---:|---:|---:|']
for key,v in a['candidate_sensitivity'].items():
    if 'edge>=None' in key:
        q,odds,_=key.split('; '); parts.append(f"| {q} | {odds} | {v['train']['n']} | {pct(v['train']['roi'])} | {v['test']['n']} | {pct(v['test']['roi'])} |")
parts+=['Lowering Q from 65 to 60 with the same 1.80–below 3.00 odds range changes later ROI from +7.00% to -19.98%. Widening the upper odds bound to below 4.00 at Q>=65 changes later ROI to -0.55%. Tightening to Q>=70 appears better, but has only 24 earlier and 25 later selections; it did not meet the 40-selection training minimum.',
'## Edge findings',
'The running ledger uses market-priced legs: its displayed edge is derived from a fair-market probability minus 1/odds. The original prediction model edge is a different quantity. In all 4,998 overlapping eligible first-capture rows with both edges available, these differed. Treating the displayed edge as the original model edge would invalidate the comparison.',
'For the candidate Q>=65 / away-win / odds 1.80–below 3.00 combination: no edge floor and a -5 percentage-point floor select the same 42 earlier / 36 later cases. Requiring nonnegative ledger edge leaves zero earlier cases and only two later cases (one win, one loss). Requiring +2 percentage points leaves none. There is insufficient evidence to recommend a positive-edge cutoff for this combination.',
'Ledger edge is recalculated using stored bookmaker books whose query does not impose an original decision-time cutoff. It cannot be treated as a verified historical pre-match signal. The separate first-capture analysis tests persisted model edge instead. The leading candidate does not rely on either edge filter.',
'## Selection types: all eligible ledger fixtures',table(list(a['markets'].items())),
'High hit rate did not imply profit: under 4.5 won 80.81% of non-void selections but returned -4.15% ROI; over 1.5 won 77.96% but returned -2.57%. Evaluate payouts and losses together.',
'## Q-score bands',table([(f"Q [{k}, {int(k)+10})" if k!='0' else 'Q below 40',v) for k,v in a['q_bands'].items()]),
'Each band chooses its highest-Q qualifying selection per match. These are separate strategies, not disjoint fixture samples. Q-score alone does not show a monotonic profit relationship.',
'## Odds bands',table(list(a['odds_bands'].items())),
'## Ledger edge bands',table([(f"Edge lower bound {k} (see JSON for bands)",v) for k,v in a['edge_bands'].items()]),
'Edge bands are [-10,-0.05), [-0.05,0), [0,0.05), [0.05,0.10), [0.10,0.20), [0.20,10). Values are probability differences; 0.05 means five percentage points. Very small positive cohorts are not evidence of an edge.',
'## Data limitations found',
'1. The UI cap is 500, which is not a full sample count.\n2. Current rejection checks use current rule evaluations, including stale-odds checks against the current clock. Replaying an old date does not recover immutable historical rejection reasons.\n3. Direct reconstruction encountered a division-by-zero in market pricing when odds were missing but fair probability existed. The read-only export bypassed repricing only for zero-odds rows so they could retain missing-odds rejection reasons; they are excluded from profit simulations. The application bug itself was not changed.\n4. Model versions and leagues are mixed. Candidate breakdowns are included in analysis.json, but league samples are too small for reliable league-specific filters.\n5. Same-day correlation is partly reflected by day-cluster resampling; dependence across days and model regimes remains. Actual bookmaker acceptance and achievable prices were not tested.',
'## Recommended next steps',
'1. Keep the away-win / Q>=65 / odds [1.80,3.00) combination as a frozen paper-testing hypothesis. Do not relax existing publication or quality gates on this evidence.\n2. Log each qualifying future fixture before kickoff, with immutable selection, Q, model edge, market edge, quoted odds, quote timestamp, decision timestamp, model version and rule version. Log excluded opportunities too.\n3. Collect a fresh period across several months and many independent matchdays. Set review dates and sample requirements before observing results; a few hundred observations is a starting point for planning, not an automatic proof threshold.\n4. Require positive future net ROI after realistic costs, uncertainty narrow enough to rule out an unacceptable loss, and reasonably stable nearby thresholds before calling any combination dependable.\n5. Report rejection precision alongside avoided loss and missed profit. A rejection can be correct more often than not while still discarding a profitable strategy.\n6. Add clear labels for model edge versus market edge, immutable rejection snapshots, full export/pagination, sample size and outcome coverage to the ledger. These are recommendations, not implemented UI changes.',
'## Files and reproducibility',
'- `current-ledger/sweep.csv`: all grid settings meeting the earlier-period minimum, with both periods.\n- `current-ledger/eligible-selections.csv`: row-level six-field evidence, final scores, returns and rejection checks.\n- `comparison.csv`: headline strategies with explicit passed/failed rejection counts and financial effect.\n- `current-ledger/analysis.json`: full ledger statistics, candidate picks, sensitivity and league/version breakdowns.\n- `analysis.json` and `sweep.csv`: persisted first-capture model-edge comparator.\n- `predictions.json` and `ledger.json`: local input snapshots.\n- Scripts: `backend/scripts/rejection_ledger_export.py`, `analyze_rejection_ledger.py`, `report_rejection_ledger.py`. Export requires application database access; analysis/report run locally with NumPy.\n- Checks: winner returns independently recomputed from final scores; candidate criteria and unique-match counts checked; wins+losses+voids and ROI arithmetic verified. No browser or UI change was made.',
'## Statistical reference',
'Searching many historical parameter settings can produce apparently strong winners by chance: [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). The bootstrap intervals here do not remove this selection effect.']
(root/'REPORT.md').write_text(re.sub(r'(?<=\|)\n\n(?=\|)', '\n', '\n\n'.join(parts))+'\n',encoding='utf8')
with (root/'comparison.csv').open('w',newline='',encoding='utf8') as f:
    fields=['combination','selections','won_rejection_failed','lost_rejection_passed','void','hit_rate_pct','rejection_pass_rate_pct','selection_roi_pct','selection_profit_units','rejection_avoided_loss_units_net']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for name,s in main:
        w.writerow(dict(zip(fields,[name,s['n'],s['wins'],s['losses'],s['voids'],s['hit'],100-s['hit'],s['roi'],s['profit'],-s['profit']])))
print('Report and comparison CSV written. Arithmetic and winner-outcome checks passed.')
