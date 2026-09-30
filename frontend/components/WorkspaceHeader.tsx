"use client"

import { usePathname, useRouter } from "next/navigation"
import ThemeToggle from "@/components/ThemeToggle"

const pageContext: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Today", subtitle: "Today's tickets and source evidence" },
  "/accumulators": { title: "Tickets", subtitle: "Every published ticket, by year, month and day" },
  "/performance": { title: "Performance", subtitle: "Profit, ROI and settlement evidence" },
  "/predictions": { title: "Forecasts", subtitle: "Priced forecasts and how they settled" },
  "/daily-candidates": { title: "Daily candidates", subtitle: "Daily Pick pool, selection decisions, and match outcomes" },
  "/models": { title: "Models", subtitle: "Which model versions produce the forecasts" },
}

export default function WorkspaceHeader() {
  const pathname = usePathname()
  const router = useRouter()
  // Sub-pages (e.g. /accumulators/<id>) take their section's context.
  const section = Object.keys(pageContext).find((k) => k !== "/" && pathname.startsWith(`${k}/`))
  const context = pageContext[pathname] ?? (section ? pageContext[section] : pageContext["/"])

  return (
    <header className="workspace-header">
      <div className="workspace-research-status">
        <span className="workspace-status-dot" aria-hidden="true" />
        <span>Data context</span>
        <span className="workspace-theme"><ThemeToggle /></span>
      </div>
      <div className="workspace-context" aria-live="polite"><strong>{context.title}</strong><span>{context.subtitle}</span></div>
      <button className="workspace-refresh" type="button" onClick={() => router.refresh()}>↻ <span>Refresh</span></button>
    </header>
  )
}
