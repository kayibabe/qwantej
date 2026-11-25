import { useState, useEffect, useCallback, useRef } from 'react'
import { localDateString } from './DailyTickets'
import { formatMarket, formatSelection, formatStage, formatTicketType, selectionRepeatsMarket, ticketTierBadgeClass } from '../lib/api'

interface PipelineSchedule {
  schedules: { name: string; hour_utc: number; minute_utc: number; time_cat: string }[]
  jobs: { id: string; next_run_utc: string | null }[]
  automation?: { startup_catchup_enabled: boolean; watchdog_interval_minutes: number; automatic_retry_limit: number; settlement_interval_minutes: number; settlement_startup_lookback_days: number; scheduler_leader_lock_enabled: boolean; scheduler_leader_lock_name: string; latest_due_window: string | null; latest_due_target_date: string | null }
}
interface PipelineStatus { id: number; target_date: string; run_type: string; trigger_source: string | null; scheduled_window: string | null; status: string; current_stage: string | null; error_details: string | null; started_at: string | null; completed_at: string | null; stages: { name: string; status: string; retry_count: number; input_count: number; output_count: number; error_details: string | null }[] }
interface AutomationAlert { id: number; severity: string; task_name: string; target_date: string | null; title: string; detail: string; occurrence_count: number; resolved: boolean; first_seen_at: string; last_seen_at: string }
interface OperationalStatus {
  observed_at: string
  latest_run: { id: number; target_date: string; run_type: string; status: string; current_stage: string | null; completed_at: string | null } | null
  latest_due_window: { name: string; target_date: string; needs_catchup: boolean; reason: string } | null
  upcoming_stale_odds_predictions: number
  upcoming_stale_odds_records: { prediction_id: number; match_id: number }[]
  upcoming_recommendation_quote_coverage: { eligible: number; covered: number; fraction: number | null; lookahead_hours: number; max_quote_age_hours: number; affected_records: { prediction_id: number; match_id: number }[] }
  api_football_quota: { daily_limit: number | null; daily_remaining: number | null; minute_limit: number | null; minute_remaining: number | null; observed_at: string; low: boolean } | null
  finished_match_refresh_lag: number
  active_alerts: number
}
interface MarketPolicyShadowTicket {
  ticket_type: string
  legs: { prediction_id: number; match_id: number; market: string; selection: string; odds: number; source_odds_at: string | null }[]
  combined_odds: number
  combined_probability: number
}
interface MarketPolicyShadow {
  target_date: string
  status: 'captured' | 'not_captured'
  mode: 'shadow_only'
  control_unchanged: boolean
  policy_version?: string
  excluded_markets?: string[]
  captured_at?: string
  qualified_pool?: number
  public_ticket_count?: number
  missing_public_ticket_types?: string[]
  tickets?: (MarketPolicyShadowTicket | null)[]
}
interface UserRecord { id: number; username: string; email: string; role: 'user' | 'admin'; plan: 'free' | 'pro'; account_status: 'active' | 'suspended' | 'pending'; created_at: string | null; last_login_at: string | null }
type UserForm = Omit<UserRecord, 'id' | 'created_at' | 'last_login_at'> & { password: string }
const emptyUserForm: UserForm = { username: '', email: '', password: '', role: 'user', plan: 'free', account_status: 'active' }

function fmt2(n: number) { return String(n).padStart(2, '0') }

interface FetchResult<T> { ok: boolean; data: T }
async function fetchJson<T>(url: string, fallback: T): Promise<FetchResult<T>> {
  try {
    const response = await fetch(url)
    if (!response.ok) return { ok: false, data: fallback }
    return { ok: true, data: await response.json() }
  } catch {
    return { ok: false, data: fallback }
  }
}

const JOB_LABELS: Record<string, string> = {
  daily_pipeline_early: 'Next early pipeline',
  daily_pipeline_morning: 'Next morning pipeline',
  paper_ticket_settlement: 'Next settlement',
  live_match_status_refresh: 'Next live refresh',
  pipeline_automation_watchdog: 'Next automation check',
  weekly_shadow_model_learning: 'Next shadow learning',
}

