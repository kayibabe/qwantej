# Qwantej GUI, UX, and information-flow audit

**Date:** 2026-10-20  
**Workspace:** `D:\WebApps\qwantej`  
**Type:** Audit with local implementation follow-up; no production behavior or stored records changed.

## Scope and evidence

Reviewed the shared React shell and route flow, plus the authenticated live screens for Today, Matches, Live, Stats & trends, Research (Market ROI, Daily Match Picks, Research Policy), Track (Paper ledger), Validate (Performance), Tools, Admin, and a selection-to-Match-Intelligence drilldown. Cross-checked those screens against the relevant frontend components and data-flow code.

The live review used the running local Qwantej app at `127.0.0.1:8001` with the signed-in admin account on 2026-10-20 around 12:42–12:45 Africa/Blantyre. The public landing/login flow, free-user permissions, mobile breakpoints, keyboard-only use, and screen-reader behavior were not reviewed in this pass. This is a product and information-flow review, not a full backend rules audit or accessibility certification. No tests were run because no implementation change was requested.

## Executive view

Qwantej has useful trust foundations: paper/research scope is stated in several places, published records are described as immutable, Match Intelligence exposes timestamps and risks, and Research Policy correctly displays zero matches when its evidence gate fails. The main problems are that screens mix several decision populations, some status language implies fresher or more specific evidence than it represents, and one drilldown loses the selected market context.

**Overall assessment:** usable for an experienced internal researcher who already knows the system’s vocabulary; harder than necessary to answer three basic questions quickly: *What is this record? How current is its evidence? What should I inspect next?*

## Findings

### P1 — Match Intelligence drops the selected market on drilldown

From the Bristol Rovers–Salford City Away Win evidence panel, the user sees 67.9% model probability, odds 2.64, Q 79.5, and a 4-hour-old snapshot. Selecting **Open match intelligence** opens the correct match, but the destination summary leads with Double Chance (X2), 87.9%, odds 1.52, Q 83.5. The full table contains both markets, but the top summary no longer describes the selection the user followed.

The selection detail passes only `match_id`; Match Intelligence then unconditionally chooses `predictions[0]` as its lead. This is a real loss of context and can make the user think the selected evidence changed.

**Recommendation:** carry `prediction_id` (or a stable market/selection key) into the route and select that row as the primary summary. Keep “best ranked market for this match” as a separate, explicitly named option. Show the source selection and its timestamp at the top of the destination.

**Code:** [SelectionDetail.tsx](/D:/WebApps/qwantej/frontend/src/components/SelectionDetail.tsx:214), [App.tsx](/D:/WebApps/qwantej/frontend/src/App.tsx:285), [MatchIntelligencePage.tsx](/D:/WebApps/qwantej/frontend/src/pages/MatchIntelligencePage.tsx:36).

### P1 — Global “Refreshed” time does not prove the data was refreshed

The shared header labels a locally initialized `lastUpdated` value as “Refreshed”. The refresh button updates that value immediately before a page reload; the label is not attached to the success time of any API request. It is present across pages whose data has different refresh behavior. A user can read it as confirmation that displayed evidence is current even if a request failed or a view’s own data has an older timestamp.

**Recommendation:** remove the global freshness claim. Show a data timestamp per module, tied to the latest successful response, with a visible stale/error state. Keep “last page reload” only if it is labeled as such.

**Code:** [App.tsx](/D:/WebApps/qwantej/frontend/src/App.tsx:92), [App.tsx](/D:/WebApps/qwantej/frontend/src/App.tsx:271).

### P1 — Admin health summary conflicts with the visible published-ticket state

At the same observation time, Today showed eight published picks across three upcoming tickets, while Admin’s **Recommendation quote coverage** said “No upcoming recommendations.” The intended population may differ, but the interface does not define that population, so these adjacent system views appear contradictory. Admin also showed freshness as “Current” while the selection drilldown surfaced a 4-hour-old odds snapshot; those statuses may use different freshness contracts and need an explicit definition.

**Recommendation:** define the exact population and age threshold behind each operational metric, and use the same words in the ticket and Admin views. If a health measure covers a different set (for example, model recommendations rather than published ticket legs), label that set directly. Add links from a non-current status to the affected records.

**Evidence:** live Today, Admin, and selection-detail screens; Admin quote-coverage rendering is in [Admin.tsx](/D:/WebApps/qwantej/frontend/src/pages/Admin.tsx:250).

### P1 — Admin alerts are hard to triage at the point of use

Admin showed ten active alerts alongside a completed latest pipeline. The list contained a live-status provider failure repeated 403 times, one settlement lock timeout, and repeated past-date scoring rejections. These appear as individual alert rows with a generic **Resolve** action. The screen does not bring the most recent occurrence, age, affected workflow, or whether the condition is still recurring into the summary.

**Recommendation:** group repeated alerts by job and error signature; show severity, first/last seen, occurrence count, current/cleared state, and one next action. Separate expected guardrail rejections from infrastructure/provider failures. Keep the latest completed run visible as recovery evidence.

