import { apiFetch } from './client'

const BASE = '/api/forecasts'

export async function fetchForecasts({ date, market, signal_only, horizon } = {}) {
  const p = new URLSearchParams()
  if (date) p.set('date', date)
  if (market) p.set('market', market)
  if (signal_only === false) p.set('signal_only', 'false')
  if (horizon) p.set('horizon', horizon)
  const res = await apiFetch(`${BASE}?${p}`)
  if (!res.ok) throw new Error(`Forecasts fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchForecastArchive({ date_from, date_to, market, league, outcome, confidence, signal_only, exclude_backfill, page, per_page } = {}) {
  const p = new URLSearchParams()
  if (date_from) p.set('date_from', date_from)
  if (date_to) p.set('date_to', date_to)
  if (market) p.set('market', market)
  if (league) p.set('league', league)
  if (outcome) p.set('outcome', outcome)
  if (confidence) p.set('confidence', confidence)
  if (signal_only === false) p.set('signal_only', 'false')
  if (exclude_backfill) p.set('exclude_backfill', 'true')
  if (page) p.set('page', page)
  if (per_page) p.set('per_page', per_page)
  const res = await apiFetch(`${BASE}/archive?${p}`)
  if (!res.ok) throw new Error(`Archive fetch failed: ${res.status}`)
  return res.json()
}

export async function computeForecasts(date) {
  const res = await apiFetch(`${BASE}/compute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date }),
  })
  if (!res.ok) throw new Error(`Forecast compute failed: ${res.status}`)
  return res.json()
}

export async function fetchHistoricalMatchIntelligence(histFixtureId) {
  const res = await apiFetch(`${BASE}/historical/${histFixtureId}`)
  if (!res.ok) throw new Error(`Historical match intelligence fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchFixtureForecasts(fixtureId) {
  const res = await apiFetch(`${BASE}/${fixtureId}`)
  if (!res.ok) throw new Error(`Fixture forecasts fetch failed: ${res.status}`)
  return res.json()
}
