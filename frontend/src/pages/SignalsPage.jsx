import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { RefreshCw, Download, Calendar, TrendingUp, AlertCircle, X, Target, Zap, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Heart, Bot, Clock } from 'lucide-react'
import { useSignals } from '../store/useSignals'
import { computeSignals, fetchSignals } from '../api/signals'
import { syncData, fetchBets } from '../api/tracker'

import SignalCard from '../components/signals/SignalCard'
import AccaCard from '../components/signals/AccaCard'
import { marketColor } from '../utils/format'
import TrackModal from '../components/tracker/TrackModal'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import useTier from '../hooks/useTier'
import { useAuth } from '../context/AuthContext'
import { useOnboarding } from '../hooks/useOnboarding'
import OnboardingModal from '../components/shared/OnboardingModal'

const FREE_SIGNAL_LIMIT = 5


function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
}

function shiftDate(iso, days) {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}


// ── Fallback card for system bets whose signal isn't in the loaded list ────────
// Mirrors SignalCard's visual structure using only TrackedBet fields.
function SystemBetFallbackCard({ bet }) {
  const hasScore  = bet.home_score != null && bet.away_score != null
  const kickoffStr = bet.kickoff_at
    ? new Date(bet.kickoff_at + (bet.kickoff_at.endsWith('Z') ? '' : 'Z'))
        .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  // Parse "Home vs Away" from match_name
  const vsSplit  = (bet.match_name || '').split(' vs ')
  const homeTeam = vsSplit[0] ?? bet.match_name
  const awayTeam = vsSplit.slice(1).join(' vs ') ?? ''

  // Implied probability from odds
  const impliedProb = bet.odds > 1 ? Math.round((1 / Number(bet.odds)) * 100) : null
  const pct         = impliedProb ?? 50
  const barColor    = pct >= 70 ? 'bg-emerald-400/70' : pct >= 50 ? 'bg-amber-400/70' : 'bg-orange-400/70'
  const pctColor    = pct >= 70 ? 'text-emerald-500'  : pct >= 50 ? 'text-amber-500'  : 'text-orange-500'

  const confidence = bet.dual_confidence
  const confStyle  = confidence === 'High'   ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                   : confidence === 'Medium' ? 'bg-amber-500/15   text-amber-400   border-amber-500/30'
                   : confidence === 'Low'    ? 'bg-rose-500/15    text-rose-400    border-rose-500/30'
                   : null

  const isWon     = bet.result_status === 'Won'
  const isLost    = bet.result_status === 'Lost'
  const statusCls = isWon ? 'text-green-400' : isLost ? 'text-red-400' : 'text-amber-400'
  const borderCls = isWon
    ? 'border-emerald-500/40 border-l-4 border-l-emerald-500'
    : isLost
      ? 'border-red-400/30 border-l-4 border-l-red-400'
      : 'border-amber-400/30 border-l-4 border-l-amber-400'

  return (
    <div className={`rounded-xl border bg-[var(--bg)] overflow-hidden ${borderCls}`}>
      <div className="px-4 py-3 space-y-2.5">
        {/* Match header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-h)] leading-tight">
              {homeTeam}{awayTeam ? ` vs ${awayTeam}` : ''}
            </h3>
            {bet.league && (
              <span className="text-[11px] text-[var(--text)] opacity-45 leading-none">{bet.league}</span>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
            {hasScore ? (
              <>
                <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-500">
                  <Clock size={10} />
                  FT
                </span>
                <span className="inline-flex items-center rounded-md border border-emerald-500/25 bg-emerald-500/8 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                  {bet.home_score}-{bet.away_score}
                </span>
              </>
            ) : kickoffStr ? (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--text)] opacity-75">
                <Clock size={10} />
                {kickoffStr}
              </span>
            ) : null}
          </div>
        </div>

        {/* Market + confidence + probability */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 flex-wrap min-w-0">
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full bg-[var(--code-bg)] border border-[var(--border)] ${marketColor(bet.market_type)}`}>
                {bet.market_type}
              </span>
              {confStyle && (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${confStyle}`}>
                  {confidence}
                </span>
              )}
            </div>
            {impliedProb != null && (
              <span className={`text-xl font-bold tabular-nums leading-none shrink-0 ${pctColor}`}>
                {impliedProb}%
              </span>
            )}
          </div>

          {/* Probability bar */}
          <div className="h-1.5 w-full rounded-full bg-[var(--code-bg)] overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
          </div>

          {/* Odds + result */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold font-mono text-[var(--accent)]">
              @{Number(bet.odds).toFixed(2)}
            </span>
            <div className="flex-1" />
            <span className={`text-xs font-bold ${statusCls}`}>{bet.result_status}</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-2">
        <span className="flex items-center gap-1 text-xs text-blue-400 font-semibold">
          <Bot size={11} />
          System Pick
        </span>
        <div className="flex-1" />
        <span className="text-[10px] text-[var(--text)] opacity-35">Stats Model</span>
      </div>
    </div>
  )
}

