"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

const REFRESH_INTERVAL_MS = 60_000

/** Refresh server-rendered accumulator data while a ticket page stays open. */
export default function LiveMatchRefresh() {
  const router = useRouter()

  useEffect(() => {
    const timer = window.setInterval(() => router.refresh(), REFRESH_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [router])

  return null
}
