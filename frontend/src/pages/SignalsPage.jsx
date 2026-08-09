import { useState, useEffect, useRef, useCallback } from 'react'
import {
  RefreshCw, Download, Calendar, AlertCircle, ChevronLeft, ChevronRight,
  TrendingUp, Zap, Activity, Clock, Filter, X
} from 'lucide-react'
import { fetchForecasts } from '../api/forecasts'
import { syncData } from '../api/tracker'
import { computeSignals } from '../api/signals'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { useAuth } from '../context/AuthContext'
import useTier from '../hooks/useTier'

// ── Helpers ───────────────────────────────────────────────────────────────────

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
}

function shiftDate(iso, days) {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

function fmtKickoff(isoStr) {
  if (!isoStr) return null
  const utc = isoStr.endsWith('Z') || isoStr.includes('+') ? isoStr : isoStr + 'Z'
  return new Date(utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function probColor(p) {
  if (p >= 0.70) return 'text-emerald-400'
  if (p >= 0.55) return 'text-amber-400'
  return 'text-orange-400'
}

function probBarColor(p) {
  if (p >= 0.70) return 'bg-emerald-400/70'
  if (p >= 0.55) return 'bg-amber-400/70'
  return 'bg-orange-400/70'
}

function edgeColor(v) {
  if (v == null) return 'text-[var(--text)]'
  if (v >= 0.10) return 'text-emerald-400'
  if (v >= 0.04) return 'text-amber-400'
  return 'text-orange-400'
}

function cardBorder(f) {
  const p = f.calibrated_prob ?? f.ensemble_prob
  if (f.outcome === 'WIN')  return 'border-emerald-500/40 border-l-4 border-l-emerald-500'
  if (f.outcome === 'LOSS') return 'border-red-400/30 border-l-4 border-l-red-400'
  if (p >= 0.70) return 'border-emerald-500/30 border-l-4 border-l-emerald-400'
  if (f.confidence === 'Medium') return 'border-amber-500/30 border-l-4 border-l-amber-400'
  return 'border-[var(--border)]'
}

function outcomeLabel(f) {
  if (!f.outcome) return null
  const map = { WIN: { label: 'Won', cls: 'text-emerald-400' }, LOSS: { label: 'Lost', cls: 'text-red-400' }, VOID: { label: 'Void', cls: 'text-slate-400' }, PUSH: { label: 'Push', cls: 'text-slate-400' } }
  return map[f.outcome] ?? null
}

// ── Forecast card ─────────────────────────────────────────────────────────────

function ForecastCard({ forecast, rank, onMatchIntelligence }) {
  const prob = forecast.calibrated_prob ?? forecast.ensemble_prob
  const pct = Math.round(prob * 100)
  const edge = forecast.value_edge
  const kickoff = fmtKickoff(forecast.kickoff_at)
  const result = outcomeLabel(forecast)

  const confStyle = {
    High:   'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    Medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    Low:    'bg-rose-500/15 text-rose-400 border-rose-500/30',
  }[forecast.confidence] ?? null

  return (
    <div className={`rounded-xl border bg-[var(--bg)] overflow-hidden ${cardBorder(forecast)}`}>
      <div className="px-4 py-3 space-y-2.5">

        {/* Match header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-[var(--text-h)] leading-tight truncate">
              {forecast.home_team ?? '—'} vs {forecast.away_team ?? '—'}
            </h3>
            {forecast.league && (
              <span className="text-[11px] text-[var(--text)] opacity-45 leading-none">
                {forecast.country ? `${forecast.country} · ` : ''}{forecast.league}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
            {forecast.outcome && forecast.actual_home_goals != null ? (
              <>
                <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-500">
                  <Clock size={10} /> FT
                </span>
                <span className="inline-flex items-center rounded-md border border-emerald-500/25 bg-emerald-500/8 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                  {forecast.actual_home_goals}-{forecast.actual_away_goals}
                </span>
              </>
            ) : kickoff ? (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--text)] opacity-75">
                <Clock size={10} /> {kickoff}
              </span>
            ) : null}
          </div>
        </div>

        {/* Market + confidence + prob */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 flex-wrap min-w-0">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[var(--code-bg)] border border-[var(--border)] text-[var(--text-h)]">
                {forecast.market}
              </span>
              {confStyle && forecast.confidence && (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${confStyle}`}>
                  {forecast.confidence}
                </span>
              )}
            </div>
            <span className={`text-xl font-bold tabular-nums leading-none shrink-0 ${probColor(prob)}`}>
              {pct}%
            </span>
          </div>

          {/* Prob bar */}
          <div className="h-1.5 w-full rounded-full bg-[var(--code-bg)] overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${probBarColor(prob)}`} style={{ width: `${pct}%` }} />
          </div>

          {/* Odds + edge + outcome */}
          <div className="flex items-center gap-3 flex-wrap">
            {forecast.fair_odds && (
              <span className="text-xs text-[var(--text)] opacity-70">
                Fair <span className="font-mono text-[var(--text-h)]">{forecast.fair_odds.toFixed(2)}</span>
              </span>
            )}
            {forecast.market_odds && (
              <span className="text-xs font-bold font-mono text-[var(--accent)]">
                @{forecast.market_odds.toFixed(2)}
              </span>
            )}
            {edge != null && (
              <span className={`text-xs font-semibold ${edgeColor(edge)}`}>
                Edge {edge >= 0 ? '+' : ''}{(edge * 100).toFixed(1)}%
              </span>
            )}
            <div className="flex-1" />
            {result && (
              <span className={`text-xs font-bold ${result.cls}`}>{result.label}</span>
            )}
          </div>
        </div>

        {/* Engine breakdown */}
        {(forecast.zinb_prob != null || forecast.bayesian_prob != null || forecast.elo_prob != null) && (
          <div className="flex items-center gap-3 pt-1 border-t border-[var(--border)]">
            {forecast.zinb_prob != null && (
              <span className="text-[10px] text-[var(--text)] opacity-60">
                ZINB <span className="font-mono text-[var(--text-h)]">{Math.round(forecast.zinb_prob * 100)}%</span>
              </span>
            )}
            {forecast.bayesian_prob != null && (
              <span className="text-[10px] text-[var(--text)] opacity-60">
                Bayes <span className="font-mono text-[var(--text-h)]">{Math.round(forecast.bayesian_prob * 100)}%</span>
              </span>
            )}
            {forecast.elo_prob != null && (
              <span className="text-[10px] text-[var(--text)] opacity-60">
                Elo <span className="font-mono text-[var(--text-h)]">{Math.round(forecast.elo_prob * 100)}%</span>
              </span>
            )}
            {forecast.brier_score != null && (
              <span className="text-[10px] text-[var(--text)] opacity-45 ml-auto">
                BS {forecast.brier_score.toFixed(3)}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-2">
        {rank != null && (
          <span className="text-[10px] font-bold text-[var(--text)] opacity-35 tabular-nums">#{rank}</span>
        )}
        <span className="flex items-center gap-1 text-xs text-[var(--accent)] font-semibold">
          <Activity size={11} /> Ensemble
        </span>
        <span className="text-[10px] text-[var(--text)] opacity-35 ml-1">{forecast.horizon}</span>
        <div className="flex-1" />
        {forecast.fixture_id && onMatchIntelligence && (
          <button
            onClick={() => onMatchIntelligence(forecast.fixture_id)}
            className="text-xs text-[var(--accent)] font-semibold hover:underline"
          >
            Deep dive →
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const MARKETS = [
  '', 'Home Win', 'Away Win', 'Draw', 'Over 2.5', 'Under 2.5',
  'Over 1.5', 'BTTS Yes', 'BTTS No', 'X2 (Draw or Away)',
]

export default function SignalsPage({ onMatchIntelligence, onUpgrade }) {
  const { user } = useAuth()
  const { isPro } = useTier()
  const isAdmin = !!user?.is_admin
  const today = todayStr()
  const maxDate = shiftDate(today, 1)

  const [date, setDate]         = useState(today)
  const [market, setMarket]     = useState('')
  const [sortBy, setSortBy]     = useState('prob')
  const [forecasts, setForecasts] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [syncing, setSyncing]   = useState(false)
  const [computing, setComputing] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const dateInputRef = useRef(null)

  const isToday    = date === today
  const isTomorrow = date === maxDate
  const isBusy     = syncing || computing

  const load = useCallback(async (d, m) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchForecasts({ date: d, market: m || undefined })
      setForecasts(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message)
      setForecasts([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(date, market) }, [date, market, load])

  async function handleSync() {
    setSyncing(true)
    try {
      await syncData(date, { force: true })
      await computeSignals(date)
      await load(date, market)
    } catch (e) { console.error(e) }
    finally { setSyncing(false) }
  }

  async function handleRecompute() {
    setComputing(true)
    try {
      await computeSignals(date)
      await load(date, market)
    } catch (e) { console.error(e) }
    finally { setComputing(false) }
  }

  const sorted = [...forecasts].sort((a, b) => {
    if (sortBy === 'prob') {
      const pa = a.calibrated_prob ?? a.ensemble_prob
      const pb = b.calibrated_prob ?? b.ensemble_prob
      return pb - pa
    }
    if (sortBy === 'edge') return (b.value_edge ?? -99) - (a.value_edge ?? -99)
    if (sortBy === 'kickoff') {
      const ta = a.kickoff_at ? new Date(a.kickoff_at.endsWith('Z') ? a.kickoff_at : a.kickoff_at + 'Z') : new Date(0)
      const tb = b.kickoff_at ? new Date(b.kickoff_at.endsWith('Z') ? b.kickoff_at : b.kickoff_at + 'Z') : new Date(0)
      return ta - tb
    }
    return 0
  })

  const FREE_LIMIT = 5
  const visible = isPro ? sorted : sorted.slice(0, FREE_LIMIT)
  const lockedCount = isPro ? 0 : Math.max(0, sorted.length - FREE_LIMIT)

  const stats = {
    total: sorted.length,
    highProb: sorted.filter(f => (f.calibrated_prob ?? f.ensemble_prob) >= 0.70).length,
  }

  return (
    <div className="space-y-5">

      {/* ── Toolbar ── */}
      <div className="flex items-center gap-2 flex-wrap">

        {/* Date nav */}
        <div className="flex items-center rounded-lg border border-[var(--border)] overflow-hidden">
          <button
            onClick={() => !isBusy && setDate(shiftDate(date, -1))}
            disabled={isBusy}
            aria-label="Previous day"
            className="px-2 py-1.5 hover:bg-[var(--code-bg)] text-[var(--text)] disabled:opacity-40 transition-colors border-r border-[var(--border)]"
          >
            <ChevronLeft size={14} />
          </button>
          <div
            className="relative flex items-center gap-1.5 px-3 py-1.5 cursor-pointer group hover:bg-[var(--code-bg)] transition-colors"
            onClick={() => !isBusy && dateInputRef.current?.showPicker()}
          >
            <Calendar size={13} className="text-[var(--accent)] shrink-0" />
            <span className="text-sm font-medium text-[var(--text-h)] group-hover:text-[var(--accent)] transition-colors select-none">
              {fmtDate(date)}{isToday ? ' · Today' : isTomorrow ? ' · Tomorrow' : ''}
            </span>
            <input
              ref={dateInputRef}
              type="date"
              value={date}
              max={maxDate}
              onChange={e => e.target.value && setDate(e.target.value)}
              disabled={isBusy}
              style={{ position: 'absolute', opacity: 0, pointerEvents: 'none', width: 0, height: 0, bottom: 0, left: 0 }}
            />
          </div>
          <button
            onClick={() => !isBusy && setDate(shiftDate(date, 1))}
            disabled={isBusy || date >= maxDate}
            aria-label="Next day"
            className="px-2 py-1.5 hover:bg-[var(--code-bg)] text-[var(--text)] disabled:opacity-40 transition-colors border-l border-[var(--border)]"
          >
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Filter toggle */}
        <button
          onClick={() => setShowFilters(v => !v)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-colors ${
            showFilters || market
              ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/8'
              : 'border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)]'
          }`}
        >
          <Filter size={13} />
          <span className="hidden sm:inline">Filters</span>
          {market && <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />}
        </button>

        {/* Admin controls */}
        {isAdmin && (
          <>
            <button
              onClick={handleRecompute}
              disabled={isBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)] disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={13} className={computing ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">{computing ? 'Computing…' : 'Recompute'}</span>
            </button>
            <button
              onClick={handleSync}
              disabled={isBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              <Download size={13} className={syncing ? 'animate-bounce' : ''} />
              <span className="hidden sm:inline">{syncing ? 'Syncing…' : 'Sync API'}</span>
            </button>
          </>
        )}

        {/* Sort */}
        <div className="ml-auto flex items-center gap-1">
          {[
            { id: 'prob', label: 'Prob' },
            { id: 'edge', label: 'Edge' },
            { id: 'kickoff', label: 'Kickoff' },
          ].map(s => (
            <button
              key={s.id}
              onClick={() => setSortBy(s.id)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                sortBy === s.id
                  ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/8'
                  : 'border-transparent text-[var(--text)] opacity-70 hover:opacity-100 hover:text-[var(--text-h)]'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Filter panel ── */}
      {showFilters && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] px-4 py-3 flex items-center gap-3 flex-wrap">
          <label className="text-xs font-medium text-[var(--text)] opacity-70">Market</label>
          <select
            value={market}
            onChange={e => setMarket(e.target.value)}
            className="flex-1 min-w-[140px] text-sm bg-[var(--bg)] border border-[var(--border)] rounded-lg px-2.5 py-1.5 text-[var(--text-h)]"
          >
            {MARKETS.map(m => (
              <option key={m} value={m}>{m || 'All markets'}</option>
            ))}
          </select>
          {market && (
            <button onClick={() => setMarket('')} className="flex items-center gap-1 text-xs text-[var(--text)] opacity-65 hover:opacity-100">
              <X size={12} /> Clear
            </button>
          )}
        </div>
      )}

      {/* ── Stats bar ── */}
      {!loading && sorted.length > 0 && (
        <div className="flex items-center gap-4 px-1 text-xs text-[var(--text)]">
          <span><span className="font-semibold text-[var(--text-h)]">{stats.total}</span> signal{stats.total !== 1 ? 's' : ''}</span>
          {stats.highProb > 0 && (
            <span><span className="font-semibold text-emerald-400">{stats.highProb}</span> high-prob (≥70%)</span>
          )}
        </div>
      )}

      {/* ── Legend ── */}
      {!loading && sorted.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-[var(--text)] opacity-60 px-1">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/60 border border-emerald-400 shrink-0" /> ≥70% prob</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500/60 border border-amber-400 shrink-0" /> Medium conf</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/60 border border-emerald-500 shrink-0" /> Won</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-500/60 border border-red-400 shrink-0" /> Lost</span>
        </div>
      )}

      {/* ── States ── */}
      {loading && (
        <div className="grid gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--code-bg)] animate-pulse overflow-hidden">
              <div className="px-4 py-3 space-y-3">
                <div className="h-4 w-2/3 rounded-full bg-[var(--border)]" />
                <div className="flex items-center gap-3">
                  <div className="h-3 w-28 rounded-full bg-[var(--border)]" />
                  <div className="h-2 w-20 rounded-full bg-[var(--border)]" />
                  <div className="h-3 w-10 rounded-full bg-[var(--border)]" />
                </div>
              </div>
              <div className="border-t border-[var(--border)] px-4 py-2.5 flex items-center gap-2">
                <div className="h-2.5 w-24 rounded-full bg-[var(--border)]" />
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-6 py-8 text-center">
          <p className="text-sm text-red-400 font-semibold mb-1">Failed to load signals</p>
          <p className="text-xs text-slate-400">{error}</p>
        </div>
      )}

      {!loading && !error && sorted.length === 0 && (
        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-12 flex flex-col items-center gap-3 text-center">
          <div className="w-12 h-12 rounded-full bg-[var(--code-bg)] flex items-center justify-center">
            <Zap size={22} className="text-[var(--text)] opacity-40" />
          </div>
          <p className="text-sm font-semibold text-[var(--text-h)]">No signals for {fmtDate(date)}</p>
          <p className="text-xs text-[var(--text)] opacity-75 max-w-sm">
            {market
              ? `No ensemble signals for the "${market}" market on this date. Try a different market or date.`
              : 'The ensemble engine has not produced signals for this date yet. Use Sync API to pull fresh fixture data and run the ensemble.'}
          </p>
          {isAdmin && (
            <button
              onClick={handleSync}
              disabled={isBusy}
              className="mt-1 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              <Download size={13} /> Run Ensemble
            </button>
          )}
        </div>
      )}

      {/* ── Signal cards ── */}
      {!loading && !error && visible.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {visible.map((f, i) => (
            <ForecastCard
              key={f.id}
              forecast={f}
              rank={i + 1}
              onMatchIntelligence={onMatchIntelligence}
            />
          ))}
        </div>
      )}

      {/* ── Peek + upgrade ── */}
      {!isPro && lockedCount > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {sorted.slice(FREE_LIMIT, FREE_LIMIT + 3).map((_, i) => (
              <div key={i} className="relative select-none pointer-events-none">
                <div className="opacity-40 blur-sm rounded-xl border border-white/8 bg-white/4 h-40" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="rounded-lg bg-black/70 px-3 py-1.5 text-xs text-white font-medium backdrop-blur-sm border border-white/10">
                    🔒 Pro only
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/8 px-4 py-3 text-center text-sm space-y-1">
            <span className="text-slate-300">
              Viewing <strong className="text-white">{FREE_LIMIT} of {sorted.length}</strong> signals.{' '}
            </span>
            <button onClick={onUpgrade} className="text-blue-400 hover:text-blue-300 underline underline-offset-2 font-medium">
              Upgrade to Pro →
            </button>
          </div>
        </>
      )}

    </div>
  )
}
