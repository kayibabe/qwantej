import { apiFetch } from './client'

export async function fetchDataSources() {
  const res = await apiFetch('/api/data-sources')
  if (!res.ok) throw new Error(`Data sources fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchDataSourceCoverage() {
  const res = await apiFetch('/api/data-sources/coverage')
  if (!res.ok) throw new Error(`Coverage fetch failed: ${res.status}`)
  return res.json()
}
