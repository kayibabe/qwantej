# Reconciling the two work streams — 2026-11-11

Two reviews ran in parallel: the OpenCode stream (calibration audit, market
grid, frozen paper policy) and the Workik stream (selection-code review,
"what can we improve on for winning market selection"). This note reconciles
them against the database and the code, separates what is verified from what
is wrong, and sets the work queue.

Everything below is read-only. No live selection, staking, or pricing logic was
changed by this note.

## 1. Where both streams agree (and the database confirms)

| Claim | Status | Evidence |
| --- | --- | --- |
| Q ≥ 75 is badly overconfident | **Verified** | 25,095 out-of-sample picks: raw 77.0%, observed 57.4%. Isotonic 65.7%, implied 60.0%. |
| The model adds no information beyond the price | **Verified** | `won ~ logit(implied) + logit(model)`: coefficient 0.003 (95% CI -0.107 to 0.110) all picks; -0.104 (-0.459 to 0.232) at Q ≥ 75. |
| No market cell survives validation | **Verified** | 3,080 Q ≥ 75 picks, -1.6% ROI; best cell +45.4% has permutation p = 0.97; no cell clears a day-cluster lower bound. |
| Double chance is the reproducible loser | **Verified** | `double_chance_x2` -7.8% over 491 picks; `1x` -12.9% over 151. Largest bucket. |
| Don't promote a market from this sample | **Agreed** | Raw ROI rank is unstable; the only cells positive in both halves have bootstrap lows well below zero. |
| One pick per fixture for staking | **Agreed** | Picks from the same fixture are correlated; per-pick totals overstate independent bets. |
| CLV is a gate, not a live filter | **Agreed in principle** | But the CLV field is currently unreliable; see §3. |

## 2. What Workik got right that the OpenCode stream had not fully absorbed

1. **The live leg price already uses market probability, not model edge.**
   `leg_probability_source` defaults to `market`, and the Conservative/Balanced
   tiers price legs at de-vigged market probability. So "stop using edge for
   selection" is partly already true in the accumulator path.

2. **There are three disagreeing exclusion lists.** `research_restricted_markets`,
   `market_policy_shadow_excluded_markets`, and `policy-q75-nodc-v1` do not
   agree, and the live portfolio follows none of them. That is a real
   governance problem, not a research detail.

3. **Multiple testing is the main reason the "best cell" is meaningless.**
   The 2,824-cell grid with a +45.4% winner and p = 0.97 is the textbook
   outcome. Keep rule counts small and pre-registered.

4. **The `best_odds` name is misleading, but not in the way Workik thought.**
   `selections.py` exposes `source_decimal_odds` as `best_odds`. It *is* the
   best price across tracked books, but it is a single-source quote, not a
   best-execution guarantee.

## 3. Where Workik was wrong, or the recommendation is already moot

### 3.1 "There is no snapshot history / exactly one snapshot per selection" — false

`odds_snapshots` has **517,402 rows over 341,218 combos**. **64,520 combos have
two or more captures**, **56,099 span ≥ 6 hours**, median span 20.85 hours.
Snapshot history exists and is usable. Do not repeat the "one capture" claim.

### 3.2 "CLV is contaminated because the closing fetch is the same fetch" — right effect, wrong mechanism

The contamination is real but not caused by a same-fetch comparison:

- 28,440 predictions have `closing_decimal_odds`.
- **18,650 (65.6%) have closing == source and `clv_percentage` = 0.**
- For those rows the median `closing_odds_at - source_odds_at` is **-0.7
  minutes**, i.e. the "closing" quote predates the entry quote. These are stale
  rows, not valid closes.
- The other 9,790 have a genuine later quote, captured a median **10.05 hours
  before kickoff**, none after kickoff.

So CLV is a *stale forward* measure, not a closing line. It is still
no-lookahead, but the label is wrong and 65.6% of the field is invalid.

### 3.3 "Compare the best quote against the Betway quote" — impossible, and unnecessary

- **No Betway rows exist.** The `odds` table holds 10 books: 1xBet,
  Marathonbet, BetVictor, Bet365, Betano, Betfair, Pinnacle, William Hill, SBO,
  Dafabet.
- More importantly, the recorded entry price is **already the best price across
  those books**: `model_runner._load_odds` sets `best = max(entries, key=decimal_odds)`.

Measured on the Q ≥ 75 universe (`research/bookmaker-price-2026-11-11/`):