export default function AdminPage() {
  const [schedule, setSchedule] = useState<PipelineSchedule | null>(null)
  const [pipelineDate, setPipelineDate] = useState(localDateString())
  const [triggering, setTriggering] = useState(false)
  const [triggerMsg, setTriggerMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [pipelineRuns, setPipelineRuns] = useState<PipelineStatus[]>([])
  const [alerts, setAlerts] = useState<AutomationAlert[]>([])
  const [operational, setOperational] = useState<OperationalStatus | null>(null)
  const [marketPolicyShadow, setMarketPolicyShadow] = useState<MarketPolicyShadow | null>(null)
  const [refreshingSafety, setRefreshingSafety] = useState(false)
  const [historyStart, setHistoryStart] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10)
  })
  const [historyEnd, setHistoryEnd] = useState(localDateString())
  const [syncingHistory, setSyncingHistory] = useState(false)
  const [users, setUsers] = useState<UserRecord[]>([])
  const [userForm, setUserForm] = useState<UserForm>(emptyUserForm)
  const [editingUserId, setEditingUserId] = useState<number | null>(null)
  const [userBusy, setUserBusy] = useState(false)
  const [userError, setUserError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadIssues, setLoadIssues] = useState<string[]>([])
  const loadId = useRef(0)

  const load = useCallback(async () => {
    const id = ++loadId.current
    setLoading(true)
    const [sched, status, alertData, ops, shadow, userData] = await Promise.all([
      fetchJson<PipelineSchedule | null>('/api/v1/admin/pipeline/schedule', null),
      fetchJson<{ runs: PipelineStatus[] }>('/api/v1/admin/pipeline/status', { runs: [] }),
      fetchJson<{ alerts: AutomationAlert[] }>('/api/v1/admin/alerts', { alerts: [] }),
      fetchJson<OperationalStatus | null>('/api/v1/admin/operational-status', null),
      fetchJson<MarketPolicyShadow | null>(`/api/v1/selections/market-policy-shadow?date=${localDateString()}`, null),
      fetchJson<{ users: UserRecord[] }>('/api/v1/admin/users', { users: [] }),
    ])
    if (id !== loadId.current) return
    // Keep the last successful value when a single report fails: an error must
    // not be indistinguishable from an empty result or erase what was loaded.
    const failures: string[] = []
    if (sched.ok) setSchedule(sched.data)
    else failures.push('pipeline schedule')
    if (status.ok) setPipelineRuns(status.data.runs)
    else failures.push('pipeline runs')
    if (alertData.ok) setAlerts(alertData.data.alerts)
    else failures.push('automation alerts')
    if (ops.ok) setOperational(ops.data)
    else failures.push('operational status')
    if (shadow.ok) setMarketPolicyShadow(shadow.data)
    else failures.push('market policy shadow')
    if (userData.ok) setUsers(userData.data.users)
    else failures.push('user accounts')
    setLoadIssues(failures)
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
    return () => { loadId.current += 1 }
  }, [load])
  useEffect(() => {
    let active = true
    let pollId = 0
    const timer = window.setInterval(() => {
      const id = ++pollId
      fetch('/api/v1/admin/pipeline/status')
        .then(r => r.ok ? r.json() : { runs: [] })
        .then(data => { if (active && id === pollId) setPipelineRuns(data.runs ?? []) })
        .catch(() => { /* keep the last known runs; the retry banner explains staleness */ })
    }, 10000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  function updateUserField<K extends keyof UserForm>(field: K, value: UserForm[K]) {
    setUserForm(current => ({ ...current, [field]: value }))
  }

  function editUser(user: UserRecord) {
    setEditingUserId(user.id)
    setUserForm({ username: user.username, email: user.email, password: '', role: user.role, plan: user.plan, account_status: user.account_status })
    setUserError(null)
  }

  async function saveUser(event: React.FormEvent) {
    event.preventDefault(); setUserBusy(true); setUserError(null)
    const body = { ...userForm, ...(editingUserId && !userForm.password ? { password: undefined } : {}) }
    if (editingUserId && !userForm.password) delete (body as { password?: string }).password
    try {
      const res = await fetch(editingUserId ? `/api/v1/admin/users/${editingUserId}` : '/api/v1/admin/users', { method: editingUserId ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setUserError(data.detail ?? 'Could not save user'); return }
      setUserForm(emptyUserForm); setEditingUserId(null); await load()
    } catch {
      setUserError('Could not reach the server. The account was not changed.')
    } finally { setUserBusy(false) }
  }

  async function removeUser(user: UserRecord) {
    if (!window.confirm(`Delete ${user.username}?`)) return
    try {
      const res = await fetch(`/api/v1/admin/users/${user.id}`, { method: 'DELETE' })
      if (!res.ok) { const data = await res.json().catch(() => ({})); setUserError(data.detail ?? 'Could not delete user'); return }
      if (editingUserId === user.id) { setEditingUserId(null); setUserForm(emptyUserForm) }
      await load()
    } catch {
      setUserError('Could not reach the server. The account was not deleted.')
    }
  }

  async function resolveAlert(id: number) {
    try {
      const res = await fetch(`/api/v1/admin/alerts/${id}/resolve`, { method: 'POST' })
      if (!res.ok) { setTriggerMsg({ ok: false, text: 'Could not resolve this alert. Try again.' }); return }
      setAlerts(current => current.filter(alert => alert.id !== id))
    } catch {
      setTriggerMsg({ ok: false, text: 'Could not reach the server. The alert is still active.' })
    }
  }

  async function refreshSafetyStatus() {
    setRefreshingSafety(true)
    try {
      const [ops, alertData] = await Promise.all([
        fetchJson<OperationalStatus | null>('/api/v1/admin/operational-status', null),
        fetchJson<{ alerts: AutomationAlert[] }>('/api/v1/admin/alerts', { alerts: [] }),
      ])
      if (ops.ok) setOperational(ops.data)
      if (alertData.ok) setAlerts(alertData.data.alerts)
      if (!ops.ok || !alertData.ok) setLoadIssues(current => [...new Set([...current, 'operational status or alerts'])])
      else setLoadIssues(current => current.filter(issue => issue !== 'operational status' && issue !== 'automation alerts'))
    } finally {
      setRefreshingSafety(false)
    }
  }

  const alertGroups = Array.from(alerts.reduce((groups, alert) => {
    const key = `${alert.task_name}\u0000${alert.title}\u0000${alert.detail}`
    const group = groups.get(key) ?? []
    group.push(alert)
    groups.set(key, group)
    return groups
  }, new Map<string, AutomationAlert[]>()).values())
    .map(rows => ({
      rows: rows.sort((left, right) => right.last_seen_at.localeCompare(left.last_seen_at)),
      lastSeen: rows.reduce((latest, row) => row.last_seen_at > latest ? row.last_seen_at : latest, rows[0]?.last_seen_at ?? ''),
      occurrences: rows.reduce((total, row) => total + row.occurrence_count, 0),
    }))
    .sort((left, right) => right.lastSeen.localeCompare(left.lastSeen))

  async function triggerPipeline() {
    setTriggering(true)
    setTriggerMsg(null)
    try {
      const res = await fetch(`/api/v1/admin/pipeline/trigger?target_date=${pipelineDate}`, { method: 'POST' })
      const data = await res.json()
      setTriggerMsg({ ok: res.ok, text: res.ok ? `Pipeline queued for ${data.target_date}` : data.detail ?? 'Error' })
    } catch {
      setTriggerMsg({ ok: false, text: 'Failed to reach server' })
    } finally {
      setTriggering(false)
    }
  }

  async function syncHistory() {
    setSyncingHistory(true); setTriggerMsg(null)
    try {
      const res = await fetch('/api/v1/admin/historical/sync', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period_start: historyStart, period_end: historyEnd }),
      })
      const data = await res.json()
      setTriggerMsg({ ok: res.ok, text: res.ok ? `Historical sync queued for ${data.period_start} to ${data.period_end}` : data.detail ?? 'Error' })
    } catch { setTriggerMsg({ ok: false, text: 'Failed to reach server' }) }
    finally { setSyncingHistory(false) }
  }

  const cardClass = 'rounded-xl border border-slate-200 bg-white p-5 shadow-sm'
  const cardTitleClass = 'text-base font-bold tracking-tight text-slate-900'
  const hintClass = 'text-base leading-relaxed text-slate-600'
  const labelClass = 'text-sm font-medium text-slate-600'
  const valueClass = 'text-sm text-slate-900 text-right font-mono tabular-nums'
  const rowClass = 'flex min-h-11 items-start justify-between gap-4 border-b border-slate-100 py-3 last:border-b-0'
  const inputClass = 'h-11 rounded-lg border border-slate-200 bg-white px-3 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-700/20 focus:border-emerald-700'
  const primaryBtnClass = 'inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const secondaryBtnClass = 'inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const dangerBtnClass = 'inline-flex min-h-11 items-center justify-center rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600'
  const disclosureClass = 'mt-4 rounded-lg border border-slate-200 bg-slate-50/70 px-4 py-3'
  const summaryClass = 'min-h-11 cursor-pointer text-sm font-semibold text-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700'
  const statusBadgeClass = (status: string) => {
    const base = 'inline-flex items-center rounded-full border px-2.5 py-1 text-sm font-semibold'
    if (status === 'failed') return `${base} border-red-200 bg-red-50 text-red-700`
    if (status === 'completed' || status === 'success') return `${base} border-emerald-200 bg-emerald-50 text-emerald-700`
    if (status === 'running' || status === 'queued') return `${base} border-sky-200 bg-sky-50 text-sky-700`
    return `${base} border-slate-200 bg-slate-50 text-slate-700`
  }

  const hasLoadedData = Boolean(schedule || operational || marketPolicyShadow || pipelineRuns.length || alerts.length || users.length)

  return (
    <div className="page-content space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-slate-600">System area</p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Administration</h1>
          <p className="text-base leading-relaxed text-slate-600">Monitor publication, recover missed runs, and manage access.</p>
        </div>
        <span className="inline-flex min-h-11 items-center gap-2 self-start rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-600" aria-hidden="true" /> Restricted to administrators</span>
      </header>

      <div aria-live="polite">
        {triggerMsg && (
          <div className={`mb-3 flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-base ${triggerMsg.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`} role={triggerMsg.ok ? 'status' : 'alert'}>
            <span>{triggerMsg.text}</span>
            <button type="button" className="min-h-11 min-w-11 shrink-0 text-current hover:underline cursor-pointer" onClick={() => setTriggerMsg(null)} aria-label="Dismiss message">×</button>
          </div>
        )}
        {loadIssues.length > 0 && (
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-base text-amber-900" role="alert">
            <span><strong>Some reports are out of date.</strong> Could not refresh: {loadIssues.join(', ')}. Last successful values remain visible.</span>
            <button type="button" className={secondaryBtnClass} onClick={() => void load()} disabled={loading}>Retry reports</button>
          </div>
        )}
        {loading && !hasLoadedData && <p className="mb-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-base text-slate-700" role="status">Loading administration reports…</p>}
      </div>

      <main className="grid gap-6 xl:grid-cols-2">
        <section className={cardClass} aria-labelledby="admin-safety-title">
          <h2 id="admin-safety-title" className={cardTitleClass}>Operational safety</h2>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className={hintClass}>Read-only health signals from the last check. Investigate before any manual intervention.</p>
            <button type="button" className={secondaryBtnClass} onClick={() => void refreshSafetyStatus()} disabled={refreshingSafety}>{refreshingSafety ? 'Refreshing…' : 'Refresh safety status'}</button>
          </div>
          {operational ? (
            <div className="mt-4">
              <div className={rowClass}><span className={labelClass}>Observed at</span><span className={valueClass}>{new Date(operational.observed_at).toLocaleString()}</span></div>
              <div className={rowClass}><span className={labelClass}>Latest pipeline</span><span className="text-right text-sm text-slate-900">{operational.latest_run ? <><span className={statusBadgeClass(operational.latest_run.status)}>{formatStage(operational.latest_run.status)}</span> · <span className="font-mono tabular-nums">{operational.latest_run.target_date}</span>{operational.latest_run.current_stage ? ` · ${formatStage(operational.latest_run.current_stage)}` : ''}</> : <span className="text-slate-600">No run recorded</span>}</span></div>
              <div className={rowClass}><span className={labelClass}>Scheduled catch-up</span><span className="text-right text-sm text-slate-900">{operational.latest_due_window ? operational.latest_due_window.needs_catchup ? `Required · ${operational.latest_due_window.reason}` : 'Current' : 'No window due'}</span></div>
              <div className={rowClass}><span className={labelClass}>Upcoming stale odds predictions</span><span className={`${valueClass} ${operational.upcoming_stale_odds_predictions ? 'text-red-700' : ''}`}>{operational.upcoming_stale_odds_predictions} stale or missing</span></div>
              <div className={rowClass}><span className={labelClass}>Fresh quote coverage · RECOMMEND predictions</span><span className="text-right text-sm text-slate-900">{operational.upcoming_recommendation_quote_coverage.eligible === 0 ? `No RECOMMEND predictions due within ${operational.upcoming_recommendation_quote_coverage.lookahead_hours} hours` : `${operational.upcoming_recommendation_quote_coverage.covered}/${operational.upcoming_recommendation_quote_coverage.eligible} fresh (${Math.round((operational.upcoming_recommendation_quote_coverage.fraction ?? 0) * 100)}%)`}</span></div>
              <details className={disclosureClass}>
                <summary className={summaryClass}>Secondary diagnostics and affected records</summary>
                <div className="mt-3 space-y-3">
                  {operational.upcoming_stale_odds_predictions > 0 && <div className="flex flex-wrap gap-x-3 gap-y-2 text-sm"><span className="text-slate-600">Inspect stale scheduled predictions</span>{operational.upcoming_stale_odds_records.slice(0, 5).map(row => <a key={row.prediction_id} href={`/match/${row.match_id}?prediction_id=${row.prediction_id}`} className="inline-flex min-h-11 items-center text-emerald-700 hover:text-emerald-800">Match {row.match_id} · prediction {row.prediction_id}</a>)}</div>}
                  {operational.upcoming_recommendation_quote_coverage.affected_records.length > 0 && <div className="flex flex-wrap gap-x-3 gap-y-2 text-sm"><span className="text-slate-600">RECOMMEND predictions missing a fresh pre-kickoff quote</span>{operational.upcoming_recommendation_quote_coverage.affected_records.slice(0, 5).map(row => <a key={row.prediction_id} href={`/match/${row.match_id}?prediction_id=${row.prediction_id}`} className="inline-flex min-h-11 items-center text-emerald-700 hover:text-emerald-800">Match {row.match_id} · prediction {row.prediction_id}</a>)}</div>}
                  <p className={hintClass}>Freshness covers scheduled prediction rows kicking off within {operational.upcoming_recommendation_quote_coverage.lookahead_hours} hours. Quote coverage counts only rows labelled RECOMMEND and requires a source quote no older than {operational.upcoming_recommendation_quote_coverage.max_quote_age_hours} hours, captured before kickoff. Published ticket legs are tracked separately.</p>
                  <div className={rowClass}><span className={labelClass}>API-Football daily quota</span><span className={valueClass}>{operational.api_football_quota?.daily_limit && operational.api_football_quota.daily_remaining !== null ? `${operational.api_football_quota.daily_remaining}/${operational.api_football_quota.daily_limit} remaining` : 'No recent quota headers'}</span></div>
                  <div className={rowClass}><span className={labelClass}>Finished-result refresh</span><span className={valueClass}>{operational.finished_match_refresh_lag ? `${operational.finished_match_refresh_lag} delayed` : 'Current'}</span></div>
                  <div className={rowClass}><span className={labelClass}>Active alert records</span><span className={valueClass}>{operational.active_alerts}</span></div>
                </div>
              </details>
            </div>
          ) : <div className="mt-4 text-base text-slate-600">Operational status has not loaded yet. Use “Retry reports” if this persists.</div>}
        </section>

        <section className={cardClass} aria-labelledby="admin-shadow-title">
          <h2 id="admin-shadow-title" className={cardTitleClass}>Market policy shadow</h2>
          <p className={`${hintClass} mt-2`}>Shadow-only comparison for {marketPolicyShadow?.target_date ?? 'today'}. The control portfolio is unchanged.</p>
          {!marketPolicyShadow ? <div className="mt-4 text-base text-slate-600">The frozen comparison is not available. Use “Retry reports” if this persists.</div> : marketPolicyShadow.status === 'not_captured' ? (
            <div className="mt-4 text-base text-slate-600">No frozen comparison was captured for {marketPolicyShadow.target_date}.</div>
          ) : (
            <>
              <div className="mt-4">
                <div className={rowClass}><span className={labelClass}>Policy</span><span className={valueClass}>{marketPolicyShadow.policy_version ?? 'Unavailable'}</span></div>
                <div className={rowClass}><span className={labelClass}>Excluded markets</span><span className="text-right text-sm text-slate-900">{marketPolicyShadow.excluded_markets?.join(', ') || 'None'}</span></div>
                <div className={rowClass}><span className={labelClass}>Qualified pool</span><span className={valueClass}>{marketPolicyShadow.qualified_pool ?? '—'}</span></div>
                <div className={rowClass}><span className={labelClass}>Comparable public tiers</span><span className={valueClass}>{marketPolicyShadow.public_ticket_count ?? 0} / 3</span></div>
                {marketPolicyShadow.missing_public_ticket_types?.length ? <div className={rowClass}><span className={labelClass}>Missing tiers</span><span className="flex flex-wrap justify-end gap-2">{marketPolicyShadow.missing_public_ticket_types.map(type => <span className={`${ticketTierBadgeClass(type)} inline-flex min-h-11 items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-semibold text-slate-700`} key={type}>{formatTicketType(type)}</span>)}</span></div> : null}
              </div>
              <details className={disclosureClass}>
                <summary className={summaryClass}>Inspect frozen counterfactual tickets</summary>
                <div className="mt-3 space-y-3">
                  {(marketPolicyShadow.tickets ?? []).filter((ticket): ticket is MarketPolicyShadowTicket => ticket !== null).map(ticket => (
                    <div className="rounded-lg border border-slate-200 bg-white p-4 text-base text-slate-700" key={ticket.ticket_type}>
                      <div className="flex flex-wrap items-center gap-2"><strong className="text-slate-900">{formatStage(ticket.ticket_type)}</strong><span>{ticket.legs.length} legs · <span className="font-mono tabular-nums">{ticket.combined_odds.toFixed(2)}</span> odds · <span className="font-mono tabular-nums">{(ticket.combined_probability * 100).toFixed(1)}%</span> model probability</span></div>
                      <p className="mt-2 leading-relaxed text-slate-600">{ticket.legs.map(leg => `${selectionRepeatsMarket(leg.market, leg.selection) ? formatSelection(leg.selection) : `${formatMarket(leg.market)}: ${formatSelection(leg.selection)}`} (${leg.odds.toFixed(2)})`).join(' · ')}</p>
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
        </section>

        <section className={cardClass} aria-labelledby="admin-pipeline-title">
          <h2 id="admin-pipeline-title" className={cardTitleClass}>Daily pipeline</h2>
          {schedule && (
            <div className="mt-4">
              <div className={rowClass}>
                <span className={labelClass}>Schedule</span>
                <span className="text-right text-sm text-slate-900">
                  {schedule.schedules.map((item, index) => <span key={`${item.hour_utc}-${item.minute_utc}`}>{index > 0 && ' · '}{item.time_cat} CAT ({fmt2(item.hour_utc)}:{fmt2(item.minute_utc)} UTC)</span>)} daily
                </span>
              </div>
              {schedule.jobs.map(j => (
                <div key={j.id} className={rowClass}>
                  <span className={labelClass}>{JOB_LABELS[j.id] ?? formatStage(j.id)}</span>
                  <span className={valueClass}>{j.next_run_utc ? new Date(j.next_run_utc).toLocaleString() : '—'}</span>
                </div>
              ))}
              <details className={disclosureClass}>
                <summary className={summaryClass}>Automation settings</summary>
                <div className="mt-3">
                  {schedule.automation ? (
                    <>
                      <div className={rowClass}><span className={labelClass}>Missed-run recovery</span><span className="text-right text-sm text-slate-900">{schedule.automation.startup_catchup_enabled ? `Automatic · every ${schedule.automation.watchdog_interval_minutes} min · retry limit ${schedule.automation.automatic_retry_limit}` : 'Disabled'}</span></div>
                      <div className={rowClass}><span className={labelClass}>Result settlement</span><span className="text-right text-sm text-slate-900">Automatic · every {schedule.automation.settlement_interval_minutes} min · {schedule.automation.settlement_startup_lookback_days}-day startup catch-up</span></div>
                      <div className={rowClass}><span className={labelClass}>Scheduler ownership</span><span className="text-right text-sm text-slate-900">{schedule.automation.scheduler_leader_lock_enabled ? `PostgreSQL leader lock enabled (${schedule.automation.scheduler_leader_lock_name})` : 'Disabled'}</span></div>
                    </>
                  ) : <p className={hintClass}>Automation settings are unavailable.</p>}
                </div>
              </details>
            </div>
          )}
          <fieldset className="mt-4 space-y-3 rounded-lg border border-slate-200 p-4">
            <legend className="px-1 text-sm font-semibold text-slate-800">Manual recovery actions</legend>
            <label className="flex flex-col gap-1 text-sm font-semibold uppercase tracking-wide text-slate-600">Pipeline target date
              <input type="date" className={inputClass} value={pipelineDate} onChange={e => setPipelineDate(e.target.value)} />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={primaryBtnClass} onClick={() => void triggerPipeline()} disabled={triggering}>
                {triggering ? 'Queuing…' : pipelineDate === localDateString() ? '▶ Run Today’s Pipeline' : '▶ Run Pipeline'}
              </button>
            </div>
            <p className={hintClass}>Runs: ingest fixtures → fetch odds → enrich form data → prediction models.</p>
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-sm font-semibold uppercase tracking-wide text-slate-600">From
                <input type="date" className={inputClass} value={historyStart} onChange={e => setHistoryStart(e.target.value)} aria-label="Historical sync start date" />
              </label>
              <label className="flex flex-col gap-1 text-sm font-semibold uppercase tracking-wide text-slate-600">To
                <input type="date" className={inputClass} value={historyEnd} onChange={e => setHistoryEnd(e.target.value)} aria-label="Historical sync end date" />
              </label>
              <button type="button" className={secondaryBtnClass} onClick={() => void syncHistory()} disabled={syncingHistory} title="Ingest finished fixtures and settle tickets in this range">
                {syncingHistory ? 'Queuing…' : '↻ Sync Historical Results'}
              </button>
            </div>
            <p className={hintClass}>Historical sync refreshes finished scores and settles matching paper tickets in the selected range.</p>
          </fieldset>
          <details className={disclosureClass}>
            <summary className={summaryClass}>Recent runs ({pipelineRuns.length})</summary>
            <div className="mt-3 divide-y divide-slate-100">
              {pipelineRuns.slice(0, 3).map(run => {
                const published = run.stages.find(stage => stage.name === 'publication')?.output_count ?? 0
                return <div className={rowClass} key={run.id}><span className={labelClass}>#{run.id} · <span className="font-mono tabular-nums">{run.target_date}</span> · {formatStage(run.run_type)}</span><span className="text-right text-sm text-slate-900"><span className={statusBadgeClass(run.status)}>{formatStage(run.status)}</span>{run.trigger_source ? ` · ${formatStage(run.trigger_source)}` : ''}{run.scheduled_window ? ` · ${formatStage(run.scheduled_window)} window` : ''}{published ? ` · ${published} published` : ''}{run.current_stage ? ` · ${formatStage(run.current_stage)}` : ''}{run.error_details ? ` · ${run.error_details}` : ''}</span></div>
              })}
              {pipelineRuns.length === 0 && <p className={hintClass}>No runs recorded for the latest status check.</p>}
            </div>
          </details>
        </section>

        <section className={cardClass} aria-labelledby="admin-alerts-title">
          <h2 id="admin-alerts-title" className={cardTitleClass}>Automation alerts</h2>
          <p className={`${hintClass} mt-2`}>Persistent provider failures, exhausted retries, and decision-safety signals.</p>
          {alerts.length === 0 ? (
            <div className="mt-4 text-base text-slate-600">No active automation alerts.</div>
          ) : (
            <div className="mt-4 space-y-3">
              {alertGroups.map(group => {
                const first = group.rows[0]
                const guardrail = group.rows.every(alert => /past-date scoring is not supported/i.test(alert.detail))
                return <details className={disclosureClass} key={`${first.task_name}-${first.title}-${first.detail}`}>
                  <summary className="min-h-11 cursor-pointer list-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                      <span className="grid gap-1"><strong className="text-base text-slate-900">{first.title}</strong><span className="text-sm text-slate-600">{first.task_name} · {guardrail ? 'Guardrail rejection' : first.severity}</span></span>
                      <span className="grid gap-1 text-sm text-slate-600 sm:text-right"><span><b className="font-mono tabular-nums text-slate-900">{group.rows.length}</b> record{group.rows.length === 1 ? '' : 's'} · <b className="font-mono tabular-nums text-slate-900">{group.occurrences}</b> occurrence{group.occurrences === 1 ? '' : 's'}</span><span>Last seen {new Date(group.lastSeen).toLocaleString()}</span></span>
                    </div>
                  </summary>
                  <div className="mt-3 space-y-2">{group.rows.map(alert => <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-start sm:justify-between" key={alert.id}>
                    <span className="grid gap-1 text-base text-slate-700"><span>{alert.target_date ? `Target ${alert.target_date} · ` : ''}{alert.detail}</span><span className="text-sm text-slate-600">First seen {new Date(alert.first_seen_at).toLocaleString()} · Last seen {new Date(alert.last_seen_at).toLocaleString()} · {alert.occurrence_count} occurrence{alert.occurrence_count === 1 ? '' : 's'}</span></span>
                    <button type="button" className={`${secondaryBtnClass} shrink-0`} onClick={() => void resolveAlert(alert.id)}>Resolve record</button>
                  </div>)}</div>
                </details>
              })}
            </div>
          )}
        </section>

        <section className={`${cardClass} xl:col-span-2`} aria-labelledby="admin-users-title">
          <h2 id="admin-users-title" className={cardTitleClass}>User access</h2>
          <p className={`${hintClass} mt-2`}>Create, update, suspend, or remove accounts. Passwords are write-only and never displayed.</p>
          <form className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" onSubmit={saveUser}>
            <div className="contents" role="group" aria-label="Account identity">
              <input className={inputClass} placeholder="Username" aria-label="Username" value={userForm.username} onChange={e => updateUserField('username', e.target.value)} required minLength={2} />
              <input className={inputClass} type="email" placeholder="Email" aria-label="Email" value={userForm.email} onChange={e => updateUserField('email', e.target.value)} required />
              <input className={inputClass} type="password" placeholder={editingUserId ? 'New password (optional)' : 'Password (6+ characters)'} aria-label={editingUserId ? 'New password (optional)' : 'Password'} value={userForm.password} onChange={e => updateUserField('password', e.target.value)} minLength={6} required={!editingUserId} />
            </div>
            <div className="contents" role="group" aria-label="Role and status">
              <select className={inputClass} aria-label="Role" value={userForm.role} onChange={e => updateUserField('role', e.target.value as UserForm['role'])}><option value="user">User</option><option value="admin">Admin</option></select>
              <select className={inputClass} aria-label="Plan" value={userForm.plan} onChange={e => updateUserField('plan', e.target.value as UserForm['plan'])}><option value="free">Free</option><option value="pro">Pro</option></select>
              <select className={inputClass} aria-label="Account status" value={userForm.account_status} onChange={e => updateUserField('account_status', e.target.value as UserForm['account_status'])}><option value="active">Active</option><option value="pending">Pending</option><option value="suspended">Suspended</option></select>
            </div>
            <div className="flex flex-wrap gap-2 sm:col-span-2">
              <button className={primaryBtnClass} type="submit" disabled={userBusy}>{userBusy ? 'Saving…' : editingUserId ? 'Save changes' : 'Create user'}</button>
              {editingUserId && <button className={secondaryBtnClass} type="button" onClick={() => { setEditingUserId(null); setUserForm(emptyUserForm) }}>Cancel edit</button>}
            </div>
          </form>
          <div aria-live="polite">
            {userError && <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-base text-red-700" role="alert">{userError}</div>}
          </div>
          <div className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {users.map(user => <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between" key={user.id}><div className="min-w-0"><strong className="block text-base text-slate-900">{user.username}</strong><span className="block text-sm text-slate-600">{user.email}</span></div><span className="text-sm text-slate-700">{user.role} · {user.plan} · {user.account_status}</span><div className="flex gap-2"><button type="button" className={secondaryBtnClass} onClick={() => editUser(user)}>Edit</button><button type="button" className={dangerBtnClass} onClick={() => void removeUser(user)}>Delete</button></div></div>)}
            {users.length === 0 && <div className="px-4 py-6 text-base text-slate-600">No user accounts found.</div>}
          </div>
        </section>
      </main>
    </div>
  )
}
