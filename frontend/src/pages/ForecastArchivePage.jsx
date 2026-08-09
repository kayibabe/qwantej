import { useState, useEffect, useCallback } from 'react'
import { Database, ChevronLeft, ChevronRight, ChevronsUpDown, ChevronUp, ChevronDown } from 'lucide-react'
import { fetchForecastArchive } from '../api/forecasts'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import DatePicker from '../components/shared/DatePicker'

// ── Helpers ───────────────────────────────────────────────────────────────────

function todayStr() { return new Date().toISOString().slice(0, 10) }
function daysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function probCell(v) {
  if (v == null) return <span className="text-[var(--text)] opacity-35">—</span>
  const pct = Math.round(v * 100)
  const cls = pct >= 70 ? 'text-emerald-400' : pct >= 55 ? 'text-amber-400' : 'text-[var(--text-h)]'
  return <span className={`font-semibold tabular-nums ${cls}`}>{pct}%</span>
}

function edgeCell(v) {
  if (v == null) return <span className="text-[var(--text)] opacity-35">—</span>
  const cls = v >= 0.10 ? 'text-emerald-400' : v >= 0.04 ? 'text-amber-400' : v < 0 ? 'text-red-400' : 'text-[var(--text-h)]'
  return <span className={`font-semibold tabular-nums ${cls}`}>{v >= 0 ? '+' : ''}{(v * 100).toFixed(1)}%</span>
}

function outcomeCell(outcome) {
  if (!outcome) return <span className="text-[var(--text)] opacity-35">pending</span>
  const map = {
    WIN:  { label: 'Win',  cls: 'text-emerald-400' },
    LOSS: { label: 'Loss', cls: 'text-red-400' },
    VOID: { label: 'Void', cls: 'text-slate-400' },
    PUSH: { label: 'Push', cls: 'text-slate-400' },
  }
  const m = map[outcome]
  return m ? <span className={`font-semibold ${m.cls}`}>{m.label}</span> : <span>{outcome}</span>
}

function brierCell(v) {
  if (v == null) return <span className="text-[var(--text)] opacity-35">—</span>
  const cls = v <= 0.10 ? 'text-emerald-400' : v <= 0.20 ? 'text-amber-400' : 'text-red-400'
  return <span className={`font-mono tabular-nums ${cls}`}>{v.toFixed(3)}</span>
}

function SortTh({ label, col, active, dir, onToggle, align = 'right' }) {
  const Icon = active ? (dir === 'desc' ? ChevronDown : ChevronUp) : ChevronsUpDown
  return (
    <th
      onClick={() => onToggle(col)}
      className={`px-3 py-2.5 font-semibold cursor-pointer select-none whitespace-nowrap transition-colors hover:text-[var(--text-h)] ${
        active ? 'text-[var(--accent)]' : 'text-[var(--text)] opacity-70'
      } ${align === 'left' ? 'text-left' : 'text-right'}`}
    >
      <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
        {label}
        <Icon size={11} className={active ? 'text-[var(--accent)]' : 'opacity-30'} />
      </span>
    </th>
  )
}

const DATE_PRESETS = [
  { label: '7d',  from: () => daysAgo(7) },
  { label: '30d', from: () => daysAgo(30) },
  { label: '90d', from: () => daysAgo(90) },
  { label: 'All', from: () => '' },
]

const MARKETS = ['', 'Home Win', 'Away Win', 'Draw', 'Over 2.5', 'Under 2.5', 'Over 1.5', 'BTTS Yes', 'BTTS No']
const OUTCOMES = ['', 'WIN', 'LOSS', 'VOID', 'PUSH']

const PER_PAGE = 50

