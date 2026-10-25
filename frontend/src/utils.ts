import { formatMarket } from './lib/api'

const PRODUCT_TIME_ZONE = 'Africa/Blantyre'

export function dateStringInProductTimeZone(d = new Date()): string {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: PRODUCT_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(d)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

export function formatKickoff(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function formatOdds(n: number): string {
  return n.toFixed(2)
}

export function formatPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

export function formatEV(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(1)}%`
}

export function gradeColor(grade: string): string {
  if (grade === 'A+' || grade === 'A') return 'grade-a'
  if (grade === 'B+' || grade === 'B') return 'grade-b'
  if (grade === 'C') return 'grade-c'
  return 'grade-reject'
}

export function marketLabel(market: string): string {
  return formatMarket(market)
}

export function addDays(dateStr: string, n: number): string {
  const [year, month, day] = dateStr.split('-').map(Number)
  const d = new Date(Date.UTC(year, month - 1, day + n))
  return d.toISOString().slice(0, 10)
}

export function todayISO(): string {
  return dateStringInProductTimeZone()
}
