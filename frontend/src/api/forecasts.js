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

export async function fetchForecastArchive({ date_from, date_to, market, outcome, signal_only, page, per_page } = {}) {
  const p = new URLSearchParams()
  if (date_from) p.set('date_from', date_from)
  if (date_to) p.set('date_to', date_to)
  if (market) p.set('market', market)
  if (outcome) p.set('outcome', outcome)
  if (signal_only === false) p.set('signal_only', 'false')
  if (page) p.set('page', page)
  if (per_page) p.set('per_page', per_page)
  const res = await apiFetch(`${BASE}/archive?${p}`)
  if (!res.ok) throw new Error(`Archive fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchFixtureForecasts(fixtureId) {
  const res = await apiFetch(`${BASE}/${fixtureId}`)
  if (!res.ok) throw new Error(`Fixture forecasts fetch failed: ${res.status}`)
  return res.json()
}
