import { useState, useEffect, useCallback } from 'react'
import { Activity, BarChart2, Target, RefreshCw, ChevronsUpDown, ChevronDown, ChevronUp } from 'lucide-react'
import { fetchModelPerformance } from '../api/model_performance'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from 'recharts'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import DatePicker from '../components/shared/DatePicker'

// ── Helpers ───────────────────────────────────────────────────────────────────

function todayStr() { return new Date().toISOString().slice(0, 10) }
function daysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function brierColor(v) {
  if (v == null) return 'text-[var(--text)]'
  if (v <= 0.10) return 'text-emerald-400'
  if (v <= 0.20) return 'text-amber-400'
  return 'text-red-400'
}

function useSortable(defaultCol, defaultDir = 'asc') {
  const [col, setCol] = useState(defaultCol)
  const [dir, setDir] = useState(defaultDir)
  function toggle(c) {
    if (col === c) setDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setCol(c); setDir('asc') }
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

function SortTh({ label, col, sort, align = 'right' }) {
  const active = sort.col === col
  const Icon = active ? (sort.dir === 'desc' ? ChevronDown : ChevronUp) : ChevronsUpDown
  return (
    <th
      onClick={() => sort.toggle(col)}
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

function Section({ icon: Icon, title, subtitle, children }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-[var(--border)] bg-[var(--code-bg)]">
        {Icon && <Icon size={14} className="text-[var(--accent)] shrink-0" />}
        <span className="text-sm font-semibold text-[var(--text-h)]">{title}</span>
        {subtitle && <span className="text-xs text-[var(--text)] opacity-70 hidden sm:inline">{subtitle}</span>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

const DATE_PRESETS = [
  { label: '30d',  from: () => daysAgo(30) },
  { label: '90d',  from: () => daysAgo(90) },
  { label: '180d', from: () => daysAgo(180) },
  { label: 'All',  from: () => '' },
]

// ── Brier Trend Chart ─────────────────────────────────────────────────────────

function BrierTrendChart({ data }) {
  if (!data?.length) {
    return <p className="text-sm text-[var(--text)] opacity-75 py-8 text-center">No settled forecasts yet — Brier trend appears after settlement begins.</p>
  }
  const avg = data.reduce((s, d) => s + (d.avg_brier ?? 0), 0) / data.length
  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text)] opacity-55">
        Brier score per day — lower is better. 0 = perfect, 0.25 = random (50/50 guessing), 1 = perfectly wrong.
        Reference line at 0.25.
      </p>
      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: 'var(--text)', opacity: 0.5 }}
              tickFormatter={v => v.slice(5)}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--text)', opacity: 0.5 }}
              axisLine={false}
              tickLine={false}
              domain={[0, 0.5]}
            />
            <Tooltip
              contentStyle={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 11 }}
              formatter={(val, name) => [val?.toFixed(4), name]}
            />
            <ReferenceLine y={0.25} stroke="var(--border)" strokeDasharray="4 4" label={{ value: '0.25 (random)', fontSize: 9, fill: 'var(--text)', opacity: 0.45 }} />
            <ReferenceLine y={avg} stroke="var(--accent)" strokeDasharray="3 3" opacity={0.5} />
            <Line type="monotone" dataKey="avg_brier" stroke="var(--accent)" strokeWidth={2} dot={false} name="Avg Brier" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-[var(--text)] opacity-45 text-center">
        Dashed accent line = period average ({avg.toFixed(4)}) · {data.length} days with settled forecasts
      </p>
    </div>
  )
}

// ── By Market table ───────────────────────────────────────────────────────────