**Code:** [Admin.tsx](/D:/WebApps/qwantej/frontend/src/pages/Admin.tsx:350).

### P2 — The same header context is repeated outside its useful scope

The daily shell exposes “508 strict candidates · Published 07:58 · Model 0.3.0” on Today, Matches, and Research. On Matches the visible market-qualified set is four; on Research Policy there are zero qualifying matches. The 508 number may describe the broader publication pool, but without a definition or scope label it competes with the local result count and can be mistaken for the size of the active list.

**Recommendation:** keep the global header focused on page identity and date. Put publication/model provenance beside the ticket record it describes; put candidate-pool counts in the relevant research summary with a short definition and a link to the population.

**Code:** [DailyTicketsPage.tsx](/D:/WebApps/qwantej/frontend/src/pages/dailyTickets/DailyTicketsPage.tsx:308).

### P2 — Today repeats pick information before the ticket-level records

Today displays eight unique published selections first, then shows all three ticket tiers with their full legs and outcomes. This supports two useful questions—“which distinct picks appeared?” and “what was published in each tier?”—but requires a long scroll and repeats match/selection content. Ticket totals, chance, expected return, and leg lists compete with the pick-level status above them.

**Recommendation:** retain both views but make the relationship navigable: show a compact pick list with tier badges and one “open ticket” path; make full tier leg details collapsible or let the user switch between **Picks** and **Ticket tiers**. Keep return/probability explanations available beside the figures.

**Evidence:** live Today screen; the unique-pick list is rendered by [PublishedSelections.tsx](/D:/WebApps/qwantej/frontend/src/pages/dailyTickets/PublishedSelections.tsx:52), then the tier totals are rendered later in [DailyTicketsPage.tsx](/D:/WebApps/qwantej/frontend/src/pages/dailyTickets/DailyTicketsPage.tsx:513).

### P2 — Research pages front-load too many counts and thresholds

Market ROI places a long gate explanation, six summary values, a grouped fixture-outcome summary, another detailed methodology note, and a sortable market table in one flow. The live table showed markets with 3, 6, and 8 observations labeled “Meets both gates” while also labeling them “very small sample.” The wording is technically consistent with the two configured thresholds but visually gives the pass state more weight than the evidence-size warning.

**Recommendation:** make the research question and selected-date result the first layer. Put gate details behind a concise “How qualification works” disclosure. Style “Meets formula” separately from evidence strength, and keep sample size/confidence adjacent to ROI. Do not alter the configured gate based on this UX audit; any sample-size rule is a research-policy decision requiring its own evidence review.

**Code:** [MarketRoiDaily.tsx](/D:/WebApps/qwantej/frontend/src/pages/dailyTickets/MarketRoiDaily.tsx:126).

### P2 — Daily Match Picks is too wide for its table hierarchy

The live table combines kickoff, match, competition, pick, odds/bookmaker, Q/grade, historical hit rate, ROI, history, quote timestamp/age, and result. At the desktop viewport, column headings visibly wrap into narrow fragments. Users must scan several historical and quote columns before reaching the live match context.

**Recommendation:** keep match, pick, odds/source, Q, and current status in the first view. Put historical sample and quote provenance into a clearly labeled expandable row or detail panel. Preserve sort/filter access, and test a narrow viewport after restructuring.

**Evidence:** Daily Match Picks rendered table at the live desktop viewport; table implementation is in [MarketRoiDaily.tsx](/D:/WebApps/qwantej/frontend/src/pages/dailyTickets/MarketRoiDaily.tsx).

### P2 — The calculator language turns user-entered assumptions into advice

Tools correctly calls the calculators “what-if” scenarios and says they do not change the ledger. Inside the Kelly and expected-value calculators, however, the default choice is “Half Kelly (recommended)” and a positive user-entered probability produces “+EV — bet has value.” Those outputs do not show uncertainty in the supplied probability or tie the assumed price/probability to a verified Qwantej record.

**Recommendation:** label the probability as user-supplied, rename the default “Half Kelly” without a recommendation, and describe positive EV as “positive under these inputs.” Keep this distinct from any system decision or paper-record status.

**Code:** [Tools.tsx](/D:/WebApps/qwantej/frontend/src/pages/Tools.tsx:27), [Tools.tsx](/D:/WebApps/qwantej/frontend/src/pages/Tools.tsx:46), [Tools.tsx](/D:/WebApps/qwantej/frontend/src/pages/Tools.tsx:225).

### P3 — Tracker opens into a long chronological ledger without a summary

Paper ledger is the default Track view and renders repeated tier cards for successive dates. Filters exist, and each cohort can be expanded, but the first impression is a long chronological list rather than the result of a user’s question (what settled, what is pending, and how much evidence is covered).

**Recommendation:** add a compact date-range summary above the ledger, default to a recent range or paged cohorts, and retain explicit filter chips and total counts. Keep the existing immutable-record drilldown.

