"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import NavIcon from "@/components/NavIcon"

const links = [
  { href: "/", label: "Today", detail: "What is actionable now", icon: "dashboard" as const, group: "Decision workspace" },
  { href: "/accumulators", label: "Tickets", detail: "Published selections and evidence", icon: "accumulators" as const, group: "Decision workspace" },
  { href: "/performance", label: "Results", detail: "What happened over time", icon: "performance" as const, group: "Decision workspace" },
  { href: "/predictions", label: "Forecasts", detail: "Archived probabilities and prices", icon: "predictions" as const, group: "Research & audit" },
  { href: "/daily-candidates", label: "Daily candidates", detail: "The candidate pool before selection", icon: "predictions" as const, group: "Research & audit" },
  { href: "/models", label: "Models", detail: "Versions and calibration context", icon: "models" as const, group: "Research & audit" },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav
      className="flex flex-col gap-1 px-3 py-4"
      aria-label="Primary navigation"
    >
      {["Decision workspace", "Research & audit"].map((group) => <div key={group} className="nav-group">
        <span className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{group}</span>
      {links.filter((link) => link.group === group).map(({ href, label, detail, icon }) => {
        const active = pathname === href || (href !== "/" && pathname.startsWith(`${href}/`))
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex items-start gap-3 rounded-lg border border-transparent px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              active
                ? "border-[color-mix(in_srgb,var(--accent)_34%,var(--border))] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]",
            ].join(" ")}
            aria-current={active ? "page" : undefined}
          >
            <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center ${active ? "opacity-100" : "opacity-75"}`}>
              <NavIcon name={icon} />
            </span>
            <span className="min-w-0">
              <span className="block">{label}</span>
              <span className={`mt-0.5 block text-xs font-normal leading-4 ${active ? "text-[var(--accent)]/80" : "text-[var(--text-muted)]"}`}>{detail}</span>
            </span>
          </Link>
        )
      })}</div>)}
    </nav>
  )
}
