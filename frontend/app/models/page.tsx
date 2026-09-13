import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchModels } from "@/lib/api"
import Pagination from "@/components/Pagination"
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

async function ModelTable({
  status,
  family,
  offset,
}: {
  status: string | undefined
  family: string | undefined
  offset: number
}) {
  const page = await fetchModels({ status, family, limit: LIMIT, offset }).catch(() => null)

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
          <thead>
            <tr className="border-b border-[var(--border)]">
              {["Name", "Family", "Version", "Status", "Commit", "Promoted", "Training window"].map(
                (h) => (
                  <th
                    key={h}
                    className="px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]"
                  >
                    {h}
                  </th>
                ),
              )}
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
  const offset = Number(sp.offset ?? 0)

  const statuses = ["", "champion", "challenger", "development", "retired"]
  const families = ["", "poisson", "dixon_coles", "zinb", "elo", "bayesian_hierarchical", "market", "ensemble"]

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Models</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Model registry — champion, challenger, development and retired versions
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
                href={`?${s ? `status=${s}&` : ""}${family ? `family=${family}&` : ""}offset=0`}
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
                href={`?${status ? `status=${status}&` : ""}${f ? `family=${f}&` : ""}offset=0`}
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
        key={`${status}-${family}-${offset}`}
        fallback={<p className="text-sm text-[var(--text-muted)] animate-pulse">Loading…</p>}
      >
        <ModelTable status={status} family={family} offset={offset} />
      </Suspense>
    </div>
  )
}
