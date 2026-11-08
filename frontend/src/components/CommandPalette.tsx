import { Fragment, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'

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
  const listId = useId()

  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return actions.filter(action => matches(action, normalized))
  }, [actions, query])

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
      onClose()
    }
    window.addEventListener('keydown', onEscape)
    return () => {
      window.removeEventListener('keydown', onEscape)
      document.body.style.overflow = previousOverflow
      restoreFocus.current?.focus()
    }
  }, [open, onClose])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  useEffect(() => {
    if (!open || results.length === 0) return
    document.getElementById(`${listId}-${Math.min(activeIndex, results.length - 1)}`)?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex, listId, open, results.length])

  if (!open) return null

  const run = (action: CommandAction | undefined) => {
    if (!action) return
    onClose()
    action.onRun()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
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
      run(results[activeIndex])
      return
    }
    if (event.key === 'Tab') {
      event.preventDefault()
      if (document.activeElement === inputRef.current) escapeRef.current?.focus()
      else inputRef.current?.focus()
    }
  }

  const activeId = results.length > 0 ? `${listId}-${Math.min(activeIndex, results.length - 1)}` : undefined

  return (
    <div className="command-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <div className="command-dialog" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKeyDown}>
        <div className="command-input-row">
          <svg className="command-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
            <circle cx="10.8" cy="10.8" r="6.6" /><path d="m16 16 4.5 4.5" />
          </svg>
          <input
            ref={inputRef}
            className="command-input"
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={activeId}
            aria-autocomplete="list"
            aria-label="Search commands"
            placeholder="Search pages, dates, and actions"
            value={query}
            onChange={event => setQuery(event.target.value)}
          />
          <button ref={escapeRef} type="button" className="command-escape" onClick={onClose}>Esc</button>
        </div>
        <div className="command-results" id={listId} role="listbox" aria-label="Commands">
          {results.length === 0 ? (
            <p className="command-empty">No command matches “{query.trim()}”.</p>
          ) : results.map((action, index) => {
            const previous = results[index - 1]
            return (
              <Fragment key={action.id}>
                {(!previous || previous.group !== action.group) && <div className="command-group" role="presentation">{action.group}</div>}
                <button
                  id={`${listId}-${index}`}
                  type="button"
                  role="option"
                  tabIndex={-1}
                  aria-selected={index === activeIndex}
                  className={`command-item${index === activeIndex ? ' active' : ''}`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => run(action)}
                >
                  <span className="command-item-label">{action.label}</span>
                  {action.hint && <span className="command-item-hint">{action.hint}</span>}
                </button>
              </Fragment>
            )
          })}
        </div>
        <footer className="command-footer" aria-hidden="true">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span><kbd>Enter</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
        </footer>
      </div>
    </div>
  )
}
