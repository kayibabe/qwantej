"use client"

import { useEffect } from "react"

/**
 * The archive streams in after the page shell, so the browser has already
 * tried (and failed) to jump to a "#day-…" link target. Retry once the
 * groups exist.
 */
export default function ScrollToHash() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1))
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" })
  }, [])
  return null
}
