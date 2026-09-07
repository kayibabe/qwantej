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
