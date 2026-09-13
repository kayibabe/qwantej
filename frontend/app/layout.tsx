import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import Link from "next/link"
import Nav from "@/components/Nav"
import ThemeToggle from "@/components/ThemeToggle"
import "./globals.css"

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: { default: "Qwantej", template: "%s | Qwantej" },
  description: "Calibrated football accumulator intelligence",
  icons: {
    icon: [
      { url: "/qwantej-icon-light.png", media: "(prefers-color-scheme: light)" },
      { url: "/qwantej-icon-dark.png", media: "(prefers-color-scheme: dark)" },
    ],
    apple: "/qwantej-icon-light.png",
  },
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex h-full min-h-screen flex-col md:flex-row">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--bg-surface)] px-4 md:hidden">
          <Link href="/" className="flex items-center gap-2" aria-label="Qwantej home">
            <img src="/qwantej-icon-light.png" alt="" className="brand-icon h-8 w-8" />
            <span className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">Qwantej</span>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <details className="relative">
              <summary className="cursor-pointer list-none rounded-md border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">Menu</summary>
              <div className="absolute right-0 z-10 mt-2 w-48 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-2 shadow-xl">
                <Nav />
              </div>
            </details>
          </div>
        </header>
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-surface)] md:flex">
          <div className="flex min-h-28 items-center justify-center border-b border-[var(--border)] px-4 py-3">
            <img src="/qwantej-brand-light.png" alt="Qwantej — Intelligence Beyond Numbers" className="brand-lockup" />
          </div>
          <Nav />
          <div className="mt-auto border-t border-[var(--border)] p-4">
            <ThemeToggle />
          </div>
        </aside>

        {/* Main */}
        <main className="flex flex-1 flex-col overflow-auto">{children}</main>
      </body>
    </html>
  )
}