export default function SignalsPage({ settings, onDeepDive, onUpgrade, onNavigateToTracker, initialFilter, onFilterConsumed }) {
  const { isPro } = useTier()
  const { user } = useAuth()
  const isAdmin = !!user?.is_admin
  const { showOnboarding, completeOnboarding } = useOnboarding(user)
  const today = (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  })()
  // Tomorrow's fixtures are pre-synced every evening (8pm local) so picks can
  // be reviewed and placed the night before — the date picker allows it.
  const maxDate = (() => {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  })()

  const [date, setDate]             = useState(today)
  const [confidence, setConfidence] = useState('')
  const [agreement, setAgreement]   = useState('')

  const [market, setMarket]         = useState('')
  const [sortBy, setSortBy]         = useState('system')
  const [bestPerFixture, setBestPerFixture] = useState(true)
  const [showSavedOnly, setShowSavedOnly] = useState(false)
  const [showFinished, setShowFinished] = useState(false)

  const getSavedIds = () => { try { return JSON.parse(localStorage.getItem('Qwantej_saved_signals_v1') || '[]') } catch { return [] } }
  const [syncing, setSyncing]       = useState(false)
  const [computing, setComputing]   = useState(false)
  const [trackingSignal, setTrackingSignal] = useState(null)
  const [trackedToast, setTrackedToast]     = useState(null) // { market, match } | null
  // Tracks which filters came from Analytics so we can show the "from Analytics" banner
  const [analyticsFilter, setAnalyticsFilter] = useState(null) // { label, fields } | null
  // Set of "fixture_id:market" keys for picks already in the tracker
  const [trackedKeys, setTrackedKeys] = useState(new Set())
  // Subset of trackedKeys that are backend-auto-tracked system picks
  const [systemTrackedKeys, setSystemTrackedKeys] = useState(new Set())

  // Load today's bets once so we can badge already-tracked signals and show system stats
  const [systemStats, setSystemStats] = useState(null) // { total, won, lost, pending }
  const [systemBets, setSystemBets]   = useState([])
  const [showSystemBets, setShowSystemBets] = useState(true)
  useEffect(() => {
    fetchBets({ date_from: today, date_to: today })
      .then(bets => {
        setTrackedKeys(new Set(bets.map(b => `${b.fixture_id}:${b.market_type}`)))
        const sys = bets.filter(b => b.source_rule_key === 'system_auto' || b.source_rule_key === 'system_dual')
        setSystemTrackedKeys(new Set(sys.map(b => `${b.fixture_id}:${b.market_type}`)))
        setSystemBets(sys)
        if (sys.length > 0) {
          const won     = sys.filter(b => b.result_status === 'Won').length
          const lost    = sys.filter(b => b.result_status === 'Lost').length
          const pending = sys.filter(b => b.result_status === 'Pending').length
          setSystemStats({ total: sys.length, won, lost, pending })
        }
      })
      .catch(() => {})
  }, []) // eslint-disable-line

  // Consume initialFilter from Analytics page — apply it once, then clear
  useEffect(() => {
    if (!initialFilter) return
    if (initialFilter.market)     setMarket(initialFilter.market)
    if (initialFilter.confidence) setConfidence(initialFilter.confidence)
    if (initialFilter.agreement)  setAgreement(initialFilter.agreement)
setAnalyticsFilter(initialFilter)
    onFilterConsumed?.()
  }, [initialFilter]) // eslint-disable-line

function clearAnalyticsFilter() {
    setMarket('')
    setConfidence('')
    setAgreement('')
    setAnalyticsFilter(null)
  }


