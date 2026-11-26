import { Fragment, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Search } from 'lucide-react'

export interface CommandAction {
  id: string
  label: string
  group: string
  hint?: string
  keywords?: string
  onRun: () => void
}

interface Props {
  open: boolean
  actions: CommandAction[]
  onClose: () => void
}

function isThemeCommand(action: CommandAction) {
  const id = action.id.toLowerCase()
  const group = action.group.toLowerCase()
  const label = action.label.toLowerCase()
  return group === 'appearance' || id.startsWith('theme-') || label.includes('theme')
}

function matches(action: CommandAction, query: string) {
  if (!query) return true
  return `${action.label} ${action.group} ${action.hint ?? ''} ${action.keywords ?? ''}`.toLowerCase().includes(query)
}

export default function CommandPalette({ open, actions, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const escapeRef = useRef<HTMLButtonElement>(null)
  const restoreFocus = useRef<HTMLElement | null>(null)
  const onCloseRef = useRef(onClose)
  const listId = useId()
  const helpId = `${listId}-help`

  // Keep the latest callback without re-running the open/close effect when the
  // parent passes a fresh inline closure on every render.
  onCloseRef.current = onClose

  const visibleActions = useMemo(() => actions.filter(action => !isThemeCommand(action)), [actions])

  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return visibleActions.filter(action => matches(action, normalized))
  }, [visibleActions, query])

  useEffect(() => {
    if (!open) return
    restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setQuery('')
    setActiveIndex(0)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    inputRef.current?.focus()
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onCloseRef.current()
    }
    window.addEventListener('keydown', onEscape)
    return () => {
      window.removeEventListener('keydown', onEscape)
      document.body.style.overflow = previousOverflow
      const target = restoreFocus.current
      restoreFocus.current = null
      target?.focus()
    }
  }, [open])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  const safeIndex = results.length === 0 ? 0 : Math.min(activeIndex, results.length - 1)

  useEffect(() => {
    if (!open || results.length === 0) return
    document.getElementById(`${listId}-${safeIndex}`)?.scrollIntoView({ block: 'nearest' })
  }, [listId, open, results.length, safeIndex])

  if (!open) return null

  // Restore focus before running the action so that a route change can focus
  // its own main region afterwards without the palette stealing it back.
  const returnFocus = () => {
    const target = restoreFocus.current
    restoreFocus.current = null
    target?.focus()
  }

  const run = (action: CommandAction | undefined) => {
    if (!action) return
    returnFocus()
    onCloseRef.current()
    action.onRun()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // Let the close button handle its own activation keys.
    if (event.key === 'Enter' && document.activeElement === escapeRef.current) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (results.length === 0) return
      setActiveIndex(current => {
        const next = event.key === 'ArrowDown' ? current + 1 : current - 1
        return (next + results.length) % results.length
      })
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      setActiveIndex(event.key === 'Home' ? 0 : Math.max(0, results.length - 1))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      run(results[safeIndex])
      return
    }
    if (event.key === 'Tab') {
      event.preventDefault()
      if (document.activeElement === inputRef.current) escapeRef.current?.focus()
      else inputRef.current?.focus()
    }
  }

  const activeId = results.length > 0 ? `${listId}-${safeIndex}` : undefined

  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center bg-slate-900/50 px-4 py-[10vh]" onMouseDown={event => { if (event.target === event.currentTarget) onCloseRef.current() }}>
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKeyDown}>
        <p id={helpId} className="sr-only">Use the up and down arrow keys to review commands, Enter to open, and Escape to close.</p>
        <p className="sr-only" role="status">{results.length === 0 ? 'No commands found.' : `${results.length} command${results.length === 1 ? '' : 's'} available.`}</p>
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3">
          <Search className="h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
          <input
            ref={inputRef}
            className="w-full bg-transparent text-base text-slate-900 placeholder:text-slate-600 focus:outline-none"
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={activeId}
            aria-autocomplete="list"
            aria-describedby={helpId}
            aria-label="Search commands"
            placeholder="Search pages, dates, and actions"
            value={query}
            onChange={event => setQuery(event.target.value)}
          />
          <button
            ref={escapeRef}
            type="button"
            className="min-h-11 min-w-11 rounded-md border border-slate-200 bg-slate-50 px-2 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-100 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
            aria-label="Esc: close command palette"
            onClick={() => onCloseRef.current()}
          >
            Esc
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2" id={listId} role="listbox" aria-label="Commands">
          {results.length === 0 ? (
            <p className="px-3 py-8 text-center text-base leading-relaxed text-slate-600">No command matches “{query.trim()}”.</p>
          ) : results.map((action, index) => {
            const previous = results[index - 1]
            return (
              <Fragment key={action.id}>
                {(!previous || previous.group !== action.group) && <div className="px-3 pb-1 pt-3 text-sm font-semibold leading-5 text-slate-600" role="presentation">{action.group}</div>}
                <button
                  id={`${listId}-${index}`}
                  type="button"
                  role="option"
                  tabIndex={-1}
                  aria-selected={index === safeIndex}
                  className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm leading-5 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 ${index === safeIndex ? 'bg-emerald-50 text-emerald-800' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'}`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => run(action)}
                >
                  <span className="font-medium">{action.label}</span>
                  {action.hint && <span className="max-w-[50%] shrink-0 truncate text-right text-sm text-slate-600">{action.hint}</span>}
                </button>
              </Fragment>
            )
          })}
        </div>
        <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-200 bg-slate-50 px-4 py-2.5 text-sm leading-5 text-slate-600" aria-hidden="true">
          <span className="inline-flex items-center gap-1"><kbd className="rounded border border-slate-200 bg-white px-1 font-mono text-sm">↑</kbd><kbd className="rounded border border-slate-200 bg-white px-1 font-mono text-sm">↓</kbd> move</span>
          <span className="inline-flex items-center gap-1"><kbd className="rounded border border-slate-200 bg-white px-1 font-mono text-sm">Enter</kbd> open</span>
          <span className="inline-flex items-center gap-1"><kbd className="rounded border border-slate-200 bg-white px-1 font-mono text-sm">Esc</kbd> close</span>
        </footer>
      </div>
    </div>
  )
}
