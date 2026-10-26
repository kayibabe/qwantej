# Qwantej GUI, UX and information-flow implementation

Date: 25 October 2026 (Africa/Blantyre)

This note records the first implementation pass based on [`GUI_UX_INFORMATION_FLOW_AUDIT_2026-10-25.md`](GUI_UX_INFORMATION_FLOW_AUDIT_2026-10-25.md). It addresses the highest-impact information-flow, loading, scope and clutter findings. It is not a claim that every audit recommendation or every role journey is complete.

## Implemented

- The shared daily page requests data for its active route and tab. Today no longer fetches candidate, rejection, custom-accumulator or ROI datasets. Polling pauses while the tab is hidden; background refresh does not replace the page with a skeleton; obsolete responses are ignored.
- Candidate selections are paginated in batches of 100. The API returns a total count and stable ordering. Matches and Acca Analysis expose a load-more action. Admin Matches now states that it intersects the daily ROI market set with the Q-score candidate feed (Q≥75); the ROI report can include lower-Q selections outside this list.
- Heavy Today/Matches/Research panels load on demand. The production build splits Matches, Acca Analysis, fixture exploration, ROI reports, policy review and published selections into separate chunks. The built Today-specific JS payload (entry plus daily page chunks) is 78.73 kB gzip versus 92.95 kB gzip in the audit build, about 15% lower by asset-size sum. This is a bundle-size comparison, not a browser latency benchmark.
- Matches presents advanced numeric filters and saved views inside “More filters and saved views”, and uses a sort selector with one direction control. The unfiltered featured-candidate panel was removed from above the result list.
- Acca Analysis labels the stored model rating separately from current price/data/fixture eligibility. Ticket suggestions continue to use current eligibility gates.
- Research subviews are reflected in `?tab=` and switch without remounting the daily page. Tracker view, selected accumulator, and date are reflected in the URL. Adding an accumulator opens that saved record in Tracker. “Choose picks” opens Research Candidates. Match Intelligence retains the originating route/query and selected prediction, and its back action follows browser history when available.
- Pro users can open authorized Match Intelligence routes; admin routes remain protected. Route rendering failures now show a recoverable page-level message while keeping the app navigation shell. Route changes focus the main content for keyboard and assistive-technology users.
- Analytics defaults to the current model, supports an explicit `all` scope, avoids refetching pipeline status on filter edits, and retains the last successful report if a refresh fails. Performance summary selects the latest ticket version before applying the model filter, matching the ledger's cohort ordering.
- Removed the verified-unused `DateNav.tsx`, `LegRow.tsx`, and `RunModelModal.tsx` components, the commented legacy candidate JSX, and styles for the removed featured-candidate panel. No exact duplicate source files were identified in the audit; compatibility barrels and historical evidence files were retained.
- Updated the existing UI tests to assert current labels and actual progressive-disclosure interactions, rather than the old static markup. Rejection reasons are tested after opening their dialog; long-ticket legs are tested through both expansion steps.
- Connected Tools calculator labels to their fields and named each accumulator leg input. Rejection-reason and Acca Analysis dialogs now keep keyboard focus inside while open and return focus to their trigger when closed.
- Analytics and Tracker tabs now use associated tab panels, roving tab stops, and Left/Right/Home/End keyboard navigation.
- The daily page always starts its initial data request, even in a background tab; visibility only pauses later polling. This fixes a route that could otherwise remain on its loading skeleton until the tab became visible.

## Verification

- `rtk npm run build`: passed; 84 modules transformed. Today-specific JS chunks: `DailyTickets` 4.32 kB / 1.65 kB gzip and `DailyTicketsPage` 60.12 kB / 17.19 kB gzip.
- `rtk npm test -- --run`: 49 passed across 11 files. The prior audit baseline was 42 passed / 7 failed; all 7 stale assertions were updated to cover the current visible labels and disclosure interactions without changing product behavior to match obsolete expectations.
- Backend tests for daily ticket API, paper-ticket flow and recommendation ledger: 5 passed, 1 skipped.
- `rtk git diff --check`: passed.
- Rebuilt and restarted only the local `qwantej-backend-1` container, which serves the frontend bundle. Readiness returned healthy; the database and other containers were not restarted.
- In the existing authenticated browser session, Today rendered the current published selections and Matches rendered 100 of 188 candidate selections across 4 matches, with the compact filters and disclosure visible. This confirms the current UI flow; it is not a cold/warm latency benchmark.

## Follow-up work proposed in the initial pass

