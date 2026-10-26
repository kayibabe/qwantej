import type { KeyboardEvent } from 'react'

export function handleArrowTab<T extends string>(
  event: KeyboardEvent<HTMLButtonElement>,
  tabs: readonly T[],
  selected: T,
  setSelected: (tab: T) => void,
  idPrefix: string,
) {
  const currentIndex = tabs.indexOf(selected)
  let nextIndex = currentIndex
  if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length
  else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = tabs.length - 1
  else return

  event.preventDefault()
  const next = tabs[nextIndex]
  setSelected(next)
  requestAnimationFrame(() => document.getElementById(`${idPrefix}${next}`)?.focus())
}
