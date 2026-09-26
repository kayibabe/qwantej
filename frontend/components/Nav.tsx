"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import NavIcon from "@/components/NavIcon"

const links = [
  { href: "/", label: "Daily tickets", icon: "dashboard" as const, group: "Workspace" },
  { href: "/accumulators", label: "Ticket archive", icon: "accumulators" as const, group: "Workspace" },
  { href: "/predictions", label: "Forecasts", icon: "predictions" as const, group: "Workspace" },
  { href: "/performance", label: "Analytics", icon: "performance" as const, group: "Research" },
  { href: "/models", label: "Models", icon: "models" as const, group: "Research" },
  { href: "/settlements", label: "Settlements", icon: "settlements" as const, group: "Operations" },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav
      className="flex flex-col gap-1 px-3 py-4"
      aria-label="Primary navigation"
    >
      {["Workspace", "Research", "Operations"].map((group) => <div key={group} className="nav-group">
        <span className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{group}</span>
      {links.filter((link) => link.group === group).map(({ href, label, icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex items-center gap-3 rounded-md border border-transparent px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
              active
                ? "border-[color-mix(in_srgb,var(--accent)_34%,var(--border))] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]",
            ].join(" ")}
            aria-current={active ? "page" : undefined}
          >
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center ${active ? "opacity-100" : "opacity-75"}`}>
              <NavIcon name={icon} />
            </span>
            {label}
          </Link>
        )
      })}</div>)}
    </nav>
  )
}