- Complete keyboard and screen-reader review across remaining route tabs and dialogs; unify remaining dialog behavior with a shared primitive.
- Reconcile the remaining primary-navigation and Analytics scope state into deep links; preserve authorized login return destinations.
- Verify the responsive shell at 390 px and 1280 px with an authenticated session; consolidate the mobile account/theme controls.
- Migrate the document-wide DOM table sorter to typed React sorting one table at a time, with refresh/navigation coverage.
- Profile the ROI and performance endpoints against a representative database before changing SQL projections, caching or query limits. No latency target is claimed until a cold/warm baseline is measured.
- Complete the full authenticated task journey from Today through match evidence, a saved draft, Tracker and validation. Only Today and Matches were visually checked after the live rebuild.
- Profile the Matches first-load query and browser timing before setting a page-load target; the authenticated screen rendered, but it took long enough that a performance baseline is still needed.

No publication, qualification policy, saved ticket, result, database record or external service was changed. Existing frozen-score-cohort work and evidence files were preserved.

## Follow-up audit pass — 25 October 2026

- Completed an authenticated read-only route journey through Today, Matches, the Phoenix Rising vs Lexington evidence drawer and Match Intelligence return path, Tracker's paper ledger and personal accumulators, Validate's performance and recommendation ledger views, Tools, and Admin. The Admin status panels resolved after their initial loading state; the API requests returned successfully.
- Tracker contains 19 personal accumulators: 1 open and 18 settled. None is an unplaced draft. I did not create a persistent test draft, so the saved-draft create/edit/return path remains unverified and no ledger rows were added for this audit.
- Reviewed the accessibility tree on the sampled routes. Evidence tabs, Tracker tabs, and Analytics tabs expose selected state and associated panels; keyboard navigation was verified for Evidence and the shared tab pattern. Tools inputs expose labels, and the dialogs preserve focus. This is an AX tree and keyboard review, not a full manual NVDA/JAWS screen-reader certification.
- At 390 px, Matches, the evidence drawer, Tracker, and Validate were visually reviewed. Their document root and body widths matched the 375 px layout viewport (the remaining 15 px is the browser scrollbar), with no page-level horizontal overflow. Match/Tracker/Validate tab strips use their own horizontal scrollers. Today was visually reviewed at 1280 px. The temporary viewport override was reset afterward.
- Profiled representative service calls against the local database using three sequential runs per service. Candidate selection batches of 100 took 515–731 ms; the daily ROI report took 1,910–2,106 ms before projection changes; current-model performance summary took 37–106 ms; and the 379-row recommendation ledger took 143–237 ms. These are service timings from a local process, not full HTTP, browser-render, or network timings.
- Measured three authenticated Chrome Matches reloads at the restored normal viewport, stopping when the 100-of-188 candidate count appeared. Results were 1.84–2.10 s (median 2.05 s). This is a small same-machine reload sample with warm browser assets; it is not a cold-start baseline or a p95 estimate.
- The ROI history query returned 968 prediction rows before deduplication while the calculation used only a subset of each prediction and match record. Narrowed both the historical and target-date ORM projections with `load_only`, retaining all fields used by qualification, settlement, provenance, and display. Three post-change runs returned the same 686 historical unique selections, 16 candidates, and 4 qualifying markets in 602–742 ms (median 705 ms, about 66% below the pre-change median of 2,077 ms). The backend was restarted and `/health/ready` returned `ready` with database and Redis healthy.
- No hard load-time target is set from service timings alone. A browser cold/warm p50/p95 baseline, including serialization and rendering, is still needed before establishing page-load budgets.

### Remaining audit work

- Exercise saved-draft creation and return with an isolated disposable account/database. The current user's tracker has no draft, and creating a persistent test row would pollute the live personal ledger.
- Finish a broader keyboard-only and screen-reader pass over every route, dialog, and long table. This pass sampled the main tabs, evidence drawer, Tools fields, and Admin status but did not certify every control.
- Extend browser timing to a defined cold/warm setup with enough runs for useful p50/p95 across Today, Matches, Tracker, and Validate. The three Matches reloads are only an initial local sample.
- Continue the planned migration from document-wide table sorting to typed React sorting with refresh and route-navigation coverage.

Existing frozen-score-cohort work and evidence remain intact. No publication, qualification policy, saved ticket, result, account, or external service was changed during this follow-up.

## Final audit follow-up — 25 October 2026

