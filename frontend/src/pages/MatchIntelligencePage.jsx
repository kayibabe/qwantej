import { useState, useEffect } from 'react'
import { ArrowLeft, Activity } from 'lucide-react'
import { fetchMatchInfo, fetchOddsMatrix } from '../api/signals'
import { fetchFixtureForecasts } from '../api/forecasts'
import LoadingSpinner from '../components/shared/LoadingSpinner'

// ── Small reusables (carried over from DeepDivePage) ─────────────────────────

function Tab({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap ${
        active
          ? 'border-[var(--accent)] text-[var(--accent)]'
          : 'border-transparent text-[var(--text)] hover:text-[var(--text-h)]'
      }`}
    >
      {label}
    </button>
  )
}

function FormBadge({ result }) {
  const colors = {
    W: 'bg-green-500 text-white',
    D: 'bg-yellow-500 text-white',
    L: 'bg-red-500 text-white',
  }
  return (
    <span className={`inline-flex items-center justify-center w-6 h-6 rounded text-xs font-bold ${colors[result] || 'bg-[var(--code-bg)] text-[var(--text)]'}`}>
      {result}
    </span>
  )
}

function StatBar({ label, homeVal, awayVal, homeRaw, awayRaw, invert = false }) {
  const total = (homeRaw || 0) + (awayRaw || 0)
  const homePct = total > 0 ? (homeRaw / total) * 100 : 50
  const awayPct = 100 - homePct
  const homeWins = invert ? homePct < awayPct : homePct >= awayPct
  return (
    <div className="grid grid-cols-[72px_1fr_72px] sm:grid-cols-[90px_1fr_90px] items-center gap-2 py-2">
      <span className={`text-xs sm:text-sm font-bold text-right tabular-nums ${homeWins ? 'text-[var(--text-h)]' : 'text-[var(--text)] opacity-75'}`}>{homeVal}</span>
      <div className="flex items-center gap-1.5">
        <div className="flex-1 h-2 rounded-full overflow-hidden bg-[var(--code-bg)] flex">
          <div className={`h-full rounded-full transition-all ${homeWins ? 'bg-green-500' : 'bg-[var(--text)] opacity-70'}`} style={{ width: `${homePct}%` }} />
        </div>
        <span className="text-[9px] sm:text-[10px] text-[var(--text)] opacity-55 w-16 sm:w-20 text-center shrink-0 leading-tight">{label}</span>
        <div className="flex-1 h-2 rounded-full overflow-hidden bg-[var(--code-bg)] flex justify-end">
          <div className={`h-full rounded-full transition-all ${!homeWins ? 'bg-green-500' : 'bg-[var(--text)] opacity-70'}`} style={{ width: `${awayPct}%` }} />
        </div>
      </div>
      <span className={`text-xs sm:text-sm font-bold text-left tabular-nums ${!homeWins ? 'text-[var(--text-h)]' : 'text-[var(--text)] opacity-75'}`}>{awayVal}</span>
    </div>
  )
}

function HighlightList({ highlights }) {
  if (!highlights?.length) return <p className="text-xs text-[var(--text)] opacity-65 py-2">Not enough historical data.</p>
  return (
    <ul className="space-y-2">
      {highlights.map((h, i) => (
        <li key={i} className="text-sm text-[var(--text)] leading-snug"
          dangerouslySetInnerHTML={{ __html: h.replace(/\*\*(.*?)\*\*/g, '<strong class="text-[var(--text-h)]">$1</strong>') }}
        />
      ))}
    </ul>
  )
}

function H2HRow({ match, homeTeam }) {
  const homeWon = match.home_score > match.away_score
  const awayWon = match.away_score > match.home_score
  const isHome  = match.home_team === homeTeam
  const weWon   = (isHome && homeWon) || (!isHome && awayWon)
  const drew    = match.home_score === match.away_score
  const bg      = weWon ? 'bg-green-500/15 border-green-500/30' : drew ? 'bg-yellow-500/10 border-yellow-500/30' : 'bg-red-500/10 border-red-500/30'
  const txt     = weWon ? 'text-green-400' : drew ? 'text-yellow-400' : 'text-red-400'
  const d = match.date ? new Date(match.date + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
  return (
    <div className={`flex items-center justify-between px-3 sm:px-4 py-3 rounded-lg border ${bg} mb-2`}>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-[var(--text-h)] truncate">{match.home_team} <span className="text-[var(--text)] opacity-65">vs</span> {match.away_team}</div>
        <div className="text-xs text-[var(--text)] opacity-75 mt-0.5">{d}</div>
      </div>
      <div className={`text-lg font-bold font-mono shrink-0 ml-3 ${txt}`}>{match.home_score} – {match.away_score}</div>
    </div>
  )
}

// ── Odds Comparison ───────────────────────────────────────────────────────────

function OddsMatrixTab({ loading, matrix }) {
  if (loading) return <div className="py-12 flex justify-center"><LoadingSpinner /></div>
  if (!matrix || matrix.rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg)] p-12 text-center">
        <p className="text-sm text-[var(--text)] opacity-80">No bookmaker odds available for this fixture.</p>
      </div>
    )
  }
  const { bookmakers, rows } = matrix
  const sharp = new Set(['Pinnacle', 'Bet365'])
  const grouped = {}
  for (const row of rows) {
    if (!grouped[row.market_type]) grouped[row.market_type] = []
    grouped[row.market_type].push(row)
  }
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text)] opacity-55">Best odds highlighted per row. Sharp books (Pinnacle, Bet365) used for EV reference.</p>
      {Object.entries(grouped).map(([marketType, mRows]) => (
        <div key={marketType} className="rounded-xl border border-[var(--border)] bg-[var(--bg)] overflow-hidden">
          <div className="px-4 py-2.5 bg-[var(--code-bg)] border-b border-[var(--border)]">
            <p className="text-xs font-semibold text-[var(--text-h)]">{marketType}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="px-3 py-2 text-left text-[var(--text)] opacity-80 font-medium whitespace-nowrap">Selection</th>
                  {bookmakers.map(bk => (
                    <th key={bk} className={`px-3 py-2 text-right font-medium whitespace-nowrap ${sharp.has(bk) ? 'text-amber-400' : 'text-[var(--text)] opacity-80'}`}>
                      {bk}{sharp.has(bk) ? ' ★' : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mRows.map((row, i) => {
                  const validOdds = bookmakers.map(bk => row.odds[bk]).filter(Boolean)
                  const maxOdd = validOdds.length ? Math.max(...validOdds) : null
                  return (
                    <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--code-bg)] transition-colors">
                      <td className="px-3 py-2.5 font-medium text-[var(--text-h)] whitespace-nowrap">{row.selection}</td>
                      {bookmakers.map(bk => {
                        const odd = row.odds[bk]
                        const isBest = odd && odd === maxOdd
                        return (
                          <td key={bk} className="px-3 py-2.5 text-right tabular-nums whitespace-nowrap">
                            {odd ? (
                              <span className={`font-mono font-semibold ${isBest ? 'text-emerald-400' : 'text-[var(--text)]'}`}>
                                {odd.toFixed(2)}{isBest && <span className="ml-1 text-[9px] text-emerald-400 opacity-70">best</span>}
                              </span>
                            ) : <span className="text-[var(--text)] opacity-25">—</span>}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Forecast tab — ensemble model output per market ───────────────────────────

function ForecastTab({ forecasts, loading }) {
  if (loading) return <div className="py-12 flex justify-center"><LoadingSpinner /></div>
  if (!forecasts.length) {
    return <p className="text-sm text-[var(--text)] opacity-75 py-8 text-center">No ensemble forecasts available for this fixture.</p>
  }

  // Group by market, show latest horizon only
  const byMarket = {}
  for (const f of forecasts) {
    if (!byMarket[f.market] || f.snapshot_at > byMarket[f.market].snapshot_at) {
      byMarket[f.market] = f
    }
  }
  const rows = Object.values(byMarket).sort((a, b) =>
    (b.calibrated_prob ?? b.ensemble_prob) - (a.calibrated_prob ?? a.ensemble_prob)
  )

  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text)] opacity-55">
        Ensemble = weighted combination of ZINB + Bayesian + Elo.
        Calibrated prob applies isotonic regression correction where available.
        Positive edge = fair odds better than market odds.
      </p>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--code-bg)]">
              <th className="px-3 py-2.5 text-left font-semibold text-[var(--text-h)] whitespace-nowrap">Market</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">ZINB</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Bayes</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Elo</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--accent)] whitespace-nowrap">Ensemble</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Calibrated</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Fair</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Market</th>
              <th className="px-3 py-2.5 text-right font-semibold text-[var(--text-h)] whitespace-nowrap">Edge</th>
              <th className="px-3 py-2.5 text-center font-semibold text-[var(--text-h)] whitespace-nowrap">Signal</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(f => {
              const ep = f.ensemble_prob
              const cp = f.calibrated_prob
              const edge = f.value_edge
              const edgeColor = edge == null ? '' : edge >= 0.10 ? 'text-emerald-400' : edge >= 0.04 ? 'text-amber-400' : 'text-orange-400'
              const isSignal = f.signal_type === 'SIGNAL'
              return (
                <tr key={f.id} className={`border-b border-[var(--border)] last:border-0 hover:bg-[var(--code-bg)] transition-colors ${isSignal ? 'bg-[var(--accent)]/3' : ''}`}>
                  <td className="px-3 py-2.5 font-medium text-[var(--text-h)] whitespace-nowrap">{f.market}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{f.zinb_prob != null ? `${Math.round(f.zinb_prob*100)}%` : '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{f.bayesian_prob != null ? `${Math.round(f.bayesian_prob*100)}%` : '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{f.elo_prob != null ? `${Math.round(f.elo_prob*100)}%` : '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[var(--accent)]">{Math.round(ep*100)}%</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-[var(--text-h)]">{cp != null ? `${Math.round(cp*100)}%` : '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--text)]">{f.fair_odds != null ? f.fair_odds.toFixed(2) : '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-mono text-[var(--text-h)]">{f.market_odds != null ? f.market_odds.toFixed(2) : '—'}</td>
                  <td className={`px-3 py-2.5 text-right tabular-nums font-semibold ${edgeColor}`}>
                    {edge != null ? `${edge >= 0 ? '+' : ''}${(edge*100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    {isSignal ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)]">
                        <Activity size={9} /> SIGNAL
                      </span>
                    ) : (
                      <span className="text-[10px] text-[var(--text)] opacity-35">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Snapshot history */}
      {forecasts.length > Object.keys(byMarket).length && (
        <details className="text-xs">
          <summary className="text-[var(--text)] opacity-60 cursor-pointer hover:opacity-100 select-none py-2">
            Show all {forecasts.length} snapshots across horizons →
          </summary>
          <div className="mt-2 overflow-x-auto rounded-xl border border-[var(--border)]">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--code-bg)]">
                  <th className="px-3 py-2 text-left font-semibold text-[var(--text-h)]">Market</th>
                  <th className="px-3 py-2 text-left font-semibold text-[var(--text-h)]">Horizon</th>
                  <th className="px-3 py-2 text-right font-semibold text-[var(--text-h)]">Ensemble</th>
                  <th className="px-3 py-2 text-right font-semibold text-[var(--text-h)]">Edge</th>
                  <th className="px-3 py-2 text-left font-semibold text-[var(--text-h)]">Snapshot at</th>
                </tr>
              </thead>
              <tbody>
                {[...forecasts].sort((a,b) => a.market.localeCompare(b.market) || b.snapshot_at.localeCompare(a.snapshot_at)).map(f => (
                  <tr key={f.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--code-bg)]">
                    <td className="px-3 py-2 text-[var(--text-h)]">{f.market}</td>
                    <td className="px-3 py-2 text-[var(--text)] opacity-70">{f.horizon}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold text-[var(--accent)]">{Math.round(f.ensemble_prob*100)}%</td>
                    <td className="px-3 py-2 text-right tabular-nums text-[var(--text)]">
                      {f.value_edge != null ? `${f.value_edge >= 0 ? '+' : ''}${(f.value_edge*100).toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-3 py-2 text-[var(--text)] opacity-55 whitespace-nowrap">
                      {new Date(f.snapshot_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MatchIntelligencePage({ fixtureId, onBack }) {
  const [matchInfo,    setMatchInfo]    = useState(null)
  const [forecasts,    setForecasts]    = useState([])
  const [oddsMatrix,   setOddsMatrix]   = useState(null)
  const [loading,      setLoading]      = useState(true)
  const [infoLoading,  setInfoLoading]  = useState(true)
  const [fcLoading,    setFcLoading]    = useState(true)
  const [oddsLoading,  setOddsLoading]  = useState(false)
  const [error,        setError]        = useState(null)
  const [activeTab,    setActiveTab]    = useState('overview')

  useEffect(() => {
    if (!fixtureId) return
    setLoading(false) // we have individual loaders

    fetchMatchInfo(fixtureId)
      .then(d => setMatchInfo(d))
      .catch(() => setMatchInfo(null))
      .finally(() => setInfoLoading(false))

    fetchFixtureForecasts(fixtureId)
      .then(d => setForecasts(Array.isArray(d) ? d : []))
      .catch(() => setForecasts([]))
      .finally(() => setFcLoading(false))
  }, [fixtureId])

  const firstForecast = forecasts[0] ?? {}
  const fixture = matchInfo?.fixture ?? {}
  const homeTeam = fixture.home_team || firstForecast.home_team || '—'
  const awayTeam = fixture.away_team || firstForecast.away_team || '—'
  const league   = fixture.league || firstForecast.league || ''
  const kickoffAt = fixture.kickoff_at || firstForecast.kickoff_at
  const kickoffStr = kickoffAt
    ? (() => {
        const utc = kickoffAt.endsWith('Z') || kickoffAt.includes('+') ? kickoffAt : kickoffAt + 'Z'
        return new Date(utc).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
      })()
    : ''
  const isFinished = ['FT', 'AET', 'PEN'].includes(fixture.status)
  const hs = matchInfo?.home_stats
  const as_ = matchInfo?.away_stats

  const TABS = [
    { id: 'overview',  label: 'Overview' },
    { id: 'stats',     label: 'Stats' },
    { id: 'forecast',  label: 'Forecast' },
    { id: 'h2h',       label: 'H2H' },
    { id: 'odds',      label: 'Odds' },
  ]

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-[var(--text)] hover:text-[var(--accent)] transition-colors">
        <ArrowLeft size={15} /> Back to Signals
      </button>

      {/* Fixture header */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg sm:text-xl font-bold text-[var(--text-h)] leading-snug">
              {homeTeam} <span className="text-[var(--text)] opacity-70 font-normal">vs</span> {awayTeam}
            </h2>
            <p className="text-xs sm:text-sm text-[var(--text)] opacity-75 mt-0.5">
              {league}{kickoffStr ? ` · ${kickoffStr}` : ''}
            </p>
          </div>
          {isFinished ? (
            <div className="text-2xl sm:text-3xl font-bold font-mono text-[var(--text-h)] shrink-0">
              {fixture.home_score} – {fixture.away_score}
            </div>
          ) : fixture.status ? (
            <span className="text-xs px-2 py-1 rounded-full border border-[var(--accent)] text-[var(--accent)] font-medium shrink-0">
              {fixture.status}
            </span>
          ) : null}
        </div>

        {hs && as_ && (
          <div className="flex items-center gap-4 mt-4 flex-wrap">
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-[var(--text)] opacity-80 mr-1 uppercase tracking-wide">Form</span>
              {hs.form.map((r, i) => <FormBadge key={i} result={r} />)}
            </div>
            <span className="text-xs text-[var(--text)] opacity-65">vs</span>
            <div className="flex items-center gap-1">
              {as_.form.map((r, i) => <FormBadge key={i} result={r} />)}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 border-b border-[var(--border)] overflow-x-auto scrollbar-none">
        {TABS.map(t => (
          <Tab
            key={t.id}
            label={t.label}
            active={activeTab === t.id}
            onClick={() => {
              setActiveTab(t.id)
              if (t.id === 'odds' && !oddsMatrix && !oddsLoading) {
                setOddsLoading(true)
                fetchOddsMatrix(fixtureId)
                  .then(d => setOddsMatrix(d))
                  .catch(() => setOddsMatrix({ bookmakers: [], rows: [] }))
                  .finally(() => setOddsLoading(false))
              }
            }}
          />
        ))}
      </div>

      {/* ── OVERVIEW ── */}
      {activeTab === 'overview' && (
        <div className="grid sm:grid-cols-2 gap-4">
          {[
            { team: homeTeam, highlights: matchInfo?.home_highlights },
            { team: awayTeam, highlights: matchInfo?.away_highlights },
          ].map(({ team, highlights }) => (
            <div key={team} className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 sm:p-5">
              <p className="text-sm font-semibold text-[var(--text-h)] mb-3">⚽ {team}</p>
              {infoLoading ? <LoadingSpinner /> : <HighlightList highlights={highlights} />}
            </div>
          ))}
        </div>
      )}

      {/* ── STATS ── */}
      {activeTab === 'stats' && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 sm:p-5">
          {infoLoading ? <LoadingSpinner /> : !hs ? (
            <p className="text-sm text-[var(--text)] opacity-75 py-4 text-center">No historical stats available yet.</p>
          ) : (
            <>
              <div className="grid grid-cols-[72px_1fr_72px] sm:grid-cols-[90px_1fr_90px] gap-2 mb-1">
                <span className="text-xs font-semibold text-[var(--accent)] text-right truncate">{homeTeam}</span>
                <span />
                <span className="text-xs font-semibold text-[var(--accent)] text-left truncate">{awayTeam}</span>
              </div>
              <StatBar label="PLAYED"      homeVal={hs.played}            awayVal={as_.played}            homeRaw={hs.played}             awayRaw={as_.played} />
              <StatBar label="WIN %"       homeVal={`${hs.win_pct}%`}     awayVal={`${as_.win_pct}%`}     homeRaw={hs.win_pct}            awayRaw={as_.win_pct} />
              <StatBar label="DRAW %"      homeVal={`${hs.draw_pct}%`}    awayVal={`${as_.draw_pct}%`}    homeRaw={hs.draw_pct}           awayRaw={as_.draw_pct} />
              <StatBar label="LOST %"      homeVal={`${hs.loss_pct}%`}    awayVal={`${as_.loss_pct}%`}    homeRaw={hs.loss_pct}           awayRaw={as_.loss_pct} invert />
              <StatBar label="GOAL DIFF"   homeVal={hs.goal_difference}   awayVal={as_.goal_difference}   homeRaw={Math.max(0, hs.goal_difference + 10)} awayRaw={Math.max(0, as_.goal_difference + 10)} />
              <StatBar label="AVG FOR"     homeVal={hs.avg_goals_for}     awayVal={as_.avg_goals_for}     homeRaw={hs.avg_goals_for}      awayRaw={as_.avg_goals_for} />
              <StatBar label="AVG AGAINST" homeVal={hs.avg_goals_against} awayVal={as_.avg_goals_against} homeRaw={hs.avg_goals_against}  awayRaw={as_.avg_goals_against} invert />
              <StatBar label="PPG"         homeVal={hs.ppg}               awayVal={as_.ppg}               homeRaw={hs.ppg}                awayRaw={as_.ppg} />
              <p className="text-[10px] text-[var(--text)] opacity-55 mt-3 text-center">
                Last {hs.played} ({homeTeam}) · {as_.played} ({awayTeam}) completed matches
              </p>
            </>
          )}
        </div>
      )}

      {/* ── FORECAST ── */}
      {activeTab === 'forecast' && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 sm:p-5">
          <h3 className="text-sm font-semibold text-[var(--text-h)] mb-4 flex items-center gap-2">
            <Activity size={14} className="text-[var(--accent)]" />
            Ensemble Forecast — All Markets
          </h3>
          <ForecastTab forecasts={forecasts} loading={fcLoading} />
        </div>
      )}

      {/* ── H2H ── */}
      {activeTab === 'h2h' && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] p-4 sm:p-5">
          <h3 className="text-sm font-semibold text-[var(--text-h)] mb-4">Head-to-Head</h3>
          {infoLoading ? <LoadingSpinner /> : !matchInfo?.h2h?.length ? (
            <p className="text-sm text-[var(--text)] opacity-75 py-4 text-center">No previous meetings found.</p>
          ) : (
            <>
              {(() => {
                const hw = matchInfo.h2h.filter(m => {
                  const hWon = m.home_score > m.away_score
                  return (m.home_team === homeTeam && hWon) || (m.away_team === homeTeam && !hWon && m.home_score !== m.away_score)
                }).length
                const aw = matchInfo.h2h.filter(m => {
                  const aWon = m.away_score > m.home_score
                  return (m.away_team === awayTeam && aWon) || (m.home_team === awayTeam && !aWon && m.home_score !== m.away_score)
                }).length
                const draws = matchInfo.h2h.filter(m => m.home_score === m.away_score).length
                return (
                  <div className="grid grid-cols-3 py-3 mb-4 rounded-lg bg-[var(--code-bg)] text-center">
                    <div><div className="text-xl sm:text-2xl font-bold text-green-400">{hw}</div><div className="text-[10px] sm:text-xs text-[var(--text)] opacity-75 mt-0.5 truncate px-1">{homeTeam} wins</div></div>
                    <div><div className="text-xl sm:text-2xl font-bold text-yellow-400">{draws}</div><div className="text-[10px] sm:text-xs text-[var(--text)] opacity-75 mt-0.5">Draws</div></div>
                    <div><div className="text-xl sm:text-2xl font-bold text-red-400">{aw}</div><div className="text-[10px] sm:text-xs text-[var(--text)] opacity-75 mt-0.5 truncate px-1">{awayTeam} wins</div></div>
                  </div>
                )
              })()}
              {matchInfo.h2h.map((m, i) => <H2HRow key={i} match={m} homeTeam={homeTeam} />)}
            </>
          )}
        </div>
      )}

      {/* ── ODDS ── */}
      {activeTab === 'odds' && (
        <OddsMatrixTab matrix={oddsMatrix} loading={oddsLoading} />
      )}
    </div>
  )
}
