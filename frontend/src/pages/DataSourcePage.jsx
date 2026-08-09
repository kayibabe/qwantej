import { useState, useEffect } from 'react'
import { Layers, CheckCircle, XCircle, ChevronDown, ChevronRight } from 'lucide-react'
import { fetchDataSources } from '../api/data_sources'
import LoadingSpinner from '../components/shared/LoadingSpinner'

// ── Source display names + descriptions ───────────────────────────────────────

const SOURCE_META = {
  football_data_co_uk: {
    label: 'Football-Data.co.uk',
    desc: 'Historical match results, half-time scores, bookmaker odds back to early 2000s. Primary results warehouse.',
    color: 'text-blue-400',
    border: 'border-blue-500/30',
    bg: 'bg-blue-500/5',
  },
  statsbomb: {
    label: 'StatsBomb Open',
    desc: 'Event-level xG and shot data for selected competitions. Enriches ZINB model with expected goals.',
    color: 'text-purple-400',
    border: 'border-purple-500/30',
    bg: 'bg-purple-500/5',
  },
  openfootball: {
    label: 'OpenFootball / OpenLigaDB',
    desc: 'Community-maintained fixtures and results. Used for coverage gaps in less-documented leagues.',
    color: 'text-emerald-400',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/5',
  },
  api_football: {
    label: 'API-Football (Live)',
    desc: 'Live fixtures, odds, and in-play data. Used exclusively for upcoming match snapshots, not historical training.',
    color: 'text-amber-400',
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/5',
  },
}

function sourceMeta(source) {
  return SOURCE_META[source] ?? {
    label: source,
    desc: '',
    color: 'text-[var(--text-h)]',
    border: 'border-[var(--border)]',
    bg: '',
  }
}

function brier(v) {
  if (v == null) return '—'
  const cls = v <= 0.10 ? 'text-emerald-400' : v <= 0.20 ? 'text-amber-400' : 'text-red-400'
  return <span className={`font-mono ${cls}`}>{v.toFixed(4)}</span>
}

function improvement(v) {
  if (v == null) return '—'
  const cls = v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-[var(--text-h)]'
  return <span className={`font-mono font-semibold ${cls}`}>{v > 0 ? '+' : ''}{v.toFixed(4)}</span>
}

function pval(v) {
  if (v == null) return <span className="text-[var(--text)] opacity-35">—</span>
  const cls = v <= 0.05 ? 'text-emerald-400' : v <= 0.10 ? 'text-amber-400' : 'text-[var(--text)] opacity-70'
  return <span className={`font-mono ${cls}`}>{v.toFixed(3)}</span>
}

// ── Source card ───────────────────────────────────────────────────────────────

