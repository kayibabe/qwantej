interface DateJumpFormProps {
  selectedDate: string
}

/** Native GET form — navigates via the browser, no client JS required. */
export default function DateJumpForm({ selectedDate }: DateJumpFormProps) {
  return (
    <form method="get" className="ml-auto flex items-center gap-2">
      <label htmlFor="date-jump" className="text-xs text-[var(--text-muted)]">
        Jump to date
      </label>
      <input
        id="date-jump"
        type="date"
        name="date"
        defaultValue={selectedDate}
        className="rounded border border-[var(--border)] bg-[var(--bg-surface)] px-2 py-1 text-sm text-[var(--text-primary)]"
      />
      <button
        type="submit"
        className="rounded px-3 py-1 text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-raised)]"
      >
        Go
      </button>
    </form>
  )
}
