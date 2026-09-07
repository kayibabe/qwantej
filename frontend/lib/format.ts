/** Currency symbol used across the UI. Change here to update everywhere. */
export const CURRENCY_SYMBOL = "£"

/** Format an ISO timestamp as a UTC date string, e.g. "07 Sep 2026". */
export function fmtDate(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso))
}

/** Format an ISO timestamp as a UTC datetime string, e.g. "07 Sep 2026, 08:00". */
export function fmtDatetime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso))
}
