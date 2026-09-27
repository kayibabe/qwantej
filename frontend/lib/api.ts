import type {
  AccumulatorOut,
  AccumulatorPage,
  KPIReportOut,
  ModelRegistryDetailOut,
  ModelRegistryPage,
  PerformanceSegmentsOut,
  PredictionPage,
  SettlementPage,
  SettlementSummary,
  TodayStatus,
} from "./types"
import type {
  AccumulatorResultsOut,
  BankrollSummaryOut,
  RealBetResultsOut,
  ResultsGranularity,
} from "./types"

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000"

// Server-only (no NEXT_PUBLIC_ prefix) so it is never bundled to the
// browser. Every caller in this module runs in a Server Component/route
// handler, never client-side.
const API_KEY = process.env.API_KEY ?? ""

async function apiFetch<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_URL}${path}`)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), {
    cache: "no-store",
    headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
  })
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export function fetchPredictions(params: {
  fixture_id?: string
  market?: string
  /** Only forecasts that carry a bookmaker price. */
  priced_only?: boolean
  sort?: string
  dir?: "asc" | "desc"
  limit?: number
  offset?: number
}): Promise<PredictionPage> {
  const { priced_only, ...rest } = params
  return apiFetch("/predictions", {
    ...(rest as Record<string, string | number | undefined>),
    priced_only: priced_only === undefined ? undefined : String(priced_only),
  })
}

/** Markets that have at least one priced forecast. */
export function fetchPricedMarkets(): Promise<string[]> {
  return apiFetch("/predictions/markets")
}

export function fetchAccumulator(id: string): Promise<AccumulatorOut> {
  return apiFetch(`/accumulators/${encodeURIComponent(id)}`)
}

export function fetchSettlements(params: {
  subject_type?: string
  outcome?: string
  sort?: string
  dir?: "asc" | "desc"
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
  /** Publication day (YYYY-MM-DD) in the Africa/Blantyre product time zone. */
  date?: string
  limit?: number
  offset?: number
}): Promise<AccumulatorPage> {
  return apiFetch("/accumulators", params as Record<string, string | number | undefined>)
}

export function fetchTodayStatus(date?: string): Promise<TodayStatus> {
  return apiFetch("/dashboard/today", date ? { date } : undefined)
}

export function fetchPerformanceReport(params?: {
  subject_type?: string
  since?: string
  market?: string
}): Promise<KPIReportOut> {
  return apiFetch("/performance/report", params as Record<string, string | undefined>)
}

export function fetchPerformanceSegments(params: {
  by: "market" | "league" | "model_version" | "product"
  subject_type?: string
  since?: string
}): Promise<PerformanceSegmentsOut> {
  return apiFetch("/performance/segments", params)
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

export function fetchBankroll(): Promise<BankrollSummaryOut> {
  return apiFetch("/bankroll")
}

export function fetchRealBetResults(): Promise<RealBetResultsOut> {
  return apiFetch("/real-bets/summary")
}

export function fetchAccumulatorResults(params: {
  granularity: ResultsGranularity
  product?: string
  /** Publication window [since, until), ISO-8601 with offset. */
  since?: string
  until?: string
  limit?: number
}): Promise<AccumulatorResultsOut> {
  return apiFetch("/performance/accumulator-results", params)
}