**Code:** [PaperLedger.tsx](/D:/WebApps/qwantej/frontend/src/components/PaperLedger.tsx:183).

## Good patterns to keep

- Research Policy reports zero matches when its frozen evidence gate fails and explains why.
- Match selection evidence exposes the quote timestamp, stale state, disagreement, and risks.
- Live monitoring distinguishes the page’s last check from the upstream provider timestamp and says alerts only run while the page is open.
- Validation shows settlement coverage and a confidence interval near hit rate, and separates personal accumulator performance from published-ticket performance.
- The workspace separation and page names (Research, Track, Validate) are a useful information architecture; the main opportunity is simplifying what each page leads with.

## Recommended implementation order

1. Preserve selected prediction context in Match Intelligence and clarify stale/freshness semantics across shell, selection, and Admin.
2. Reconcile the Admin quote-coverage and freshness population labels with the published-ticket view; make alerts grouped and actionable.
3. Reduce repeated header/context and daily pick/tier duplication through a simple pick-to-ticket handoff.
4. Rework Market ROI and Daily Match Picks into a short result-first layer with optional methodology and evidence detail.
5. Rephrase calculator outputs and give Tracker a summary-first entry.

## Resolution record (2026-10-20)

The following UX and information-flow recommendations were implemented in the local Qwantej checkout without changing recommendation gates, model decisions, publication records, or historical evidence:

| Finding | Resolution |
| --- | --- |
| Selected market lost on Match Intelligence drilldown | The route carries `prediction_id`; the destination leads with that stored market, highlights its row, and shows the selected prediction ID and captured-odds time. If it is unavailable, the page says it is falling back to the top stored market. |
| Global freshness claim | Removed the shell-wide “Refreshed” clock. The action is now labeled “Reload”; the ticket page reports when its own data loaded. |
| Admin population and freshness ambiguity | Admin labels the scheduled-prediction freshness and RECOMMEND quote-coverage populations, lookahead, and quote-age limit. It explicitly says published ticket legs are tracked separately and links stale or uncovered records to their selected Match Intelligence snapshot. |
| Alert triage overload | Alerts are grouped by job and matching title/detail, with severity, record and occurrence counts, last-seen time, and expandable per-record detail including first/last seen and a resolve action. Past-date scoring guardrail rejections are labeled separately. |
| Repeated publication context | Publication-pool and model context is confined to the published-ticket view and labels the candidate population. |
| Duplicate pick and ticket detail | The unique-pick list remains first, with tier context on each pick; full immutable ticket tiers and legs are collapsed by default. Stake output is explicitly described as illustrative. |
| Research overview overload | Market ROI now leads with four scoped counts; gate methodology and grouped fixture outcomes sit in a disclosure. Formula qualification has neutral styling and per-market evidence labels remain visible. |
| Wide Daily Match Picks table | The first view keeps kickoff, match, pick, odds/source, Q/grade, result, and a compact evidence disclosure. Minimum-Q and grade filters remain, and sorting retains access to historical hit rate, ROI, and sample size. |
| Calculator assumptions read as advice | Inputs are labeled as assumptions; Kelly is no longer called recommended; outputs are conditional on entered inputs and disclose missing uncertainty/calibration/quote checks. |
| Tracker chronology overload | The ledger now starts with filtered cohort/settlement/P&L summaries, opens only the latest year, and keeps months collapsed while retaining the existing cohort drilldown. |

**Current verification:** `npm run build` passed (TypeScript and Vite), and `python -m py_compile` passed for the operational monitor. The supervised local Qwantej Compose runtime rebuilt and returned healthy. The authenticated local browser showed the revised Admin metric labels and grouped alerts, the four-card Market ROI overview, the condensed Daily Match Picks rows, the published selection-first ticket view with full tiers collapsed, and the Tracker summary cards. The selected prediction handoff was followed end to end: the URL retained `prediction_id`, the expected market led the page, its odds capture time appeared in the header, and its row was highlighted. Historical hit-rate, ROI, and sample-size sorting controls were expanded and used successfully. At 390 × 844, Daily Match Picks reflowed into labeled stacked rows with usable content. The Admin API/UI zero-state loaded successfully after adding conditional record links; no affected rows existed at observation time, so those links were not exercised. No automated tests were run.

**Still outside this implementation pass:** backend correctness of the existing metric calculations, full-app mobile/tablet behavior beyond the Daily Match Picks check, free-role behavior, keyboard/screen-reader use, and WCAG conformance. These remain contract and accessibility review items rather than changes to evidence or recommendation policy.

## Verification boundary

**Verified:** listed screens were rendered in the authenticated local app; the selected-market handoff mismatch and displayed freshness/alert states were observed; cited frontend components support the described behavior.  
**Not verified:** whether Admin’s “No upcoming recommendations” and “Current” values are incorrect at the backend contract level, whether historical small-sample qualification is intended policy, mobile/tablet behavior, free-role behavior, and WCAG conformance. Resolve those through contract review and focused browser/accessibility checks before changing policy or declaring compliance.
