import { useState, useEffect } from 'react'
import { Database, CheckCircle, ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react'
import { fetchDataSourceCoverage } from '../api/data_sources'
import LoadingSpinner from '../components/shared/LoadingSpinner'

// ── Helpers ───────────────────────────────────────────────────────────────────

function useSortable(defaultCol, defaultDir = 'desc') {
  const [col, setCol] = useState(defaultCol)
  const [dir, setDir] = useState(defaultDir)
  function toggle(c) {
    if (col === c) setDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setCol(c); setDir('desc') }
  }
  function sorted(rows) {
    return [...rows].sort((a, b) => {
      const va = a[col] ?? (dir === 'desc' ? -Infinity : Infinity)
      const vb = b[col] ?? (dir === 'desc' ? -Infinity : Infinity)
      if (typeof va === 'string') return dir === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb)
      return dir === 'desc' ? vb - va : va - vb
    })
  }
  return { col, dir, toggle, sorted }
}

function SortTh({ label, col, sort, align = 'right', className = '' }) {
  const active = sort.col === col
  const Icon = active ? (sort.dir === 'desc' ? ChevronDown : ChevronUp) : ChevronsUpDown
  return (
    <th
      onClick={() => sort.toggle(col)}
      className={`px-3 py-2.5 font-semibold cursor-pointer select-none whitespace-nowrap transition-colors hover:text-[var(--text-h)] ${
        active ? 'text-[var(--accent)]' : 'text-[var(--text)] opacity-70'
      } ${align === 'left' ? 'text-left' : 'text-right'} ${className}`}
    >
      <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
        {label}
        <Icon size={11} className={active ? 'text-[var(--accent)]' : 'opacity-30'} />
      </span>
    </th>
  )
}

function CompletenessBar({ pct }) {
  const color = pct >= 90 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-[var(--code-bg)] overflow-hidden min-w-[48px]">
        <div className={`h-full rounded-full ${color} opacity-75 transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-mono tabular-nums w-10 text-right ${pct >= 90 ? 'text-emerald-400' : pct >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
        {pct.toFixed(1)}%
      </span>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DataSourcePage() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const sort = useSortable('fixture_count', 'desc')

  useEffect(() => {
    fetchDataSourceCoverage()
      .then(d => setData(d))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const leagues = data?.leagues ?? []
  const sortedLeagues = sort.sorted(leagues)
  const avgCompleteness = leagues.length > 0
    ? (leagues.reduce((s, l) => s + l.completeness_pct, 0) / leagues.length).toFixed(1)
    : null

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] px-5 py-4 space-y-1.5">
        <div className="flex items-center gap-2">
          <Database size={15} className="text-[var(--accent)]" />
          <span className="text-sm font-semibold text-[var(--text-h)]">Data Warehouse Coverage</span>
        </div>
        <p className="text-xs text-[var(--text)] opacity-70 leading-relaxed">
          Historical match data used to train the ZINB and Elo models. Completeness = goals + odds + shots columns populated.
          Calibration snapshots = settled ForecastSnapshot rows derived from each league's backfill data.
        </p>
      </div>

      {loading && <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>}
      {error   && <p className="text-sm text-red-400 px-1">{error}</p>}

      {!loading && data && (
        <>
          {/* ── Summary KPIs ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Fixtures',  value: data.total_fixtures.toLocaleString(),  sub: 'historical match records' },
              { label: 'Leagues',   value: data.total_leagues,                     sub: 'competition tiers' },
              { label: 'Season-Entries', value: data.total_seasons.toLocaleString(), sub: 'league × season pairs' },
              { label: 'Avg Completeness', value: avgCompleteness ? `${avgCompleteness}%` : '—', sub: 'goals + odds + shots' },
            ].map(s => (
              <div key={s.label} className="rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3">
                <p className="text-[10px] text-[var(--text)] opacity-55 uppercase tracking-wide">{s.label}</p>
                <p className="text-2xl font-bold text-[var(--text-h)] tabular-nums mt-0.5">{s.value}</p>
                <p className="text-[10px] text-[var(--text)] opacity-50 mt-0.5">{s.sub}</p>
              </div>
            ))}
          </div>

          {/* ── By Source ── */}
          {data.by_source?.length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
              <div className="px-5 py-3.5 border-b border-[var(--border)] bg-[var(--code-bg)]">
                <span className="text-sm font-semibold text-[var(--text-h)]">By Source</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border)]">
                      <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)]">Source</th>
                      <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Fixtures</th>
                      <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">With xG</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_source.map((s, i) => (
                      <tr key={i} className="border-t border-[var(--border)] hover:bg-[var(--code-bg)]">
                        <td className="px-3 py-2.5 font-medium text-[var(--text-h)]">{s.source}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{s.fixture_count.toLocaleString()}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">
                          {s.with_xg > 0
                            ? <span className="text-emerald-400 flex items-center justify-end gap-1"><CheckCircle size={11} /> {s.with_xg.toLocaleString()}</span>
                            : <span className="opacity-35">—</span>
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Per-League table ── */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
            <div className="px-5 py-3.5 border-b border-[var(--border)] bg-[var(--code-bg)]">
              <span className="text-sm font-semibold text-[var(--text-h)]">League Coverage</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    <SortTh label="League"       col="league"                        sort={sort} align="left" />
                    <SortTh label="Country"      col="country"                       sort={sort} align="left" />
                    <th className="px-3 py-2.5 text-left font-semibold text-[var(--text)] opacity-70 whitespace-nowrap">Seasons</th>
                    <SortTh label="Fixtures"     col="fixture_count"                 sort={sort} />
                    <SortTh label="Completeness" col="completeness_pct"              sort={sort} className="min-w-[160px]" />
                    <SortTh label="Goals"        col="with_goals"                    sort={sort} />
                    <SortTh label="Odds"         col="with_odds"                     sort={sort} />
                    <SortTh label="Shots"        col="with_shots"                    sort={sort} />
                    <SortTh label="Cal. Snaps"   col="calibration_snapshot_count"    sort={sort} />
                  </tr>
                </thead>
                <tbody>
                  {sortedLeagues.map((row, i) => (
                    <tr key={i} className="border-t border-[var(--border)] hover:bg-[var(--code-bg)]">
                      <td className="px-3 py-2.5 font-medium text-[var(--text-h)] whitespace-nowrap">{row.league}</td>
                      <td className="px-3 py-2.5 text-[var(--text)] opacity-70 whitespace-nowrap">{row.country}</td>
                      <td className="px-3 py-2.5 text-[var(--text)] opacity-60">
                        {row.seasons?.length > 0
                          ? `${Math.min(...row.seasons)}–${Math.max(...row.seasons)}`
                          : '—'}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-h)]">{row.fixture_count.toLocaleString()}</td>
                      <td className="px-3 py-2.5">
                        <CompletenessBar pct={row.completeness_pct} />
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{row.with_goals.toLocaleString()}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{row.with_odds.toLocaleString()}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{row.with_shots.toLocaleString()}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {row.calibration_snapshot_count > 0
                          ? <span className="text-emerald-400 font-semibold">{row.calibration_snapshot_count.toLocaleString()}</span>
                          : <span className="opacity-35">—</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
