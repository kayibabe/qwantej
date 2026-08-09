import { apiFetch } from './client'

export async function fetchModelPerformance({ date_from, date_to, signal_only } = {}) {
  const p = new URLSearchParams()
  if (date_from) p.set('date_from', date_from)
  if (date_to) p.set('date_to', date_to)
  if (signal_only === false) p.set('signal_only', 'false')
  const res = await apiFetch(`/api/model-performance?${p}`)
  if (!res.ok) throw new Error(`Model performance fetch failed: ${res.status}`)
  return res.json()
}
