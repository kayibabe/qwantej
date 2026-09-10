"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/accumulators", label: "Accumulators" },
  { href: "/predictions", label: "Predictions" },
  { href: "/settlements", label: "Settlements" },
  { href: "/performance", label: "Performance" },
  { href: "/models", label: "Models" },
]

export default function Nav() {
  const pathname = usePathname()

  return (
    <nav
      className="flex flex-col gap-1 px-3 py-4"
      aria-label="Primary navigation"
    >
      {links.map(({ href, label }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            className={[
              "rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-[var(--bg-raised)] text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]",
            ].join(" ")}
          >
            {label}
          </Link>
        )
      })}
    </nav>
  )
}