- Completed the authenticated draft journey in a disposable PostgreSQL clone. Added a candidate from Matches, confirmed the new draft opened in Tracker, added a second leg, removed and restored it to exercise edits, and reloaded Tracker to confirm both immutable snapshots returned with combined odds of 5.87. The live `lohela` database was not written. The draft could not be marked placed without a stake.
- The journey uncovered an async ORM serialization defect in `PATCH /custom-accumulators/{id}`: the update committed, then response serialization tried to lazy-load `leg.match` and raised `MissingGreenlet` (HTTP 500). Updated the route to eager-load match data and refresh the identity-map collection after the update. Retested both remove and add operations through the authenticated UI; each returned successfully and the saved draft persisted after reload.
- Broadened the keyboard and accessibility-tree review across Today, Matches and candidate details, evidence tabs/drawer, Tracker tabs and accumulator history, Validate performance and recommendation ledger, and the nested research-method tabs. Controls expose accessible names and selected/expanded/disabled states in the browser accessibility tree; tab arrows and Escape/focus return were checked in the sampled flows. This is a browser accessibility-tree and keyboard review, not certification with NVDA or JAWS speech output. The Tracker history exposed about 2,000 AX nodes for the 19 pre-existing accumulators plus the disposable draft; consider collapsing older settled periods by default to reduce navigation overhead.
- Collected authenticated same-machine reload samples with normal viewport and warm browser assets, timing from reload to the data-ready marker: Today 8 runs, 1.43–2.27 s (median 1.66 s); Matches 8 runs, 2.67–6.22 s (median 5.04 s); Tracker 4 runs, 1.19–2.19 s (median 1.36 s); Validate 8 runs, 1.24–2.27 s (median 1.50 s). Matches is the current end-to-end outlier. These runs use the cloned database and are warm reloads; browser cache clearing and a true cold-start profile were not available in this setup, and 4–8 samples per route do not support a useful p95 or hard budget.
- The earlier service-level ROI improvement remains unchanged: median local daily ROI service time fell from 2.077 s to 0.705 s with the same result counts. Keep load-time targets provisional until a defined cache-cleared and cold-process profile is collected on representative hardware/network conditions. In particular, profile the Matches endpoint breakdown next; this browser sample indicates more cost than the candidate service timing alone.
- Removed the disposable audit backend and Redis container and dropped only `qwantej_audit_20261025`. The original local backend still reports readiness with database and Redis healthy.

The saved-draft return journey is verified. The remaining qualification is a manual assistive-technology speech pass (NVDA/JAWS) and a cache-cleared cold-start timing run; no hard load-time target is claimed. Existing frozen-score-cohort work and evidence remain intact.

## Accessibility and Matches profiling follow-up — 25 October 2026

- Revisited the authenticated Matches screen in a separate read-only browser tab. Its accessibility tree exposes the navigation and route tabs, selected date, candidate totals, search and competition filters, sort control, status filters, settled-result summary, collapsed match cards and the “Load next 100 candidates” action with names and states. This is a spot review of the Matches screen, not a speech-output review.
- Reviewed the Matches request flow in `DailyTicketsPage.tsx`: the qualified-candidate and custom-accumulator requests start together in the route loader, while the daily market-ROI request starts concurrently in the background. The admin candidate list stays gated until the ROI response resolves; candidate data is committed after the candidate and custom-accumulator requests both resolve. This gives a likely request-level explanation for why candidate content can appear late, but it is not a measured browser waterfall. Existing local service timings were about 0.5–0.7 s for the candidate batch and a 0.6–0.7 s median for the optimized daily ROI service; the 5.04 s warm Matches browser median is materially higher.
- The browser automation interface does not expose page Performance entries or request events, so this pass produced no valid cache-cleared timing sample and no endpoint-by-endpoint browser waterfall. A quick reload probe returned the already-rendered candidate marker immediately and was discarded as stale content, not counted as a measurement. The Chrome profile was not cleared.
- Narrator was available and started, but its UI ran at a higher Windows integrity level than the controller and the attempted NVDA launch timed out. No speech was captured or certified. The NVDA installer downloaded from NV Access’s official stable release page was removed from the temporary directory; it was not installed.
- Older settled accumulator history remains expanded as before. The earlier recommendation to group it under an accessible, collapsed-by-default “Older settled” disclosure is still open; no change was made without a verified assistive-technology pass on the summary and focus behavior.

The manual speech review, cold-start profile, request waterfall, and collapsed-history decision remain open. Do not set a hard load-time target from the existing warm reload samples.
