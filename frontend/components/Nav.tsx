"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import NavIcon from "@/components/NavIcon"

const links = [
  { href: "/", label: "Dashboard", icon: "dashboard" as const },
  { href: "/accumulators", label: "Accumulators", icon: "accumulators" as const },
  { href: "/predictions", label: "Predictions", icon: "predictions" as const },
  { href: "/settlements", label: "Settlements", icon: "settlements" as const },
  { href: "/performance", label: "Performance", icon: "performance" as const },
  { href: "/models", label: "Models", icon: "models" as const },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav
      className="flex flex-col gap-1 px-3 py-4"
      aria-label="Primary navigation"
    >
      <span className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
        Workspace
      </span>
      {links.map(({ href, label, icon }) => {
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
      })}
    </nav>
  )
}
