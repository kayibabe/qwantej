/**
 * Shared column-sort rules so every sortable table behaves the same way,
 * whether it sorts in the browser (SortableTable) or on the API
 * (SortableHeader + ?sort=&dir=):
 *
 * - a click cycles ascending → descending → back to the table's own order;
 * - missing values (null / undefined / NaN) always sort last, matching the
 *   API's NULLS LAST, so "highest first" never starts with a blank.
 */

export type SortDir = "asc" | "desc"
export type SortValue = string | number | null | undefined
export interface SortState {
  key: string
  dir: SortDir
}

function isMissing(v: SortValue): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v))
}

/** Compare two cell values in `dir`; missing values sort last either way. */
export function compareSortValues(a: SortValue, b: SortValue, dir: SortDir): number {
  const aMissing = isMissing(a)
  const bMissing = isMissing(b)
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1
  const cmp =
    typeof a === "number" && typeof b === "number"
      ? a - b
      : String(a).localeCompare(String(b), "en", { numeric: true, sensitivity: "base" })
  return dir === "asc" ? cmp : -cmp
}

/** Stable sort of `rows` by the value `valueOf` reads from each. */
export function sortRows<T>(rows: readonly T[], valueOf: (row: T) => SortValue, dir: SortDir): T[] {
  return [...rows].sort((a, b) => compareSortValues(valueOf(a), valueOf(b), dir))
}

/** The sort after clicking `key`: asc, then desc, then none (original order). */
export function nextSortState(current: SortState | null, key: string): SortState | null {
  if (!current || current.key !== key) return { key, dir: "asc" }
  return current.dir === "asc" ? { key, dir: "desc" } : null
}
