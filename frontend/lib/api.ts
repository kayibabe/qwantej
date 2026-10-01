import type {
  AccumulatorOut,
  AccumulatorPage,
  DailyCandidatePage,
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
  scope?: "all" | "production" | "research" | "awaiting" | "overdue"
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

export function fetchDailyCandidates(date?: string): Promise<DailyCandidatePage> {
  return apiFetch("/daily-candidates", date ? { date } : undefined)
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
  /** Publication window [since, until), ISO-8601 with offset. */
  since?: string
  until?: string
  limit?: number
  offset?: number
}): Promise<AccumulatorPage> {
  return apiFetch("/accumulators", params as Record<string, string | number | undefined>)
}

const ACCUMULATOR_PAGE_MAX = 100

/**
 * Every ticket matching the filters, paging through the API's 100-per-page
 * cap (at most `maxPages` pages). `total` is the API's count, so a caller can
 * tell whether `items` is complete.
 */
export async function fetchAllAccumulators(
  params: { date?: string; since?: string; until?: string },
  maxPages = 10,
): Promise<{ items: AccumulatorOut[]; total: number }> {
  const limit = ACCUMULATOR_PAGE_MAX
  const first = await fetchAccumulators({ ...params, limit, offset: 0 })
  const pages = Math.min(Math.ceil(first.total / limit), maxPages)
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, pages - 1) }, (_, i) =>
      fetchAccumulators({ ...params, limit, offset: (i + 1) * limit }),
    ),
  )
  // A ticket published between page requests can shift a row onto two pages.
  const byId = new Map<string, AccumulatorOut>()
  for (const acc of [first, ...rest].flatMap((p) => p.items)) byId.set(acc.id, acc)
  return { items: [...byId.values()], total: first.total }
}

export function fetchTodayStatus(date?: string): Promise<TodayStatus> {
  return apiFetch("/dashboard/today", date ? { date } : undefined)
}

export function fetchPerformanceReport(params?: {
  subject_type?: string
  since?: string
  until?: string
  market?: string
  selection?: string
  min_probability?: string
  min_odds?: string
  date_from?: string
  date_to?: string
  scope?: "all" | "production" | "research"
}): Promise<KPIReportOut> {
  return apiFetch("/performance/report", params as Record<string, string | undefined>)
}

export function fetchPerformanceSegments(params: {
  by: "market" | "league" | "model_version" | "product"
  subject_type?: string
  since?: string
  until?: string
  market?: string
  selection?: string
  min_probability?: string
  min_odds?: string
  date_from?: string
  date_to?: string
  scope?: "all" | "production" | "research"
}): Promise<PerformanceSegmentsOut> {
  return apiFetch("/performance/segments", params)
}

export function fetchModels(params?: {
  status?: string
  family?: string
  sort?: string
  dir?: "asc" | "desc"
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