const dateInputRef = useRef(null)
  const { signals, hiddenHighConfidenceCount, loading, error, load, invalidate } = useSignals()
  // Map fixture_id:market → signal so we can render system-tracked bets as full cards
  const signalByKey = useMemo(() => {
    const map = new Map()
    for (const s of signals) map.set(`${s.fixture_id}:${s.market}`, s)
    return map
  }, [signals])

const params = {
    date,
    confidence:  confidence || undefined,
    agreement:   agreement  || undefined,
    market:      market     || undefined,
    sort_by:     sortBy,
    best_per_fixture: bestPerFixture,
    include_finished: showFinished || undefined,
  }

  useEffect(() => { load(params) }, [date, confidence, agreement, market, sortBy, bestPerFixture, showFinished]) // eslint-disable-line
const reload = () => load(params)

  const isToday    = date === today
  const isTomorrow = date === maxDate
  const isBusy     = syncing || computing

  // ── Client-side sort + EV filter ────────────────────────────────────────
  const displayedSignals = useMemo(() => {
    let list = [...signals]

    // Sort
    switch (sortBy) {
      case 'system':
        // The API already returns one best signal per fixture in authoritative system-rank order.
        break
      case 'probability':
        list.sort((a, b) => (b.bayesian?.prob ?? -Infinity) - (a.bayesian?.prob ?? -Infinity))
        break
      case 'kickoff': {
        const toUtc = v => v ? new Date(v.endsWith('Z') || v.includes('+') ? v : v + 'Z') : new Date(0)
        list.sort((a, b) => toUtc(a.kickoff_at) - toUtc(b.kickoff_at))
      }
        break
      case 'stake':
        list.sort((a, b) => (b.dual_recommended_stake_pct ?? 0) - (a.dual_recommended_stake_pct ?? 0))
        break
      case 'quality':
        list.sort((a, b) => (b.dual_quality_score ?? -Infinity) - (a.dual_quality_score ?? -Infinity))
        break
      default:
        break
    }

    if (showSavedOnly) {
      const savedIds = getSavedIds()
      list = list.filter(s => savedIds.includes(s.id))
    }


    return list
  }, [signals, sortBy, showSavedOnly]) // eslint-disable-line

  // Summary stats for the result bar
  const stats = useMemo(() => {
    if (!displayedSignals.length) return null
    const highConf = displayedSignals.filter(s => s.dual_confidence === 'High').length
    return { total: displayedSignals.length, highConf }
  }, [displayedSignals])

