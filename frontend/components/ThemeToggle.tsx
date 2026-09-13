"use client"

import { useEffect, useState } from "react"

type Theme = "system" | "light" | "dark"

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system")

  useEffect(() => {
    const stored = window.localStorage.getItem("qwantej-theme") as Theme | null
    if (stored === "light" || stored === "dark") {
      document.documentElement.dataset.theme = stored
      setTheme(stored)
    }
  }, [])

  function cycleTheme() {
    const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system"
    setTheme(next)
    if (next === "system") {
      window.localStorage.removeItem("qwantej-theme")
      delete document.documentElement.dataset.theme
    } else {
      window.localStorage.setItem("qwantej-theme", next)
      document.documentElement.dataset.theme = next
    }
  }

  return (
    <button
      type="button"
      onClick={cycleTheme}
      title={`Theme: ${theme}`}
      aria-label={`Theme: ${theme}. Click to change.`}
      className="flex h-9 min-w-12 items-center justify-center rounded-md border border-[var(--border)] bg-[var(--bg-raised)] px-2 text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)] transition-colors hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
    >
      {theme === "system" ? "Auto" : theme}
    </button>
  )
}
