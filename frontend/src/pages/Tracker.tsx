import { useState } from 'react'
import { handleArrowTab } from '../utils/tabs'
import PaperLedger from '../components/PaperLedger'
import MatchHistory from '../components/MatchHistory'
import SweetSpotTracker from '../components/SweetSpotTracker'

type EvidenceView = 'tickets' | 'matches' | 'sweet'
const EVIDENCE_VIEWS: EvidenceView[] = ['tickets', 'matches', 'sweet']
// Older bookmarks used view=matches and view=sweet as top-level tabs, and the
// removed personal tabs used view=accumulators/manual. Everything now lands on
// the matching paper-evidence sub-view.
function evidenceFromLocation(): EvidenceView {
  const view = new URLSearchParams(window.location.search).get('view')
  return view === 'matches' || view === 'sweet' ? view : 'tickets'
}

const tabButtonClass = (active: boolean) =>
  `inline-flex min-h-11 items-center justify-center rounded-md px-4 py-2 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${
    active ? 'bg-white text-emerald-800 shadow-xs' : 'text-slate-600 hover:text-slate-900'
  }`

/**
 * The settled match history can contain thousands of rows. Mounting it only
 * after an explicit disclosure keeps the initial accessibility tree small;
 * the native summary keeps keyboard focus in place when toggled.
 */
export function MatchHistoryArchive({ isInternal }: { isInternal: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="space-y-3" aria-labelledby="match-archive-title">
      <div>
        <h2 id="match-archive-title" className="text-lg font-semibold tracking-tight text-slate-900">Published match archive</h2>
        <p className="mt-1 max-w-3xl text-base leading-relaxed text-slate-600">Older settled match groups are kept in a single archive. It is collapsed by default so the page stays fast and readable; open it to load every year, month and date group with the date filters inside.</p>
      </div>
      <details
        className="rounded-xl border border-slate-200 bg-white overflow-hidden"
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="min-h-11 cursor-pointer border-b border-slate-200 bg-slate-50/70 px-4 py-3 text-base font-semibold text-slate-800 transition-colors hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">
          {open ? 'Hide full match archive' : 'Show full match archive (all settled years)'}
        </summary>
        {open && <div className="p-4"><MatchHistory isInternal={isInternal} /></div>}
      </details>
    </section>
  )
}

export default function TrackerPage({ isInternal, onOpenValidation }: { isInternal: boolean; onOpenValidation?: () => void }) {
  const [evidence, setEvidence] = useState<EvidenceView>(evidenceFromLocation)
  const selectEvidence = (next: EvidenceView) => {
    setEvidence(next)
    const url = new URL(window.location.href)
    if (next === 'tickets') url.searchParams.delete('view')
    else url.searchParams.set('view', next)
    url.searchParams.delete('ticket')
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }
  const badge = evidence === 'sweet' ? 'Prospective paper experiment' : evidence === 'matches' ? 'Published selection evidence' : 'Production paper evidence'

  return <div className="page-content space-y-4">
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <span className="text-sm font-semibold uppercase tracking-wide text-slate-600">Auditable portfolio</span>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Tracker</h1>
        <p className="mt-1 max-w-3xl text-base leading-relaxed text-slate-600">Settled paper evidence for every published ticket and selection, plus the frozen prospective experiment.</p>
      </div>
      <span className="inline-flex items-center gap-2 self-start rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-semibold uppercase tracking-wide text-slate-600 shadow-sm">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" /> {badge}
      </span>
    </div>

    <div className="inline-flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-1" role="tablist" aria-label="Paper evidence views">
      {([['tickets', 'Ticket history'], ['matches', 'Match outcomes'], ['sweet', 'Sweet-spot test']] as [EvidenceView, string][]).map(([id, label]) => <button key={id} type="button" id={`tracker-evidence-tab-${id}`} aria-controls="tracker-evidence-panel" tabIndex={evidence === id ? 0 : -1} role="tab" aria-selected={evidence === id} className={tabButtonClass(evidence === id)} onKeyDown={event => handleArrowTab(event, EVIDENCE_VIEWS, evidence, selectEvidence, 'tracker-evidence-tab-')} onClick={() => selectEvidence(id)}>{label}</button>)}
    </div>
    <div id="tracker-evidence-panel" role="tabpanel" aria-labelledby={`tracker-evidence-tab-${evidence}`} tabIndex={0}>
      {evidence === 'tickets' ? <PaperLedger isInternal={isInternal} onOpenValidation={onOpenValidation} /> : evidence === 'matches' ? <MatchHistoryArchive isInternal={isInternal} /> : <SweetSpotTracker />}
    </div>
  </div>
}
