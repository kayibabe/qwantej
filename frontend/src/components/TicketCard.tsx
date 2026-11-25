import { useState } from 'react'
import type { Leg, Ticket } from '../lib/api'
import { formatKickoff, formatMarket, formatSelection, selectionRepeatsMarket, selectionTone } from '../lib/api'
import GradeBadge from './GradeBadge'
import { fmt } from '../utils/currency'

interface Props {
  ticket: Ticket | null
  tierName: string
  tierDesc: string
  color: string
  research?: boolean
  /** Show internal research language. Product copy is the default. */
  internal?: boolean
  onSelectLeg?: (leg: Leg, ticket: Ticket) => void
  flatStake?: number | null
  showMarketSelections?: boolean
  /** Free plan: the API hides prices, probabilities and selections. */
  locked?: boolean
}

const PCT = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(1)}%`

const formatLegDay = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })

/** Latest leg's kickoff day, e.g. "Sat 26 Sep" — how far a horizon ticket reaches. */
const formatHorizonEnd = (kickoffs: string[]) =>
  formatLegDay(kickoffs.reduce((latest, iso) => (Date.parse(iso) > Date.parse(latest) ? iso : latest)))

const LIVE_PHASE_LABELS: Record<string, string> = {
  '1st_half': '1st Half', half_time: 'Half Time', '2nd_half': '2nd Half',
  extra_time: 'Extra Time', penalties: 'Penalties', suspended: 'Suspended',
  interrupted: 'Interrupted', live: 'Live',
}

function matchStateLabel(leg: Leg): string {
  const status = (leg.match_status ?? '').toLowerCase()
  if (status === 'live' || leg.live_phase) {
    const phase = leg.live_phase ? LIVE_PHASE_LABELS[leg.live_phase] ?? 'Live' : 'Live'
    return `${phase}${leg.elapsed_minutes != null ? ` · ${leg.elapsed_minutes}'` : ''}`
  }
  if (status === 'finished') return 'Finished'
  if (status === 'postponed') return 'Postponed'
  if (status === 'cancelled') return 'Cancelled'
  if (status === 'abandoned') return 'Abandoned · review'
  if (status === 'awarded') return 'Awarded · review'
  if (status === 'scheduled') return 'Upcoming'
  return 'Pending'
}

const toneClass = (tone: string) => tone === 'home' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : tone === 'away' ? 'border-sky-200 bg-sky-50 text-sky-700' : tone === 'draw' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-slate-50 text-slate-600'
const statusBadgeTone = (tone: string) => tone === 'won' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : tone === 'lost' ? 'border-red-200 bg-red-50 text-red-700' : tone === 'void' ? 'border-amber-200 bg-amber-50 text-amber-700' : tone === 'settled' ? 'border-sky-200 bg-sky-50 text-sky-700' : 'border-slate-200 bg-slate-50 text-slate-600'

export default function TicketCard({ ticket, tierName, tierDesc, color, research, internal = false, onSelectLeg, flatStake, showMarketSelections = true, locked = false }: Props) {
  const [legsExpanded, setLegsExpanded] = useState(false)
  const [showAllLegs, setShowAllLegs] = useState(false)
  if (!ticket) {
    return (
      <div className="ticket-card rounded-xl border border-slate-200 bg-white overflow-hidden border-l-4" style={{ borderLeftColor: color }}>
        <div className="px-4 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <div className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
            <span className="text-sm font-bold uppercase tracking-wide" style={{ color }}>{tierName}</span>
            {research && <span className="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-sm font-semibold text-violet-700">Research</span>}
          </div>
        </div>
        <div className="px-4 py-8 text-center space-y-2">
          <div className="text-sm font-semibold text-slate-900">No ticket found</div>
          <div className="text-base leading-relaxed text-slate-600">
            No combination satisfied every {tierName.toLowerCase()} rule ({tierDesc}),
            including distinct-match, odds, and correlation limits.
          </div>
          <span className="inline-block text-sm text-slate-600">Review strongest selections or try another date</span>
        </div>
      </div>
    )
  }

  const marketPriced = ticket.pricing === 'market'
  const evPositive = (ticket.expected_value ?? 0) > 0
  const flaggedLegs = marketPriced ? [] : ticket.legs.filter(leg => leg.edge != null && leg.edge > 0.30)
  const visibleLegs = showAllLegs ? ticket.legs : ticket.legs.slice(0, 4)
  const resultCounts = ticket.legs.reduce<Record<string, number>>((counts, leg) => { const result = leg.result || 'pending'; counts[result] = (counts[result] ?? 0) + 1; return counts }, {})
  const settlementPending = ticket.legs.some(leg => leg.home_goals != null && leg.away_goals != null && (leg.result === 'pending' || !leg.result))
  const pendingLegs = resultCounts.pending ?? 0
  const ticketResult = ticket.result?.toLowerCase()
  const ticketStatusTone = ticketResult === 'won' || ticketResult === 'lost' || ticketResult === 'void'
    ? ticketResult
    : ticket.status === 'settled'
      ? 'settled'
      : 'open'
  const ticketStatusLabel = ticketResult === 'won'
    ? 'Ticket won'
    : ticketResult === 'lost'
      ? 'Ticket lost'
      : ticketResult === 'void'
        ? 'Ticket void'
        : ticket.status === 'settled'
          ? 'Settled'
          : pendingLegs > 0
            ? `Open · ${pendingLegs} pending`
            : 'Published'
  const riskTone = ticket.risk_score == null ? 'text-slate-600' : ticket.risk_score >= 65 ? 'text-red-600' : ticket.risk_score >= 45 ? 'text-amber-700' : 'text-emerald-700'
  const learningReady = ticket.status === 'settled' || ['won', 'lost', 'void'].includes(ticketResult ?? '')
  const roiLearningReady = learningReady && ticket.legs.every(leg => {
    if (!leg.source_odds_at) return false
    return new Date(leg.source_odds_at).getTime() < new Date(leg.kickoff_at).getTime()
  })

  return (
    <div className="ticket-card rounded-xl border border-slate-200 bg-white overflow-hidden border-l-4" style={{ borderLeftColor: color }}>
      <div className="px-4 py-4 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
            <span className="text-sm font-bold uppercase tracking-wide" style={{ color }}>{tierName}</span>
            {research && <span className="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-sm font-semibold text-violet-700">Research</span>}
            {ticket.relaxed_tier && (
              <span
                className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-sm font-semibold text-amber-700"
                title={`Thin match day: tier thresholds were relaxed (level ${ticket.relaxation_level}) to publish a ticket instead of none. Treat grade-mix and Q-score expectations as looser than usual.`}
              >
                Relaxed · Thin Slate
              </span>
            )}
            {(ticket.horizon_days ?? 0) > 0 && ticket.legs.length > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-sm font-semibold text-sky-700"
                title={`Too few fixtures on the ticket date (e.g. an international break), so this ticket also uses games up to ${ticket.horizon_days} day(s) later. Check each leg's kickoff time.`}
              >
                Includes games to <span className="event-date font-mono tabular-nums">{formatHorizonEnd(ticket.legs.map(leg => leg.kickoff_at))}</span>
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${statusBadgeTone(ticketStatusTone)}`}>{ticketStatusLabel}</span>
            {locked
              ? <span className="ticket-lock-badge inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-sm font-semibold text-slate-600">Pro</span>
              : marketPriced
                ? <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-sm font-semibold text-sky-700">Market-priced</span>
                : ticket.legs[0]?.q_grade && <GradeBadge grade={ticket.legs[0].q_grade} />}
            {flaggedLegs.length > 0 && <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-sm font-semibold text-amber-700">Value review · {flaggedLegs.length}</span>}
          </div>
        </div>
        {locked ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <span className="ticket-lock-badge inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-sm font-semibold text-slate-600">Free plan</span>
            <div className="mt-2"><strong className="block text-base font-semibold text-slate-900">Odds, chance and leg evidence are locked</strong><span className="text-base leading-relaxed text-slate-600">Free keeps the published record: match legs, kickoff, score and settlement.</span></div>
          </div>
        ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2" title="Combined decimal odds for every leg">
            <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Ticket odds</span>
            <span className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">{ticket.combined_odds == null ? 'Unavailable' : `${ticket.combined_odds.toFixed(2)}×`}</span>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2" title={marketPriced ? "Estimated joint chance from each bookmaker fair probability, assuming the legs are independent" : 'Estimated ticket probability after the configured correlation adjustment'}>
            <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Estimated chance</span>
            <span className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">
              {ticket.adjusted_probability == null
                ? 'Unavailable'
                : `${(ticket.adjusted_probability * 100).toFixed(1)}%`}
              {marketPriced && ticket.adjusted_probability != null && ticket.adjusted_probability > 0 && (
                <small className="ml-2 text-sm font-medium text-slate-600">about 1 in {Math.max(1, Math.round(1 / ticket.adjusted_probability))}</small>
              )}
            </span>
          </div>
          {marketPriced ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2" title="Estimated long-run return per unit staked at the recorded odds. Negative means below break-even.">
              <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Return / unit</span>
              <span className="mt-1 block font-mono text-xl font-bold tabular-nums text-slate-900">
                {ticket.expected_value == null ? 'Unavailable' : PCT(ticket.expected_value)}
              </span>
            </div>
          ) : (<>
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2" title={flaggedLegs.length > 0 ? 'Provisional expected value: one or more legs require a value review' : 'Expected value based on the recorded model probabilities and odds'}>
            <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Ticket EV</span>
            <span className={`mt-1 block font-mono text-xl font-bold tabular-nums ${flaggedLegs.length > 0 ? 'text-amber-700' : evPositive ? 'text-emerald-700' : 'text-slate-900'}`}>
              {flaggedLegs.length > 0 ? 'Unverified' : ticket.expected_value == null ? 'Unavailable' : PCT(ticket.expected_value)}
            </span>
          </div>
          </>)}
        </div>
        )}
        {ticket.adjusted_probability != null && <p className="text-base leading-relaxed text-slate-600">{marketPriced
          ? 'This estimate multiplies fair leg probabilities and assumes independent legs. It is not a validated joint probability.'
          : 'This estimate uses the model probabilities and a configured correlation adjustment; calibration is ongoing.'}</p>}
        {(flaggedLegs.length > 0 || settlementPending) && (
          <div className="space-y-2">
            {flaggedLegs.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-base leading-relaxed text-amber-800"><strong className="block font-semibold">Value check</strong><span>{flaggedLegs.length} leg{flaggedLegs.length === 1 ? '' : 's'} show unusually large model/odds gaps. Treat edge and EV as provisional until market mapping and odds freshness are checked.</span></div>}
            {settlementPending && <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-base leading-relaxed text-sky-800"><strong className="block font-semibold">Settlement action</strong><span>A final score is available, but at least one market outcome still awaits result ingestion.</span></div>}
          </div>
        )}
        {ticket.publication_timing === 'post_kickoff' && (
          <div className="space-y-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-base leading-relaxed text-slate-700" role="note">
              <strong className="block font-semibold text-slate-900">Historical record</strong>
              <span>This ticket was published after at least one match kicked off. It is a historical record, not a pre-match prediction or upcoming pick.</span>
            </div>
          </div>
        )}
        <button
          className="ticket-summary flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:bg-slate-50 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          type="button"
          aria-expanded={legsExpanded}
          aria-controls={`ticket-leg-list-${tierName.toLowerCase().replace(/\s+/g, '-')}`}
          onClick={() => setLegsExpanded((open) => !open)}
        >
          <span className="text-sm text-slate-700"><span>{legsExpanded ? 'Click to hide legs' : 'Click to expand and view legs'}</span> <strong className="font-mono tabular-nums text-slate-900">{ticket.legs.length} legs</strong></span>
          <div className="flex flex-wrap items-center gap-1.5" aria-label="Leg outcomes">
            {(['won', 'lost', 'void', 'pending'] as const).filter(result => resultCounts[result]).map(result => (
              <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm font-semibold ${statusBadgeTone(result)}`} key={result}><b className="font-mono tabular-nums">{resultCounts[result]}</b> {result}</span>
            ))}
          </div>
          <span className={`text-slate-600 transition-transform ${legsExpanded ? 'rotate-180' : ''}`} aria-hidden="true">⌄</span>
        </button>
        {ticket.settled_at && <div className="text-base text-slate-600">Settled {new Date(ticket.settled_at).toLocaleString()} · {ticket.settlement_source ?? 'system'} · settlement revision {ticket.settlement_version ?? '—'}{ticket.settlement_version && ticket.settlement_version > 1 && <span className="ml-1 inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-sm font-semibold text-amber-700">Corrected settlement</span>}</div>}
        {learningReady && !locked && (
          <div className={`rounded-lg border px-3 py-2 text-sm ${roiLearningReady ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
            <strong className="block font-semibold">{internal ? 'Learning evidence recorded' : 'Result recorded'}</strong>
            <span>{internal
              ? roiLearningReady
                ? 'Probability and pre-kickoff ROI evidence can enter future offline challenger windows; this published ticket remains immutable.'
                : 'Probability evidence can enter future offline challenger windows; ROI learning is excluded where pre-kickoff odds provenance is incomplete.'
              : roiLearningReady
                ? 'This ticket is settled. Its model probability, captured price and result stay on record.'
                : 'This ticket is settled. Where pre-kickoff odds were not fully captured, return figures are left out.'}</span>
          </div>
        )}
        <details className="rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3 text-sm text-slate-700">
          <summary className="min-h-11 cursor-pointer font-semibold text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">Risk, model and publication details</summary>
          <div className="mt-3 space-y-3">
            {locked ? <p className="text-base text-slate-600">Risk, average Q-score and average edge are available on Pro.</p> : <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-2" title="Higher scores indicate a riskier accumulator">
                <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Risk score</span>
                <span className={`mt-1 block font-mono text-lg font-bold tabular-nums ${riskTone}`}>{ticket.risk_score == null ? 'Unavailable' : `${ticket.risk_score.toFixed(0)}/100`}</span>
              </div>
              {!marketPriced && <>
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2" title="Average Q-score across all ticket legs">
                  <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Average Q-score</span>
                  <span className="mt-1 block font-mono text-lg font-bold tabular-nums text-slate-900">{ticket.avg_q_score == null ? 'Unavailable' : ticket.avg_q_score.toFixed(1)}</span>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2" title="Average model edge across all ticket legs">
                  <span className="block text-sm font-medium uppercase tracking-wide text-slate-600">Average edge</span>
                  <span className={`mt-1 block font-mono text-lg font-bold tabular-nums ${flaggedLegs.length > 0 ? 'text-amber-700' : ticket.avg_edge == null ? 'text-slate-900' : 'text-emerald-700'}`}>{flaggedLegs.length > 0 ? 'Review' : ticket.avg_edge == null ? '—' : PCT(ticket.avg_edge)}</span>
                </div>
              </>}
            </div>}
            <div className="flex flex-wrap gap-3 text-sm text-slate-600">
              <span>Version {ticket.version} · model {ticket.model_version}</span>
              <span title={ticket.publication_hash}>Publication hash {ticket.publication_hash.slice(0, 10)}…</span>
            </div>
          </div>
        </details>
        {flatStake != null && ticket.combined_odds != null && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-base"><div><span className="block text-sm uppercase tracking-wide text-slate-600">Flat stake</span><strong className="font-mono text-lg tabular-nums text-slate-900">{fmt(flatStake)}</strong></div><div className="flex flex-wrap gap-4 text-slate-600"><span>Potential return <b className="font-mono tabular-nums text-slate-900">{fmt(flatStake * ticket.combined_odds)}</b></span><span>Potential profit <b className="font-mono tabular-nums text-emerald-700">+{fmt(flatStake * (ticket.combined_odds - 1))}</b></span></div></div>}
      </div>

      <ul hidden={!legsExpanded} className="leg-list divide-y divide-slate-100 border-t border-slate-200" id={`ticket-leg-list-${tierName.toLowerCase().replace(/\s+/g, '-')}`}>
        {visibleLegs.map((leg) => (
          <li key={leg.prediction_id} className="leg-item">
            <button className="flex min-h-11 w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50/70 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-emerald-700 disabled:cursor-default" onClick={() => onSelectLeg?.(leg, ticket)} disabled={!onSelectLeg}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-900">
                  {leg.home_team}
                  <span className="text-slate-600 font-normal"> vs </span>
                  {leg.away_team}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-slate-600">
                  <span>{leg.competition}</span>
                  <span className="leg-time kickoff-date font-mono tabular-nums" aria-label={`Match date ${formatLegDay(leg.kickoff_at)}`}>
                    {formatLegDay(leg.kickoff_at)}
                  </span>
                  <span className="leg-time kickoff-time font-mono tabular-nums" aria-label={`Kickoff time ${formatKickoff(leg.kickoff_at)}`}>
                    {formatKickoff(leg.kickoff_at)}
                  </span>
                  <span
                    className={`match-state-badge inline-flex items-center rounded-full border px-2 py-0.5 font-semibold ${(leg.match_status ?? 'pending').toLowerCase() === 'live' || leg.live_phase ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : (leg.match_status ?? '').toLowerCase() === 'finished' ? 'border-slate-200 bg-slate-100 text-slate-700' : 'border-slate-200 bg-slate-50 text-slate-600'}`}
                    aria-label={`Match state ${matchStateLabel(leg)}`}
                  >
                    {matchStateLabel(leg)}
                  </span>
                  {leg.home_goals != null && leg.away_goals != null && <span className="live-score-badge inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono font-semibold tabular-nums text-slate-900" aria-label={`Score ${leg.home_goals} to ${leg.away_goals}`}>{leg.home_goals}–{leg.away_goals}</span>}
                  {showMarketSelections && <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-semibold ${toneClass(selectionTone(leg.selection))}`}>{selectionRepeatsMarket(leg.market, leg.selection) ? formatSelection(leg.selection) : `${formatMarket(leg.market)}: ${formatSelection(leg.selection)}`}</span>}
                </div>
                <div className="mt-2 text-sm">
                  <span className="text-slate-600">Pick </span>
                  <strong className={`font-semibold ${leg.result === 'won' ? 'text-emerald-700' : leg.result === 'lost' ? 'text-red-600' : leg.result === 'void' ? 'text-amber-700' : 'text-slate-600'}`}>{leg.result === 'pending' ? (leg.home_goals != null && leg.away_goals != null ? 'Settlement pending' : 'Pending') : leg.result === 'won' ? 'Won' : leg.result === 'lost' ? 'Lost' : 'Void'}</strong>
                </div>
              </div>
              <div className="shrink-0 text-right text-sm">
                {locked ? <span className="ticket-lock-badge inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-sm font-semibold text-slate-600">Pro</span> : <>
                <span className="block font-mono text-sm font-bold tabular-nums text-slate-900">{leg.best_odds == null ? 'Unavailable' : `${leg.best_odds.toFixed(2)}×`}</span>
                {marketPriced ? (
                  leg.model_probability != null && <span className="block font-mono tabular-nums text-slate-600">{(leg.model_probability * 100).toFixed(0)}% chance</span>
                ) : (<>
                {leg.edge != null && (
                  <span className={`block font-mono font-semibold tabular-nums ${leg.edge > 0.30 ? 'text-amber-700' : leg.edge > 0 ? 'text-emerald-700' : 'text-slate-600'}`}>{PCT(leg.edge)} edge</span>
                )}
                {leg.edge != null && leg.edge > 0.30 && leg.best_odds != null && leg.best_odds > 1 && <span className="block text-sm text-amber-700">Implied {(100 / leg.best_odds).toFixed(0)}% · review</span>}
                <span className="block font-mono tabular-nums text-slate-600">{leg.q_score == null ? 'Q —' : `Q ${leg.q_score.toFixed(1)}`}</span>
                </>)}
                {!marketPriced && <span className={`block text-sm ${leg.model_agreement == null ? 'text-slate-600' : leg.model_agreement <= 0.05 ? 'text-emerald-700' : leg.model_agreement <= 0.10 ? 'text-slate-600' : leg.model_agreement <= 0.15 ? 'text-amber-700' : 'text-red-600'}`}>Spread {leg.model_agreement == null ? '—' : `${(leg.model_agreement * 100).toFixed(1)} pp`}</span>}
                </>}
              </div>
              {onSelectLeg && <span className="self-center text-slate-300" aria-hidden="true">›</span>}
            </button>
          </li>
        ))}
      </ul>
      {legsExpanded && ticket.legs.length > 4 && (
        <button className="ticket-expand flex min-h-11 w-full items-center justify-center gap-2 border-t border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-emerald-700" onClick={() => setShowAllLegs(value => !value)} aria-expanded={showAllLegs} aria-controls={`ticket-leg-list-${tierName.toLowerCase().replace(/\s+/g, '-')}`}>
          {showAllLegs ? 'Show fewer legs' : `View all ${ticket.legs.length} legs`}
          <span aria-hidden="true">{showAllLegs ? '↑' : '↓'}</span>
        </button>
      )}
    </div>
  )
}