const _LIVE_SET = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT'])
  const hasLiveMatches = signals.some(s => _LIVE_SET.has((s.status || '').trim().toUpperCase()))

  async function handleSync() {
    setSyncing(true)
    try {
      await syncData(date, { force: true })
      await computeSignals(date)
      invalidate()
      await reload()
    } catch (e) { console.error(e) }
    finally { setSyncing(false) }
  }

  async function handleRecompute() {
    setComputing(true)
    try {
      await computeSignals(date)
      invalidate()
      await reload()
    } catch (e) { console.error(e) }
    finally { setComputing(false) }
  }

  // Auto-refresh every 5 min when LIVE matches are on screen (today only)
  const silentReload = useCallback(async () => {
    try { await reload() } catch { /* silent */ }
  }, [reload]) // eslint-disable-line

  useEffect(() => {
    if (!isToday || !hasLiveMatches) return
    const id = setInterval(silentReload, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [isToday, hasLiveMatches, silentReload])

  function trackingSourceFamily() {
    if (sortBy === 'system') return 'Signals Board'
    if (sortBy === 'quality') return 'Quality View'
    if (sortBy === 'probability') return 'Probability View'
    if (sortBy === 'stake') return 'Stake View'
    return 'Signals Board'
  }

  return (
    <div className="space-y-5">

      {showOnboarding && <OnboardingModal onComplete={completeOnboarding} />}

      {/* ── Toolbar ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
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
            title="Pick a date"
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

        {isAdmin && (
          <>
            <button
              onClick={handleRecompute}
              disabled={isBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)] disabled:opacity-50 transition-colors"
              title="Re-run engines on cached odds — no API call"
            >
              <RefreshCw size={13} className={computing ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">{computing ? 'Computing…' : 'Recompute'}</span>
              <span className="sm:hidden">{computing ? '…' : 'Run'}</span>
            </button>

            <button
              onClick={handleSync}
              disabled={isBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
              title="Pull fresh odds from API-Football for this date, then recompute"
            >
              <Download size={13} className={syncing ? 'animate-bounce' : ''} />
              <span className="hidden sm:inline">{syncing ? 'Syncing…' : 'Sync API'}</span>
              <span className="sm:hidden">{syncing ? '…' : 'Sync'}</span>
            </button>
          </>
        )}
      </div>

      {/* ── SIGNALS ───────────────────────────────────────────────────────── */}
      <div className="space-y-4">

        {/* ── System performance bar ────────────────────────────────────── */}
        {isToday && (systemStats || systemTrackedKeys.size > 0) && (() => {
          const tracked = systemStats?.total ?? systemTrackedKeys.size
          const won     = systemStats?.won ?? 0
          const lost    = systemStats?.lost ?? 0
          const settled = won + lost
          const hitRate = settled > 0 ? Math.round(won / settled * 100) : null
          return (
            <div className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/6 overflow-hidden">
              {/* Header bar */}
              <div
                className="flex items-center gap-3 px-4 py-2.5 text-xs flex-wrap cursor-pointer select-none"
                onClick={() => setShowSystemBets(s => !s)}
              >
                <span className="flex items-center gap-1.5 text-[var(--accent)] font-semibold shrink-0">
                  <Zap size={11} />
                  System Auto-Tracking
                </span>
                <span className="text-[var(--text)] opacity-80">
                  <span className="font-semibold text-[var(--text-h)]">{tracked}</span> pick{tracked !== 1 ? 's' : ''} tracked today
                </span>
                {settled > 0 && (
                  <>
                    <span className="text-[var(--text)] opacity-40">·</span>
                    <span className="text-[var(--text)] opacity-80">
                      <span className="font-semibold text-green-400">{won}W</span>{' / '}
                      <span className="font-semibold text-red-400">{lost}L</span>
                      {hitRate !== null && (
                        <span className="ml-1 font-semibold text-[var(--text-h)]">({hitRate}%)</span>
                      )}
                    </span>
                  </>
                )}
                {systemStats?.pending > 0 && (
                  <>
                    <span className="text-[var(--text)] opacity-40">·</span>
                    <span className="text-[var(--text)] opacity-60">{systemStats.pending} pending</span>
                  </>
                )}
                <button
                  onClick={e => { e.stopPropagation(); onNavigateToTracker() }}
                  className="ml-auto text-[var(--accent)] font-semibold hover:underline shrink-0"
                >
                  View in Tracker →
                </button>
                <ChevronDown
                  size={13}
                  className={`text-[var(--accent)] transition-transform duration-200 ${showSystemBets ? 'rotate-180' : ''}`}
                />
              </div>

              {/* Expandable bet list — rendered as full signal cards when signal data is available */}
              {showSystemBets && systemBets.length > 0 && (
                <div className="border-t border-[var(--accent)]/15 p-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {systemBets.map(bet => {
                      const sig = signalByKey.get(`${bet.fixture_id}:${bet.market_type}`)
                      if (sig) {
                        return (
                          <SignalCard
                            key={bet.id}
                            signal={sig}
                            rank={null}
                            isPro={isPro}
                            isTracked={true}
                            isAutoTracked={true}
                            onDeepDive={onDeepDive}
                          />
                        )
                      }
                      // Fallback card for bets whose signal isn't in the current loaded list
                      return <SystemBetFallbackCard key={bet.id} bet={bet} />
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        })()}

        {/* ── Analytics filter banner ───────────────────────────────────── */}
        {analyticsFilter && (
          <div className="flex items-center gap-3 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/8 px-4 py-2.5 text-sm">
            <span className="text-[var(--accent)] font-semibold shrink-0">From Analytics</span>
            <span className="flex-1 text-[var(--text)] opacity-85 text-xs">
              {analyticsFilter.label}
            </span>
            <button
              onClick={clearAnalyticsFilter}
              className="shrink-0 flex items-center gap-1 text-xs text-[var(--text)] opacity-65 hover:opacity-100 hover:text-[var(--text-h)] transition-colors"
              title="Clear this filter"
            >
              <X size={12} /> Clear filter
            </button>
          </div>
        )}

        {/* ── ACCA of the Day ───────────────────────────────────────────── */}
        <AccaCard />



        {/* ── Results-pending banner ───────────────────────────────────── */}
        {!loading && hasLiveMatches && (
          <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/8 px-4 py-2.5 text-sm">
            <AlertCircle size={14} className="text-amber-400 shrink-0" />
            <p className="flex-1 text-[var(--text)] opacity-85">
              {isToday
                ? <>Some matches are <span className="font-semibold text-amber-400">still in progress or recently finished</span> — sync to fetch the latest scores.</>
                : <>Results for this date <span className="font-semibold text-amber-400">weren&apos;t captured</span> when the games ended — sync to recover the final scores.</>
              }
            </p>
            <button
              onClick={handleSync}
              disabled={isBusy}
              className="shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500 text-white text-xs font-semibold hover:bg-amber-400 disabled:opacity-50 transition-colors"
            >
              <Download size={11} className={syncing ? 'animate-bounce' : ''} />
              {syncing ? 'Syncing…' : 'Sync Now'}
            </button>
          </div>
        )}

        {/* ── Result summary bar ────────────────────────────────────────── */}
        <div className="flex items-center gap-4 px-1 text-xs text-[var(--text)]">
          {stats && !loading && (
            <>
              <span><span className="font-semibold text-[var(--text-h)]">{stats.total}</span> match{stats.total !== 1 ? 'es' : ''}</span>
              {stats.highConf > 0 && (
                <span><span className="font-semibold text-[var(--accent)]">{stats.highConf}</span> high confidence</span>
              )}
            </>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => setShowFinished(v => !v)}
              title={showFinished ? 'Showing finished matches too — click to hide them' : 'Include finished matches with final scores (results review)'}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-full border text-[10px] font-semibold transition-colors ${
                showFinished
                  ? 'border-emerald-400/50 bg-emerald-500/15 text-emerald-400'
                  : 'border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)]'
              }`}
            >
              <Clock size={10} />
              Finished
            </button>
            <button
              onClick={() => setShowSavedOnly(v => !v)}
              title={showSavedOnly ? 'Showing saved signals only — click to show all' : 'Show saved signals only'}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-full border text-[10px] font-semibold transition-colors ${
                showSavedOnly
                  ? 'border-red-400/50 bg-red-500/15 text-red-300'
                  : 'border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)]'
              }`}
            >
              <Heart size={10} fill={showSavedOnly ? 'currentColor' : 'none'} />
              Saved
            </button>
            <button
              onClick={() => setBestPerFixture(v => !v)}
              title={bestPerFixture ? 'Currently showing best signal per game — click to see all signals per game' : 'Currently showing all signals per game — click to show only the best per game'}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-semibold transition-colors ${
                bestPerFixture
                  ? 'border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--text)] hover:text-[var(--text-h)] hover:bg-[var(--code-bg)]'
              }`}
            >
              <Target size={10} />
              {bestPerFixture ? 'One per match' : 'All per match'}
            </button>
          </div>
        </div>

        {/* Card-border legend — always visible so users don't need to open filters to decode colours */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-[var(--text)] opacity-60 px-1">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/60 border border-emerald-400 shrink-0"></span> High prob 70%+</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-500/60 border border-blue-400 shrink-0"></span> Bayesian only</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500/60 border border-amber-400 shrink-0"></span> Medium conf</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-500/60 border border-red-400 shrink-0"></span> Contradiction</span>
          <span className="flex items-center gap-1"><span className="inline-flex items-center px-1.5 rounded bg-blue-500/20 border border-blue-400/50 text-[9px] font-bold text-blue-300 shrink-0">1X/X2/12</span> Safer cover</span>
        </div>

        {loading && signals.length === 0 && (
          <div className="grid gap-3">
            {[...Array(5)].map((_, i) => (
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
                  <div className="ml-auto h-6 w-20 rounded-lg bg-[var(--border)]" />
                </div>
              </div>
            ))}
          </div>
        )}

        {loading && signals.length > 0 && (
          <div className="flex justify-center py-12">
            <LoadingSpinner size="lg" />
          </div>
        )}

        {error && signals.length === 0 && (
          <div className="rounded-lg border border-red-500/25 bg-red-500/8 px-6 py-8 text-center">
            <p className="text-sm text-red-400 font-semibold mb-2">Failed to load signals</p>
            <p className="text-xs text-slate-400 mb-4">{typeof error === 'string' ? error : 'Something went wrong. Please try again.'}</p>
            <button onClick={() => window.location.reload()} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition-colors">
              Retry
            </button>
          </div>
        )}

        {error && signals.length > 0 && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {!loading && !error && displayedSignals.length === 0 && (
          signals.length > 0 ? (
            /* Filters are active but nothing passes — invite the user to loosen them */
            <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-10 flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-full bg-[var(--code-bg)] flex items-center justify-center">
                <Search size={22} className="text-[var(--text)] opacity-40" />
              </div>
              <p className="text-sm font-semibold text-[var(--text-h)]">No signals match these filters</p>
              <p className="text-xs text-[var(--text)] opacity-75 max-w-xs">
                Try changing the confidence or market filter, or{' '}
                <button onClick={() => { setConfidence(''); setAgreement(''); setMarket(''); setShowSavedOnly(false) }} className="font-semibold text-[var(--accent)] hover:underline">reset all filters</button>.
              </p>
            </div>
          ) : (
            /* No signals at all for this date */
            <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-10 flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-full bg-[var(--code-bg)] flex items-center justify-center">
                <Zap size={22} className="text-[var(--text)] opacity-40" />
              </div>
              <p className="text-sm font-semibold text-[var(--text-h)]">No qualifying signals for {fmtDate(date)}</p>
              <p className="text-xs text-[var(--text)] opacity-75 max-w-sm">
                Our dual-model gate requires both the Bayesian and Poisson engines to agree at High confidence.
                Today&apos;s fixtures don&apos;t meet that threshold — typically because available matches are lopsided,
                or odds data is unavailable for the leagues playing.
              </p>
              <p className="text-xs text-[var(--text)] opacity-60 max-w-sm">
                Hit{' '}
                <button
                  onClick={handleSync}
                  disabled={isBusy}
                  className="font-semibold text-[var(--accent)] hover:underline disabled:opacity-50"
                >
                  Sync API
                </button>{' '}
                to pull fresh odds — if the Bayesian model finds value even without Poisson agreement,
                supplemental picks will appear below the main list.
              </p>
              {isToday && (
                <p className="text-[11px] text-[var(--text)] opacity-50 max-w-xs">
                  Auto-syncs run at 04:00, 19:00 and 23:00 UTC.
                </p>
              )}
            </div>
          )
        )}

        {!loading && displayedSignals.length > 0 && (() => {
          // Supplemental = Bayesian-only OR Both+Medium (Bayesian High but Poisson not grade A)
          const isSupplemental = s => s.dual_agreement === 'Bayesian Only'
          const primarySignals = displayedSignals.filter(s => !isSupplemental(s))
          const supplementalSignals = displayedSignals.filter(isSupplemental)
          // Free-tier limit applies across both sections combined, primary first
          const allOrdered = [...primarySignals, ...supplementalSignals]
          const freeSlice = isPro ? allOrdered.length : FREE_SIGNAL_LIMIT
          const visibleAll = allOrdered.slice(0, freeSlice)
          const visiblePrimary = visibleAll.filter(s => !isSupplemental(s))
          const visibleSupplemental = visibleAll.filter(isSupplemental)

          return (
            <div className="space-y-3">
              {/* Primary signals — Both + Poisson Only */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {visiblePrimary.map((signal, idx) => (
                <SignalCard
                  key={signal.id}
                  signal={signal}
                  rank={idx + 1}
                  isPro={isPro}
                  isTracked={trackedKeys.has(`${signal.fixture_id}:${signal.market}`) || systemTrackedKeys.has(`${signal.fixture_id}:${signal.market}`)}
                  isAutoTracked={systemTrackedKeys.has(`${signal.fixture_id}:${signal.market}`)}
                  onTrackPick={sig => setTrackingSignal({ ...sig, tracking_source_family: trackingSourceFamily() })}
                  onDeepDive={onDeepDive}
                />
              ))}
              </div>

              {/* Supplemental section — Bayesian Only picks */}
              {supplementalSignals.length > 0 && (
                <>
                  <div className="flex items-center gap-3 pt-2">
                    <div className="flex-1 h-px bg-blue-400/20" />
                    <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-blue-400/30 bg-blue-500/8">
                      <span className="text-[10px] font-bold text-blue-400 tracking-wide uppercase">Supplemental Picks</span>
                    </div>
                    <div className="flex-1 h-px bg-blue-400/20" />
                  </div>
                  <div className="rounded-lg border border-blue-400/25 bg-blue-500/6 px-4 py-3 text-xs text-[var(--text)] leading-relaxed">
                    <span className="font-semibold text-blue-300">Bayesian model only</span>
                    {' — '}our Bayesian engine found High-confidence value here, but the Poisson model didn&apos;t confirm. One engine vs two: treat these as lower-conviction picks and size stakes accordingly.
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  {visibleSupplemental.map((signal, idx) => (
                    <SignalCard
                      key={signal.id}
                      signal={signal}
                      rank={visiblePrimary.length + idx + 1}
                      isPro={isPro}
                      isTracked={trackedKeys.has(`${signal.fixture_id}:${signal.market}`) || systemTrackedKeys.has(`${signal.fixture_id}:${signal.market}`)}
                      isAutoTracked={systemTrackedKeys.has(`${signal.fixture_id}:${signal.market}`)}
                      onTrackPick={sig => setTrackingSignal({ ...sig, tracking_source_family: trackingSourceFamily() })}
                      onDeepDive={onDeepDive}
                    />
                  ))}
                  </div>
                </>
              )}

              {/* Peek cards — next 3 signals blurred for free users */}
              {!isPro && allOrdered.slice(freeSlice, freeSlice + 3).map((sig, i) => (
                <div key={sig.id || i} className="relative select-none pointer-events-none">
                  <div className="opacity-40 blur-sm">
                    <div className="rounded-xl border border-white/8 bg-white/4 h-40 flex flex-col justify-between p-4">
                      <div className="h-3 w-2/3 rounded bg-white/10" />
                      <div className="h-6 w-1/2 rounded bg-white/10" />
                      <div className="h-3 w-1/3 rounded bg-white/10" />
                    </div>
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="rounded-lg bg-black/70 px-3 py-1.5 text-xs text-white font-medium backdrop-blur-sm border border-white/10">
                      🔒 Pro only
                    </div>
                  </div>
                </div>
              ))}

              {/* Upgrade banner */}
              {!isPro && allOrdered.length > freeSlice && (
                <div className="rounded-lg border border-blue-500/30 bg-blue-500/8 px-4 py-3 text-center text-sm space-y-1">
                  <div>
                    <span className="text-slate-300">Viewing <strong className="text-white">{freeSlice} of {allOrdered.length}</strong> signals. </span>
                    <button onClick={onUpgrade} className="text-blue-400 hover:text-blue-300 underline underline-offset-2 font-medium">
                      Upgrade to Pro →
                    </button>
                  </div>
                  {hiddenHighConfidenceCount > 0 && (
                    <p className="text-[11px] text-emerald-400 font-medium">
                      {hiddenHighConfidenceCount} High-confidence · Both-engines pick{hiddenHighConfidenceCount > 1 ? 's' : ''} hidden behind the paywall
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })()}
      </div>

      {/* ── Post-track success toast ──────────────────────────────────────── */}
      {trackedToast && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border border-green-500/30 bg-[var(--bg)] shadow-xl text-sm animate-fade-in">
          <span className="text-green-400 font-semibold">✓ Tracked</span>
          <span className="text-[var(--text)] opacity-75 max-w-[220px] truncate">
            {trackedToast.market} · {trackedToast.match}
          </span>
          <button
            onClick={() => { setTrackedToast(null); onNavigateToTracker?.() }}
            className="shrink-0 text-xs font-semibold text-[var(--accent)] hover:underline"
          >
            View in Tracker →
          </button>
          <button onClick={() => setTrackedToast(null)} className="shrink-0 text-[var(--text)] opacity-70 hover:opacity-100">
            <span aria-label="dismiss">✕</span>
          </button>
        </div>
      )}

      {trackingSignal && (
        <TrackModal
          signal={trackingSignal}
          bankroll={settings?.bankroll}
          onClose={() => setTrackingSignal(null)}
          onTracked={() => {
            const sig = trackingSignal
            // Optimistically mark this fixture+market as tracked
            setTrackedKeys(prev => new Set([...prev, `${sig.fixture_id}:${sig.market}`]))
            setTrackingSignal(null)
            setTrackedToast({ market: sig.market, match: `${sig.home_team} vs ${sig.away_team}` })
            setTimeout(() => setTrackedToast(null), 6000)
          }}
        />
      )}

    </div>
  )
}
