import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import Nav from "@/components/Nav"
import "./globals.css"

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: { default: "Qwantej", template: "%s | Qwantej" },
  description: "Calibrated football accumulator intelligence",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex h-full min-h-screen flex-col md:flex-row">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--bg-surface)] px-4 md:hidden">
          <span className="text-sm font-semibold tracking-widest text-[var(--text-primary)] uppercase">Qwantej</span>
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-md border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]">Menu</summary>
            <div className="absolute right-0 z-10 mt-2 w-48 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-2 shadow-xl">
              <Nav />
            </div>
          </details>
        </header>
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg-surface)] md:flex">
          <div className="flex h-14 items-center px-4 border-b border-[var(--border)]">
            <span className="text-sm font-semibold tracking-widest text-[var(--text-primary)] uppercase">
              Qwantej
            </span>
          </div>
          <Nav />
        </aside>

        {/* Main */}
        <main className="flex flex-1 flex-col overflow-auto">{children}</main>
      </body>
    </html>
  )
}