| Policy | N | Avg price | ROI | ROI vs recorded |
| --- | --- | --- | --- | --- |
| Recorded entry price | 3,080 | 2.03 | -1.57% | 0.00 pp |
| Best quoted at entry | 3,080 | 2.03 | -1.57% | **0.00 pp** |
| Median quoted at entry | 3,080 | 1.95 | -4.69% | -3.13 pp |

`recorded_price_equals_best_pct = 100.0`. **The margin-shopping lever is already
exhausted.** There is nothing to recover there; the only way to improve the
price is to bet a different selection, not a different book.

### 3.4 "Pre-bet line movement is the cheapest remaining test" — not testable at decision time

Snapshot history exists, but pre-entry movement does not, because of the
pipeline's cadence:

- Predictions are created a median of **8.8 hours before kickoff**
  (p10 -312h from later backfill, p90 38.4h).
- The **first stored pick coincides with the first snapshot** for that
  selection, so it has no prior price by construction.
- Only **1,310 of 17,595** latest pre-kickoff picks (7.4%) have a quote at
  least 1 hour before entry.

A pilot on those 1,310 picks (`research/line-movement-2026-11-11/`) gives a
movement coefficient of **-0.90 (95% CI -2.02 to 0.86, p = 0.79)**: no
evidence, and far too underpowered to call it evidence of absence.

**Conclusion:** movement-before-decision requires re-predicting fixtures as the
line moves (or a cheap "market watch" snapshot tied to a later decision). It is
a data-cadence change, not an analysis job.

### 3.5 Line movement from `odds.opening_odds` — impossible

`odds` holds one row per (match, bookmaker, market, selection), so
`opening_odds` and `movement` are overwritten by the latest fetch. Only
`odds_snapshots` supports movement.

## 4. Where the OpenCode stream was incomplete

### 4.1 The learning loop is stalled, not structurally starved

The last stored run (id 2) says `train_rows: 0`, but the current loader returns
**68,757 train rows** and **19,306 validation rows** for the same windows. The
0 is a stale artefact of the run (the loader now passes the base model version,
not the challenger version). The real problem is downstream:

- **0 predictions have `learning_profile_id`.**
- Every stored profile is `insufficient_evidence` or `validation_rejected`.

So calibration is never applied. The fix is to re-run the challenger job and
then gate promotion on **out-of-sample Brier/log-loss versus the bookmaker**,
not versus the raw model.

### 4.2 `source_implied_probability` is not de-vigged

`model_runner` stores `bundle.avg_implied`, the arithmetic mean of each book's
`1/decimal_odds`. That still contains the overround. Consequences:

- The calibration audit's "bookmaker" Brier is computed from a vigged
  probability, so the market is slightly better than the audit credits.
- `edge = model_probability - implied` is biased downward.
- "Rank by implied probability" is really "rank by vigged implied
  probability"; for ordering within a fixture it is close enough, but it is not
  a fair probability and should not be labelled as one.

### 4.3 The live policy has two design flaws that were not caught

`policy-q75-nodc-v1` activated on 2026-11-11 (18 decisions, 7 qualified). Its
protocol is now frozen in `paper_rule_events`, so it cannot be edited without
failing the digest check. Two problems are visible in the first captures:

1. **The odds floor (1.50) makes `over_1.5` inert.** `over_1.5` has median odds
   1.21; only **2 of 180** Q ≥ 75 picks clear 1.50. It also drops 64% of
   `under_3.5` (157 of 432 eligible). The basket advertises five markets but
   effectively trades three.
2. **Ranking by highest implied probability is a favourite selector, and
   favourites were the worse buckets.** ROI by bookmaker-implied band:
   0-40% **+1.8%**, 40-50% **+0.4%**, 50-60% **-3.2%**, 60-70% **-5.6%**,
   70-80% **-0.9%**. The 7 live picks are all `under_2.5` / `under_3.5` /
   `btts_no`, i.e. the shortest prices in the basket.

The first flaw is a mechanical mismatch; the second is a hypothesis that the
data does not support. Both argue for a **v2 rule**, not an edit to v1.

Also note: the only cell positive in both halves with n ≥ 40 is
`under_4.5 / 1.00-1.49 / chance ≥ 90%` (+2.8%, bootstrap low -4.7%). It is not
in the basket, and its price band is below the odds floor.

## 5. Work queue

Ordered by value per unit of risk. P0 and P1 are correctness; P2 is the
experiment; P3 is product.

