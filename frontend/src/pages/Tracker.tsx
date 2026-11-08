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

export default function TrackerPage({ onOpenValidation }: { onOpenValidation?: () => void }) {
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

  return <div className="page-content tracker-page">
    <div className="analytics-hero tracker-hero"><div><span className="eyebrow">Auditable portfolio</span><h1>Tracker</h1><p>Settled paper evidence for every published ticket and selection, plus the frozen prospective experiment.</p></div><span className={`ledger-chip tracker-chip ${evidence}`}><span /> {badge}</span></div>

    <div className="analytics-tabs analytics-subtabs" role="tablist" aria-label="Paper evidence views">
      {([['tickets', 'Ticket history'], ['matches', 'Match outcomes'], ['sweet', 'Sweet-spot test']] as [EvidenceView, string][]).map(([id, label]) => <button key={id} id={`tracker-evidence-tab-${id}`} aria-controls="tracker-evidence-panel" tabIndex={evidence === id ? 0 : -1} role="tab" aria-selected={evidence === id} className={evidence === id ? 'active' : ''} onKeyDown={event => handleArrowTab(event, EVIDENCE_VIEWS, evidence, selectEvidence, 'tracker-evidence-tab-')} onClick={() => selectEvidence(id)}>{label}</button>)}
    </div>
    <div id="tracker-evidence-panel" role="tabpanel" aria-labelledby={`tracker-evidence-tab-${evidence}`} tabIndex={0}>
      {evidence === 'tickets' ? <PaperLedger onOpenValidation={onOpenValidation} /> : evidence === 'matches' ? <MatchHistory /> : <SweetSpotTracker />}
    </div>
  </div>
}