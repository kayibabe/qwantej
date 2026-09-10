import type {
  AccumulatorPage,
  KPIReportOut,
  ModelRegistryDetailOut,
  ModelRegistryPage,
  PredictionPage,
  SettlementPage,
  SettlementSummary,
} from "./types"

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000"

async function apiFetch<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_URL}${path}`)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), { cache: "no-store" })
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function fetchPredictions(params: {
  fixture_id?: string
  market?: string
  limit?: number
  offset?: number
}): Promise<PredictionPage> {
  return apiFetch("/predictions", params as Record<string, string | number | undefined>)
}

export function fetchSettlements(params: {
  subject_type?: string
  outcome?: string
  limit?: number
  offset?: number
}): Promise<SettlementPage> {
  return apiFetch("/settlements", params as Record<string, string | number | undefined>)
}

export function fetchSettlementSummary(params?: {
  subject_type?: string
}): Promise<SettlementSummary> {
  return apiFetch("/settlements/summary", params as Record<string, string | number | undefined>)
}

export function fetchAccumulators(params: {
  status?: string
  limit?: number
  offset?: number
}): Promise<AccumulatorPage> {
  return apiFetch("/accumulators", params as Record<string, string | number | undefined>)
}

export function fetchPerformanceReport(params?: {
  subject_type?: string
  market?: string
}): Promise<KPIReportOut> {
  return apiFetch("/performance/report", params as Record<string, string | undefined>)
}

export function fetchModels(params?: {
  status?: string
  family?: string
  limit?: number
  offset?: number
}): Promise<ModelRegistryPage> {
  return apiFetch("/models", params as Record<string, string | number | undefined>)
}

export function fetchModel(id: string): Promise<ModelRegistryDetailOut> {
  return apiFetch(`/models/${id}`)
}
