/**
 * Currency symbol for the UI.
 * Set NEXT_PUBLIC_CURRENCY_SYMBOL in the environment to override.
 */
export const CURRENCY_SYMBOL =
  process.env.NEXT_PUBLIC_CURRENCY_SYMBOL ?? "£"

/** Qwantej operates in CAT (UTC+2). All stored timestamps are UTC ISO strings. */
const TZ = "Africa/Blantyre"

/** Format an ISO timestamp in CAT, e.g. "07 Sep 2026". */
export function fmtDate(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso))
}

/** Format an ISO timestamp in CAT, e.g. "07 Sep 2026, 08:00". */
export function fmtDatetime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso))
}

/** Today's date in CAT as an ISO YYYY-MM-DD string. */
export function todayIsoDate(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date())
}

/** Add `days` (may be negative) to an ISO YYYY-MM-DD date string. */
export function addDaysIso(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + days)
  return dt.toISOString().slice(0, 10)
}

/** Format an ISO YYYY-MM-DD date string for display, e.g. "07 Sep 2026". */
export function fmtIsoDate(iso: string): string {
  return fmtDate(`${iso}T00:00:00+02:00`)
}

/** True if an ISO YYYY-MM-DD date string is syntactically valid. */
export function isValidIsoDate(iso: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false
  const [y, m, d] = iso.split("-").map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d
}
