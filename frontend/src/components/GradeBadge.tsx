interface Props { grade: string }

const TONE_MAP: Record<string, string> = {
  'A+':     'border-emerald-200 bg-emerald-50 text-emerald-700',
  'A':      'border-emerald-200 bg-emerald-50 text-emerald-700',
  'B+':     'border-amber-200 bg-amber-50 text-amber-700',
  'B':      'border-amber-200 bg-amber-50 text-amber-700',
  'C':      'border-sky-200 bg-sky-50 text-sky-700',
  'REJECT': 'border-red-200 bg-red-50 text-red-700',
}

export default function GradeBadge({ grade }: Props) {
  const tone = TONE_MAP[grade] ?? 'border-slate-200 bg-slate-50 text-slate-600'
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-semibold ${tone}`}>{grade}</span>
}
