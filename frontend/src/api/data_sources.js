import { apiFetch } from './client'

export async function fetchDataSources() {
  const res = await apiFetch('/api/data-sources')
  if (!res.ok) throw new Error(`Data sources fetch failed: ${res.status}`)
  return res.json()
}
