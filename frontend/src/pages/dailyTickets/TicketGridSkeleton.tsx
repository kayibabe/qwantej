export function TicketGridSkeleton() {
  return (
    <div
      className="space-y-4"
      aria-label="Loading daily recommendations and research panels"
      aria-busy="true"
      role="status"
      aria-live="polite"
    >
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden animate-pulse motion-reduce:animate-none">
        <div className="px-4 py-4 space-y-3 sm:px-5">
          <span className="block h-5 w-56 max-w-full rounded bg-slate-200" />
          <span className="block h-4 w-full max-w-2xl rounded bg-slate-100" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[0, 1, 2, 3].map((index) => (
              <span className="block h-12 rounded-lg bg-slate-100" key={`brief-${index}`} />
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2, 3].map((index) => (
          <div
            className="rounded-xl border border-slate-200 bg-white overflow-hidden animate-pulse motion-reduce:animate-none"
            key={`panel-${index}`}
          >
            <div className="border-b border-slate-200 px-4 py-3 space-y-3">
              <span className="block h-5 w-40 max-w-full rounded bg-slate-200" />
              <div className="flex flex-wrap gap-2">
                <span className="block h-6 w-20 rounded bg-slate-100" />
                <span className="block h-6 w-24 rounded bg-slate-100" />
                <span className="block h-6 w-16 rounded bg-slate-100" />
              </div>
            </div>
            <div className="px-4 py-4 space-y-2.5">
              {[0, 1, 2, 3].map((row) => (
                <span className="block h-11 w-full rounded-lg bg-slate-100" key={`row-${row}`} />
              ))}
            </div>
            <div className="border-t border-slate-200 px-4 py-3">
              <span className="block h-4 w-2/3 rounded bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Loading daily recommendations and research panels…</span>
    </div>
  );
}
