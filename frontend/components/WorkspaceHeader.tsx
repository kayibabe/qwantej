"use client"

import { usePathname, useRouter } from "next/navigation"
import ThemeToggle from "@/components/ThemeToggle"

const pageContext: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Today", subtitle: "Published paper tickets and source evidence" },
  "/accumulators": { title: "Tickets", subtitle: "Immutable published accumulator history" },
  "/performance": { title: "Performance", subtitle: "Results, calibration and settlement evidence" },
  "/predictions": { title: "Forecasts", subtitle: "Archived probability forecasts" },
  "/models": { title: "Models", subtitle: "Versioned research models" },
}

export default function WorkspaceHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const context = pageContext[pathname] ?? pageContext["/"]

  return (
    <header className="workspace-header">
      <div className="workspace-research-status">
        <span className="workspace-status-dot" aria-hidden="true" />
        <span>Paper research</span>
        <span className="workspace-theme"><ThemeToggle /></span>
      </div>
      <div className="workspace-context" aria-live="polite"><strong>{context.title}</strong><span>{context.subtitle}</span></div>
      <button className="workspace-refresh" type="button" onClick={() => router.refresh()}>↻ <span>Refresh</span></button>
    </header>
  )
}