### P0 — Make the forward measurement honest (before more picks settle)

- Fix `capture_closing_odds` semantics: a closing quote must be strictly after
  the entry timestamp and at or before kickoff. Add closing timestamp and
  bookmaker to the paper settlement payload; treat missing/invalid as "no CLV"
  rather than zero.
- Store `source_implied_probability` de-vigged going forward (or add a separate
  `source_fair_probability`), keeping the old field for comparability.
- Backfill/invalidate the 18,650 stale CLV rows, or mark them unusable in every
  report. Do not let the policy gate consume them.

### P1 — Restart calibration, with a market-relative gate

- Re-run `train_shadow_challenger`; confirm profiles populate.
- Change promotion to require out-of-sample Brier/log-loss **better than the
  bookmaker** on the same fixtures, plus a non-negative model coefficient in
  the market-relative regression.
- Apply only to forward predictions; never refit on the evaluation window.

### P2 — Pre-register `policy-q75-nodc-v2` (a new rule, not an edit)

Change exactly one thing at a time, and freeze it before the first pick:

- **Odds floor 1.20** (or 1.00) so the basket is actually traded, or drop
  `over_1.5` from the basket.
- **Rank by lowest bookmaker margin / longest price within the allowed basket**
  instead of highest implied probability. This removes the favourite bias and
  tests the direction the implied-band data actually shows.
- Keep Q ≥ 75, one pick per fixture, pre-kickoff quote ≤ 3h, flat 1 unit,
  300 settled / 30 matchdays.

Do not modify v1. Its protocol is already in the ledger, and editing it would
break the integrity check.

### P3 — Product consistency

- Unify the three exclusion lists into one config source, with a documented
  owner and a shadow flag until the paper trial reports.
- Add an opt-in sort by de-vigged market probability on the daily page; keep Q
  as a display field, not the default order.
- Rename or document `best_odds` as "best tracked quote at entry", and expose
  the bookmaker and timestamp.

### P4 — Data cadence (only if P2 shows a pulse)

- Re-predict fixtures as the line moves (or snapshot a decision price later in
  the day) so that pre-decision movement and a true closing line become
  measurable. Without this, CLV and movement will stay weak proxies.

## 6. The strategic answer

**Do not overhaul the model now.** The evidence is that the current model has
no demonstrated information beyond the price, and a rebuild would be an
unvalidated premise. The order is:

1. make the measurement honest (P0),
2. make calibration actually run and be judged against the market (P1),
3. run one clean, pre-registered selection experiment (P2),
4. only then rebuild base models — and only against a market-relative benchmark
   that includes a positive day-cluster coefficient and positive forward CLV.

A rebuild that cannot beat `1/decimal_odds` out of sample is not an
improvement; it is a new way to lose the same money.

## 7. Reproduction

```bash
# inside the backend container
python scripts/bookmaker_price_audit.py --out /tmp/bookmaker_audit
python scripts/line_movement_audit.py --out /tmp/line_movement --selection latest
python scripts/calibration_walk_forward.py --output /tmp/cal-audit
python scripts/market_sweet_spot_backtest.py --selection first --output /tmp/sweet --permutations 200
```

Outputs committed under `research/bookmaker-price-2026-11-11/`,
`research/line-movement-2026-11-11/`,
`research/calibration-audit-2026-11-10/`, and
`research/market-sweet-spot-2026-11-10/first/`.

## 8. Execution status — 2026-11-11

### P0 — complete

- Added `predictions.source_fair_probability` (proportional no-vig) and
  `predictions.closing_bookmaker`; migration `b7c1e2f3a4d5` is applied
  (alembic head).
- `capture_closing_odds` now requires `source_odds_at < closing_odds_at <=
  kickoff_at` and stores the closing bookmaker and timestamp. `clv_is_valid`
  is the single validity predicate.
- `invalidate_stale_clv.py --apply` cleared **15,783** invalid rows. After
  cleanup: **12,657** valid rows, **0** invalid; mean CLV **-0.038%**, beat-close
  **36.5%**, median closing quote **9.94h** before kickoff.
- Paper settlement stores `clv_valid`, `closing_odds_at`, `entry_odds_at`, and
  `closing_bookmaker`; the CLV gate counts only valid observations and reports
  `excluded_invalid`.

### P1 — complete, and rejected

