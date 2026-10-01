"use client"

import { usePathname, useRouter } from "next/navigation"

const pageContext: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Today", subtitle: "What is actionable now" },
  "/accumulators": { title: "Tickets", subtitle: "Published selections and source evidence" },
  "/performance": { title: "Results", subtitle: "Profit, ROI and settlement evidence" },
  "/predictions": { title: "Forecasts", subtitle: "Archived probabilities and executable prices" },
  "/daily-candidates": { title: "Daily candidates", subtitle: "The candidate pool before selection" },
  "/models": { title: "Models", subtitle: "Versions and calibration context" },
}

export default function WorkspaceHeader() {
  const pathname = usePathname()
  const router = useRouter()
  const section = Object.keys(pageContext).find((key) => key !== "/" && pathname.startsWith(`${key}/`))
  const context = pageContext[pathname] ?? (section ? pageContext[section] : pageContext["/"])

  return (
    <header className="workspace-header">
      <div className="workspace-context" aria-live="polite"><strong>{context.title}</strong><span>{context.subtitle}</span></div>
      <button className="workspace-refresh" type="button" onClick={() => router.refresh()}>↻ <span>Refresh data</span></button>
    </header>
  )
}