function ByMarketTable({ rows }) {
  const sort = useSortable('avg_brier_ensemble', 'asc')
  const data = sort.sorted(rows)

  if (!rows.length) return <p className="text-sm text-[var(--text)] opacity-70 py-4 text-center">No market data yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <SortTh label="Market"    col="market"            sort={sort} align="left" />
            <SortTh label="Signals"   col="n"                 sort={sort} />
            <SortTh label="Win Rate"  col="win_rate"          sort={sort} />
            <SortTh label="Brier"     col="avg_brier_ensemble" sort={sort} />
            <SortTh label="Avg Prob"  col="avg_ensemble_prob" sort={sort} />
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-t border-[var(--border)] hover:bg-[var(--code-bg)]">
              <td className="px-3 py-2 font-medium text-[var(--text-h)]">{row.market}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--text)]">{row.n}</td>
              <td className="px-3 py-2 text-right tabular-nums font-semibold text-[var(--text-h)]">
                {row.win_rate != null ? `${row.win_rate}%` : '—'}
              </td>
              <td className={`px-3 py-2 text-right tabular-nums font-mono font-semibold ${brierColor(row.avg_brier_ensemble)}`}>
                {row.avg_brier_ensemble != null ? row.avg_brier_ensemble.toFixed(4) : '—'}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--text)]">
                {row.avg_ensemble_prob != null ? `${row.avg_ensemble_prob}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Calibration records ───────────────────────────────────────────────────────

function CalibrationTable({ rows }) {
  if (!rows.length) return (
    <p className="text-sm text-[var(--text)] opacity-70 py-4 text-center">
      No calibration records yet — calibration runs after sufficient settled forecasts are available.
    </p>
  )
  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text)] opacity-55">
        Isotonic regression calibration is fit per market. Positive improvement = calibration reduces Brier score.
        Only active records are used at prediction time.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--border)]">
              <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)]">Market</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Samples</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Raw Brier</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Cal. Brier</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Improvement</th>
              <th className="px-3 py-2.5 text-center font-semibold text-[var(--text-h)]">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const imp = row.brier_improvement
              const impColor = imp > 0 ? 'text-emerald-400' : imp < 0 ? 'text-red-400' : 'text-[var(--text-h)]'
              return (
                <tr key={i} className="border-t border-[var(--border)] hover:bg-[var(--code-bg)]">
                  <td className="px-3 py-2.5 font-medium text-[var(--text-h)]">{row.market}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{row.n_samples}</td>
                  <td className={`px-3 py-2.5 text-right tabular-nums font-mono ${brierColor(row.raw_brier)}`}>{row.raw_brier.toFixed(4)}</td>
                  <td className={`px-3 py-2.5 text-right tabular-nums font-mono ${brierColor(row.calibrated_brier)}`}>{row.calibrated_brier.toFixed(4)}</td>
                  <td className={`px-3 py-2.5 text-right tabular-nums font-semibold ${impColor}`}>
                    {imp >= 0 ? '+' : ''}{imp.toFixed(4)}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {row.is_active
                      ? <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">Active</span>
                      : <span className="text-[10px] text-[var(--text)] opacity-40">Inactive</span>
                    }
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Engine availability bars ──────────────────────────────────────────────────

function EngineChart({ rows, total }) {
  if (!rows.length) return null
  return (
    <div className="space-y-3">
      {rows.map(e => {
        const pct = total > 0 ? Math.round(e.n_available / total * 100) : 0
        const colors = {
          ZINB:     { bar: 'bg-blue-500',    text: 'text-blue-400' },
          Bayesian: { bar: 'bg-purple-500',  text: 'text-purple-400' },
          Elo:      { bar: 'bg-amber-500',   text: 'text-amber-400' },
          Ensemble: { bar: 'bg-[var(--accent)]', text: 'text-[var(--accent)]' },
        }
        const c = colors[e.engine] ?? colors.Ensemble
        return (
          <div key={e.engine} className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className={`font-semibold ${c.text}`}>{e.engine}</span>
              <div className="flex items-center gap-3 text-[var(--text)] opacity-70">
                <span className="tabular-nums">{e.n_available.toLocaleString()} signals</span>
                <span className="font-mono text-[var(--text-h)]">{pct}% coverage</span>
                {e.avg_brier != null && (
                  <span className={`font-mono font-semibold ${brierColor(e.avg_brier)}`}>BS {e.avg_brier.toFixed(4)}</span>
                )}
              </div>
            </div>
            <div className="h-2 w-full rounded-full bg-[var(--code-bg)] overflow-hidden">
              <div className={`h-full rounded-full ${c.bar} opacity-70 transition-all`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview',     label: 'Overview' },
  { id: 'markets',      label: 'By Market' },
  { id: 'calibration',  label: 'Calibration' },
]

export default function ModelPerformancePage() {
  const [dateFrom, setDateFrom]     = useState(daysAgo(90))
  const [dateTo, setDateTo]         = useState(todayStr())
  const [activePreset, setActivePreset] = useState('90d')
  const [activeTab, setActiveTab]   = useState('overview')
  const [refreshKey, setRefreshKey] = useState(0)
  const [data, setData]             = useState(null)
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)

  function applyPreset(p) {
    setActivePreset(p.label)
    setDateFrom(p.from())
    setDateTo(todayStr())
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchModelPerformance({ date_from: dateFrom || undefined, date_to: dateTo || undefined })
      setData(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, refreshKey]) // eslint-disable-line

  useEffect(() => { load() }, [load])

  const o = data?.overall

  return (
    <div className="space-y-5">

      {/* ── Date filter bar ── */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <DatePicker label="From" value={dateFrom} onChange={v => { setDateFrom(v); setActivePreset('') }} />
          <DatePicker label="To"   value={dateTo}   onChange={v => { setDateTo(v);   setActivePreset('') }} />
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
          <button
            onClick={() => setRefreshKey(k => k + 1)}
            disabled={loading}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--bg)] disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {loading && <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>}
      {error   && <p className="text-sm text-red-400 px-1">{error}</p>}

      {!loading && data && (
        <>
          {/* ── KPI row ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Total Signals', value: o?.signal_count?.toLocaleString() ?? '0', sub: 'SIGNAL-type snapshots' },
              { label: 'Settled',       value: o?.settled_count?.toLocaleString() ?? '0', sub: 'outcome known' },
              { label: 'Win Rate',      value: o?.win_rate != null ? `${o.win_rate}%` : '—', sub: `${o?.win_count ?? 0} wins` },
              { label: 'Avg Brier',     value: o?.avg_brier_ensemble != null ? o.avg_brier_ensemble.toFixed(4) : '—', sub: 'ensemble (lower = better)', cls: brierColor(o?.avg_brier_ensemble) },
            ].map(s => (
              <div key={s.label} className="rounded-xl border border-[var(--border)] bg-[var(--bg)] px-4 py-3">
                <p className="text-[10px] text-[var(--text)] opacity-55 uppercase tracking-wide">{s.label}</p>
                <p className={`text-2xl font-bold tabular-nums mt-0.5 ${s.cls ?? 'text-[var(--text-h)]'}`}>{s.value}</p>
                <p className="text-[10px] text-[var(--text)] opacity-50 mt-0.5">{s.sub}</p>
              </div>
            ))}
          </div>

          {/* ── Tab bar ── */}
          <div className="flex gap-1 border-b border-[var(--border)]">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  activeTab === t.id
                    ? 'border-[var(--accent)] text-[var(--accent)]'
                    : 'border-transparent text-[var(--text)] opacity-80 hover:opacity-100 hover:text-[var(--text-h)]'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* ── OVERVIEW ── */}
          {activeTab === 'overview' && (
            <div className="space-y-5">
              <Section icon={BarChart2} title="Brier Score Trend" subtitle="daily average ensemble Brier score">
                <BrierTrendChart data={data.brier_trend} />
              </Section>
              <Section icon={Activity} title="Engine Coverage" subtitle="how many signals each engine contributed to">
                {data.by_engine.length === 0
                  ? <p className="text-sm text-[var(--text)] opacity-70">No forecast data yet.</p>
                  : <EngineChart rows={data.by_engine} total={o?.signal_count ?? 0} />
                }
              </Section>
              {data.by_horizon.length > 0 && (
                <Section icon={Target} title="By Horizon" subtitle="forecast timing relative to kickoff">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-[var(--border)]">
                          <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)]">Horizon</th>
                          <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Signals</th>
                          <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Avg Ensemble %</th>
                          <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)]">Avg Brier</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.by_horizon.map((row, i) => (
                          <tr key={i} className="border-t border-[var(--border)] hover:bg-[var(--code-bg)]">
                            <td className="px-3 py-2.5 font-mono text-[var(--text-h)]">{row.horizon}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{row.n}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text-h)]">
                              {row.avg_ensemble_prob != null ? `${row.avg_ensemble_prob}%` : '—'}
                            </td>
                            <td className={`px-3 py-2.5 text-right tabular-nums font-mono font-semibold ${brierColor(row.avg_brier_ensemble)}`}>
                              {row.avg_brier_ensemble != null ? row.avg_brier_ensemble.toFixed(4) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Section>
              )}
            </div>
          )}

          {/* ── BY MARKET ── */}
          {activeTab === 'markets' && (
            <Section icon={BarChart2} title="Brier Score by Market" subtitle="sorted ascending — lower Brier = better calibration">
              <ByMarketTable rows={data.by_market} />
            </Section>
          )}

          {/* ── CALIBRATION ── */}
          {activeTab === 'calibration' && (
            <Section icon={Target} title="Calibration Records" subtitle="isotonic regression calibrators per market">
              <CalibrationTable rows={data.calibration_records} />
            </Section>
          )}
        </>
      )}
    </div>
  )
}