- Added a paired, day-clustered market baseline to `fit_market_challenger`.
  Promotion now additionally requires **both** Brier and log-loss advantages
  over `1/decimal_odds` whose 95% interval lower bound is above zero.
- Fixed the weekly job to clamp the validation window to
  `learning_validation_not_before` instead of skipping until the 30-day lookback
  clears the holdout start.
- Ran challenger `0.3.0-l261110-mktg` with validation **2026-10-25..2026-11-10**
  and train **2026-04-28..2026-10-24**: **72,683** train / **13,016** validation
  rows, 19 market profiles plus shared goals.
- **0 of 19 markets were promoted.** Every Brier/log-loss advantage over the
  price was negative or had an interval straddling zero. The closest market was
  effectively tied: Brier advantage **+0.000257**, interval
  **[-0.003151, 0.003918]**. One market had positive validation ROI and was still
  rejected by the market gate, which is the intended behavior.

### P2 — complete and live

- Added `policy-q75-nodc-v2` as a new frozen rule; v1 was not edited.
- v2 changes two things only: odds floor **1.20** (so `over_1.5` is no longer
  inert) and ranking by **longest entry price** instead of highest implied
  probability. Q remains a universe filter, not a ranking signal.
- First capture: 22 fixtures, **0 qualified**. All 22 were rejected
  `stale_quote_at_capture` because their predictions pre-dated the rule by more
  than the 3h quote limit. Those decisions stay in the ledger; the rule has no
  replacements. Future predictions are captured on the next 5-minute tick after
  creation, so this first-cohort burn is not structural.
- First pulse (2026-11-13): v2 qualified **1 of 25** observed fixtures —
  `under_2.5` at **4.00**, Q 82.1. The remaining first-cohort rejections are
  stale-quote (22) or Q < 75 (22; reasons overlap). One pick is not evidence,
  but it confirms the rule trades.
- Review gates unchanged: 300 settled / 30 matchdays, mean CLV > 0, beat-close
  > 50%, no automatic promotion.

### P3 — complete

- `PRODUCT_RESTRICTED_MARKETS` is now the single config source for
  `research_restricted_markets` and `market_policy_shadow_excluded_markets`.
  `PAPER_POLICY_EXCLUDED_MARKETS` documents the intentionally different frozen
  paper-experiment set. The shadow remains behind `market_policy_shadow_enabled`
  until the paper trial reports.
- The daily All Matches page has an opt-in **Market probability (no-vig)** sort.
  Q remains visible and sortable but is not the default order.
- `best_odds` is documented as the **best tracked quote at entry** (not live,
  not guaranteed), with `source_bookmaker`, `source_odds_at`, and the new
  `source_fair_probability` exposed alongside it.

### P4 — partial (closing-line capture)

P2 showed a first pulse, so the measurement half of P4 is now implemented:
near-kickoff quote refresh now includes **qualified paper-rule picks**, not only
published market tickets. That gives the experiment a genuine closing line
within 3h of kickoff without a global cadence or quota increase.

Pre-kickoff re-prediction and line-movement measurement remain **deferred**:
the entry decision is already frozen, and P1 found no market that beats the
price, so re-predicting would add cost without a measurable decision to
improve.

Two-day health check (2026-11-13):

- Valid CLV rows: **12,753**; mean CLV **-0.030%**; beat-close **36.57%**.
- `source_fair_probability` populated for **592** new predictions since the
  migration; historical rows remain NULL by design (no lookahead backfill).
- v1: 8 qualified, 4 settled (2W 2L). v2: 1 qualified, 1 settled (1W).
- Learning run 3: 18 of 19 profiles carry a market baseline, **0 ready**.

### Forward health check

`backend/scripts/forward_health.py` is read-only (no provider calls, no writes)
and is the standing check for this phase:

```bash
# inside the backend container
python scripts/forward_health.py
python scripts/forward_health.py --json
```

It reports paper-tick age, qualified and settled counts, upcoming picks and
whether closing capture is due, valid/invalid CLV, fair-probability coverage,
the last learning run, and the next scheduled run. It exits non-zero on invalid
CLV, a stale tick, or a post-fix settled pick without valid CLV.

Next operational checkpoints:

1. v1 picks **32916 / 32918** kick off in ~15h; when they enter the 3h horizon,
   `closing_capture_due` should flip and a closing quote should be stored.
2. The weekly learning run fires **2026-11-15 04:30 UTC**; verify it no longer
   skips and still rejects on the market gate.


