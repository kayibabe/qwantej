import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchModels } from "@/lib/api"
import Pagination from "@/components/Pagination"
import SortableHeader from "@/components/SortableHeader"
import { fmtDate } from "@/lib/format"
import type { ModelRegistryOut } from "@/lib/types"

export const metadata: Metadata = { title: "Models" }

const LIMIT = 20

const STATUS_STYLE: Record<string, string> = {
  champion: "status-badge status-badge-champion",
  challenger: "status-badge status-badge-challenger",
  development: "status-badge status-badge-development",
  retired: "status-badge status-badge-retired",
}

function ModelRow({ model }: { model: ModelRegistryOut }) {
  const statusStyle =
    STATUS_STYLE[model.status.toLowerCase()] ??
    "status-badge status-badge-development"

  return (
    <tr className="border-b border-[var(--border-subtle)]">
      <td className="px-4 py-3 text-sm font-medium text-[var(--text-primary)]">
        {model.name}
        {model.description && (
          <p className="text-xs text-[var(--text-muted)] font-normal mt-0.5 truncate max-w-xs">
            {model.description}
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-[var(--text-secondary)]">{model.family}</td>
      <td className="px-4 py-3 text-xs font-mono text-[var(--text-secondary)]">{model.version}</td>
      <td className="px-4 py-3">
        <span className={statusStyle}>
          {model.status.toUpperCase()}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-[var(--text-muted)]">
        {model.code_commit ?? "—"}
      </td>
      <td className="px-4 py-3 text-xs text-[var(--text-muted)]">
        {model.promoted_at ? fmtDate(model.promoted_at) : "—"}
      </td>
      <td className="px-4 py-3 text-xs text-[var(--text-muted)]">
        {model.training_window_start && model.training_window_end
          ? `${fmtDate(model.training_window_start)} → ${fmtDate(model.training_window_end)}`
          : "—"}
      </td>
    </tr>
  )
}

const COLUMNS: { label: string; sortKey: string }[] = [
  { label: "Name", sortKey: "name" },
  { label: "Family", sortKey: "family" },
  { label: "Version", sortKey: "version" },
  { label: "Status", sortKey: "status" },
  { label: "Commit", sortKey: "code_commit" },
  { label: "Promoted", sortKey: "promoted_at" },
  { label: "Training window", sortKey: "training_window_start" },
]

async function ModelTable({
  status,
  family,
  sort,
  dir,
  offset,
}: {
  status: string | undefined
  family: string | undefined
  sort: string | undefined
  dir: "asc" | "desc" | undefined
  offset: number
}) {
  const page = await fetchModels({ status, family, sort, dir, limit: LIMIT, offset }).catch(() => null)

  if (!page) {
    return (
      <p className="text-sm text-[var(--loss)]">
        Could not load models — is the API running?
      </p>
    )
  }

  if (page.items.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)]">No models match this filter.</p>
    )
  }

  return (
    <>
      <div className="theme-table-shell">
        <table className="theme-table w-full text-left">
          <caption className="sr-only">Model registry, newest first unless sorted. Column headers sort the table; Training window sorts by its start.</caption>
          <thead className="text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            <tr className="border-b border-[var(--border)]">
              {COLUMNS.map((c) => (
                <SortableHeader key={c.sortKey} label={c.label} sortKey={c.sortKey} className="px-4 py-2 font-semibold" />
              ))}
            </tr>
          </thead>
          <tbody>
            {page.items.map((m) => (
              <ModelRow key={m.id} model={m} />
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={page.total} limit={page.limit} offset={page.offset} />
    </>
  )
}

export default async function ModelsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  const status = typeof sp.status === "string" ? sp.status : undefined
  const family = typeof sp.family === "string" ? sp.family : undefined
  const sort = typeof sp.sort === "string" ? sp.sort : undefined
  const dir = sp.dir === "asc" ? "asc" : sp.dir === "desc" ? "desc" : undefined
  const sortQuery = sort ? `sort=${encodeURIComponent(sort)}&dir=${dir ?? "desc"}&` : ""
  const offset = Math.max(0, Number(sp.offset ?? 0) || 0)

  const statuses = ["", "champion", "challenger", "development", "retired"]
  const families = ["", "poisson", "dixon_coles", "zinb", "elo", "bayesian_hierarchical", "market", "ensemble"]

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Models</h1>
        <p className="mt-1 max-w-3xl text-sm text-[var(--text-secondary)]">
          The audit record of every forecasting model version. Each forecast and ticket is stamped
          with the version that produced it, so results can be traced to exact code and training
          data. The <strong>champion</strong> produces today&apos;s forecasts; a <strong>challenger</strong> runs
          alongside it and is only promoted if it beats the champion on settled results. Compare
          versions on{" "}
          <a href="/performance?subject_type=prediction" className="font-semibold text-[var(--accent)] hover:underline">
            Performance → Individual forecasts
          </a>.
          Research scope is a separate evidence boundary, not automatically a different model;
          a challenger should differ in code, inputs or parameters before it is compared for promotion.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-3 shadow-[var(--surface-shadow)] sm:flex-row sm:flex-wrap sm:items-start">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--text-muted)] self-center">Status:</span>
          {statuses.map((s) => {
            const label = s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)
            const active = (status ?? "") === s
            return (
              <a
                key={s}
                href={`?${s ? `status=${s}&` : ""}${family ? `family=${family}&` : ""}${sortQuery}offset=0`}
                className={[
                  "rounded px-3 py-1 text-xs font-medium border transition-colors",
                  active
                    ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                    : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
                ].join(" ")}
              >
                {label}
              </a>
            )
          })}
        </div>

        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--text-muted)] self-center">Family:</span>
          {families.map((f) => {
            const label = f === "" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)
            const active = (family ?? "") === f
            return (
              <a
                key={f}
                href={`?${status ? `status=${status}&` : ""}${f ? `family=${f}&` : ""}${sortQuery}offset=0`}
                className={[
                  "rounded px-3 py-1 text-xs font-medium border transition-colors",
                  active
                    ? "bg-[var(--accent)] border-[var(--accent)] text-white"
                    : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]",
                ].join(" ")}
              >
                {label}
              </a>
            )
          })}
        </div>
      </div>

      <Suspense
        key={`${status}-${family}-${sort}-${dir}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <ModelTable status={status} family={family} sort={sort} dir={dir} offset={offset} />
      </Suspense>
    </div>
  )
}