function SourceCard({ summary }) {
  const [expanded, setExpanded] = useState(false)
  const meta = sourceMeta(summary.source)
  const hasData = summary.experiment_count > 0

  return (
    <div className={`rounded-xl border ${meta.border} ${meta.bg} overflow-hidden`}>
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Layers size={14} className={meta.color} />
              <h3 className={`text-sm font-bold ${meta.color}`}>{meta.label}</h3>
              {summary.accepted_count > 0 && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                  <CheckCircle size={9} /> {summary.accepted_count} accepted
                </span>
              )}
            </div>
            {meta.desc && (
              <p className="text-xs text-[var(--text)] opacity-70 leading-relaxed">{meta.desc}</p>
            )}
          </div>

          {/* Quick stats */}
          <div className="shrink-0 text-right space-y-1">
            {hasData ? (
              <>
                <p className="text-xs text-[var(--text)] opacity-60">{summary.experiment_count} experiment{summary.experiment_count !== 1 ? 's' : ''}</p>
                {summary.latest_brier_improvement != null && (
                  <p className="text-xs">
                    Latest Δ {improvement(summary.latest_brier_improvement)}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-[var(--text)] opacity-40">No experiments yet</p>
            )}
          </div>
        </div>

        {/* Overall acceptance bar */}
        {hasData && (
          <div className="mt-3 flex items-center gap-3">
            <div className="flex-1 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-500/60 transition-all"
                style={{ width: `${Math.round(summary.accepted_count / summary.experiment_count * 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-[var(--text)] opacity-60 whitespace-nowrap">
              {Math.round(summary.accepted_count / summary.experiment_count * 100)}% acceptance rate
            </span>
          </div>
        )}
      </div>

      {/* Experiment table (expandable) */}
      {hasData && (
        <>
          <button
            onClick={() => setExpanded(v => !v)}
            className="w-full flex items-center gap-2 px-5 py-2.5 border-t border-[var(--border)] text-xs text-[var(--text)] opacity-70 hover:opacity-100 hover:bg-[var(--code-bg)] transition-colors text-left"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {expanded ? 'Hide' : 'Show'} {summary.experiments.length} experiment{summary.experiments.length !== 1 ? 's' : ''}
          </button>

          {expanded && (
            <div className="border-t border-[var(--border)] overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--code-bg)]">
                    <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)]">Market</th>
                    <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)]">League</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Period</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Baseline</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">With Source</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Δ Brier</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">p-val</th>
                    <th className="px-3 py-2.5 text-center font-semibold text-[var(--text-h)]">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.experiments.map(exp => (
                    <tr key={exp.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--code-bg)]">
                      <td className="px-3 py-2.5 font-medium text-[var(--text-h)] whitespace-nowrap">{exp.market}</td>
                      <td className="px-3 py-2.5 text-[var(--text)] opacity-70 whitespace-nowrap">{exp.league ?? 'All'}</td>
                      <td className="px-3 py-2.5 text-right text-[var(--text)] opacity-60 whitespace-nowrap">
                        {exp.experiment_start} → {exp.experiment_end}
                      </td>
                      <td className="px-3 py-2.5 text-right">{brier(exp.baseline_brier)}<span className="text-[var(--text)] opacity-35 ml-1">({exp.baseline_n})</span></td>
                      <td className="px-3 py-2.5 text-right">{brier(exp.source_brier)}<span className="text-[var(--text)] opacity-35 ml-1">({exp.source_n})</span></td>
                      <td className="px-3 py-2.5 text-right">{improvement(exp.brier_improvement)}</td>
                      <td className="px-3 py-2.5 text-right">{pval(exp.p_value)}</td>
                      <td className="px-3 py-2.5 text-center">
                        {exp.accepted
                          ? <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-400"><CheckCircle size={10} /> Accepted</span>
                          : <span className="inline-flex items-center gap-1 text-[10px] text-red-400 opacity-70"><XCircle size={10} /> Rejected</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {summary.experiments[0]?.notes && (
                <p className="px-4 py-2.5 text-[10px] text-[var(--text)] opacity-55 border-t border-[var(--border)] italic">
                  {summary.experiments[0].notes}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DataSourcePage() {
  const [sources, setSources] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    fetchDataSources()
      .then(d => setSources(Array.isArray(d) ? d : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const totalAccepted = sources?.reduce((s, src) => s + src.accepted_count, 0) ?? 0
  const totalExp      = sources?.reduce((s, src) => s + src.experiment_count, 0) ?? 0

  return (
    <div className="space-y-5">

      {/* ── Intro ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] px-5 py-4 space-y-1.5">
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-[var(--accent)]" />
          <span className="text-sm font-semibold text-[var(--text-h)]">Data Source Performance</span>
        </div>
        <p className="text-xs text-[var(--text)] opacity-70 leading-relaxed">
          Each source undergoes an A/B Brier-score experiment before its data is incorporated into the ensemble.
          Positive Δ Brier (improvement) means adding the source reduces prediction error.
          Only accepted sources flow into ensemble weights — rejected sources are tracked but not used.
        </p>
        {totalExp > 0 && (
          <p className="text-xs text-[var(--accent)] font-semibold">
            {totalAccepted} of {totalExp} experiment{totalExp !== 1 ? 's' : ''} accepted across {sources?.length} source{sources?.length !== 1 ? 's' : ''}.
          </p>
        )}
      </div>

      {loading && <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>}
      {error   && <p className="text-sm text-red-400 px-1">{error}</p>}

      {!loading && !error && (!sources || sources.length === 0) && (
        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-12 flex flex-col items-center gap-3 text-center">
          <Layers size={32} className="text-[var(--text)] opacity-25" />
          <p className="text-sm font-semibold text-[var(--text-h)]">No experiments recorded yet</p>
          <p className="text-xs text-[var(--text)] opacity-75 max-w-sm">
            Data source A/B experiments are recorded here as each source is evaluated against the ensemble.
            Run the ETL loaders and calibration pipeline to generate experiment records.
          </p>
        </div>
      )}

      {/* Known sources always shown — even if no experiments yet */}
      {!loading && !error && (
        <div className="space-y-4">
          {Object.keys(SOURCE_META).map(sourceKey => {
            const found = sources?.find(s => s.source === sourceKey)
            return (
              <SourceCard
                key={sourceKey}
                summary={found ?? { source: sourceKey, experiment_count: 0, accepted_count: 0, latest_brier_improvement: null, experiments: [] }}
              />
            )
          })}
          {/* Any sources in DB not in our known list */}
          {sources?.filter(s => !SOURCE_META[s.source]).map(s => (
            <SourceCard key={s.source} summary={s} />
          ))}
        </div>
      )}
    </div>
  )
}