export default function ForecastArchivePage({ onMatchIntelligence }) {
  const [dateFrom, setDateFrom] = useState(daysAgo(30))
  const [dateTo, setDateTo]     = useState(todayStr())
  const [market, setMarket]     = useState('')
  const [outcome, setOutcome]   = useState('')
  const [activePreset, setActivePreset] = useState('30d')
  const [page, setPage]         = useState(1)
  const [sortCol, setSortCol]   = useState('snapshot_at')
  const [sortDir, setSortDir]   = useState('desc')

  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  function applyPreset(preset) {
    setActivePreset(preset.label)
    setDateFrom(preset.from())
    setDateTo(todayStr())
    setPage(1)
  }

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setSortCol(col); setSortDir('desc') }
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchForecastArchive({
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        market: market || undefined,
        outcome: outcome || undefined,
        page,
        per_page: PER_PAGE,
      })
      setData(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, market, outcome, page])

  useEffect(() => { load() }, [load])

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  // Client-side sort (within loaded page)
  const sorted = [...items].sort((a, b) => {
    let va = a[sortCol]
    let vb = b[sortCol]
    if (va == null) va = sortDir === 'desc' ? -Infinity : Infinity
    if (vb == null) vb = sortDir === 'desc' ? -Infinity : Infinity
    if (typeof va === 'string') return sortDir === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb)
    return sortDir === 'desc' ? vb - va : va - vb
  })

  const wins   = items.filter(i => i.outcome === 'WIN').length
  const losses = items.filter(i => i.outcome === 'LOSS').length
  const settled = wins + losses
  const wr = settled > 0 ? Math.round(wins / settled * 100) : null
  const avgBrier = items.filter(i => i.brier_score != null).length > 0
    ? items.reduce((s, i) => s + (i.brier_score ?? 0), 0) / items.filter(i => i.brier_score != null).length
    : null

  return (
    <div className="space-y-5">

      {/* ── Filters ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <DatePicker label="From" value={dateFrom} onChange={v => { setDateFrom(v); setActivePreset(''); setPage(1) }} />
          <DatePicker label="To"   value={dateTo}   onChange={v => { setDateTo(v);   setActivePreset(''); setPage(1) }} />

          <div className="flex items-end gap-1">
            {DATE_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => applyPreset(p)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  activePreset === p.label
                    ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10'
                    : 'border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--bg)]'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-[var(--text)] opacity-70 whitespace-nowrap">Market</label>
            <select
              value={market}
              onChange={e => { setMarket(e.target.value); setPage(1) }}
              className="text-sm bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-[var(--text-h)]"
            >
              {MARKETS.map(m => <option key={m} value={m}>{m || 'All'}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-[var(--text)] opacity-70 whitespace-nowrap">Outcome</label>
            <select
              value={outcome}
              onChange={e => { setOutcome(e.target.value); setPage(1) }}
              className="text-sm bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-[var(--text-h)]"
            >
              {OUTCOMES.map(o => <option key={o} value={o}>{o || 'All'}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ── Summary stats ── */}
      {!loading && total > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total', value: total.toLocaleString(), sub: 'signals in period' },
            { label: 'Win Rate', value: wr != null ? `${wr}%` : '—', sub: `${wins}W · ${losses}L` },
            { label: 'Avg Brier', value: avgBrier != null ? avgBrier.toFixed(3) : '—', sub: 'lower = better (0 is perfect)' },
            { label: 'Page', value: `${page} / ${pages}`, sub: `${PER_PAGE} per page` },
          ].map(s => (
            <div key={s.label} className="rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3">
              <p className="text-[10px] text-[var(--text)] opacity-55 uppercase tracking-wide">{s.label}</p>
              <p className="text-xl font-bold text-[var(--text-h)] tabular-nums mt-0.5">{s.value}</p>
              <p className="text-[10px] text-[var(--text)] opacity-50 mt-0.5">{s.sub}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── States ── */}
      {loading && <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>}
      {error   && <p className="text-sm text-red-400 px-1">{error}</p>}

      {!loading && !error && total === 0 && (
        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-12 flex flex-col items-center gap-3 text-center">
          <Database size={32} className="text-[var(--text)] opacity-25" />
          <p className="text-sm font-semibold text-[var(--text-h)]">No archived forecasts found</p>
          <p className="text-xs text-[var(--text)] opacity-75 max-w-sm">
            The archive grows as the ensemble runs and settles. Try a wider date range or remove filters.
          </p>
        </div>
      )}

      {/* ── Table ── */}
      {!loading && !error && sorted.length > 0 && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--code-bg)]">
                  <SortTh label="Date"      col="snapshot_at"   active={sortCol==='snapshot_at'}   dir={sortDir} onToggle={toggleSort} align="left" />
                  <SortTh label="Match"     col="home_team"     active={sortCol==='home_team'}      dir={sortDir} onToggle={toggleSort} align="left" />
                  <SortTh label="Market"    col="market"        active={sortCol==='market'}         dir={sortDir} onToggle={toggleSort} align="left" />
                  <SortTh label="Ensemble"  col="ensemble_prob" active={sortCol==='ensemble_prob'}  dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Calibrated" col="calibrated_prob" active={sortCol==='calibrated_prob'} dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Fair"      col="fair_odds"     active={sortCol==='fair_odds'}      dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Market @"  col="market_odds"   active={sortCol==='market_odds'}    dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Edge"      col="value_edge"    active={sortCol==='value_edge'}     dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Outcome"   col="outcome"       active={sortCol==='outcome'}        dir={sortDir} onToggle={toggleSort} />
                  <SortTh label="Brier"     col="brier_score"   active={sortCol==='brier_score'}    dir={sortDir} onToggle={toggleSort} />
                </tr>
              </thead>
              <tbody>
                {sorted.map(row => (
                  <tr
                    key={row.id}
                    className={`border-b border-[var(--border)] last:border-0 transition-colors ${
                      row.fixture_id && onMatchIntelligence ? 'cursor-pointer hover:bg-[var(--code-bg)]' : 'hover:bg-[var(--code-bg)]'
                    }`}
                    onClick={() => row.fixture_id && onMatchIntelligence?.(row.fixture_id)}
                  >
                    <td className="px-3 py-2.5 text-[var(--text)] opacity-70 whitespace-nowrap">
                      {row.snapshot_at ? new Date(row.snapshot_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-h)] font-medium whitespace-nowrap">
                      {row.home_team && row.away_team
                        ? <span title={`${row.league ?? ''}`}>{row.home_team} vs {row.away_team}</span>
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-h)] whitespace-nowrap">{row.market}</td>
                    <td className="px-3 py-2.5 text-right">{probCell(row.ensemble_prob)}</td>
                    <td className="px-3 py-2.5 text-right">{probCell(row.calibrated_prob)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-mono text-[var(--text)]">
                      {row.fair_odds != null ? row.fair_odds.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-mono text-[var(--text-h)]">
                      {row.market_odds != null ? row.market_odds.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right">{edgeCell(row.value_edge)}</td>
                    <td className="px-3 py-2.5 text-right">{outcomeCell(row.outcome)}</td>
                    <td className="px-3 py-2.5 text-right">{brierCell(row.brier_score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] bg-[var(--code-bg)]">
            <p className="text-xs text-[var(--text)] opacity-60">
              {total.toLocaleString()} total · page {page} of {pages}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs border border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--bg)] disabled:opacity-40 transition-colors"
              >
                <ChevronLeft size={13} /> Prev
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs border border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--bg)] disabled:opacity-40 transition-colors"
              >
                Next <ChevronRight size={13} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
