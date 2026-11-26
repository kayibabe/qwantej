import type { DailyTab } from './types'

export interface PipelineStep {
  key: DailyTab
  label: string
  value: string | number
  note: string
  disabled?: boolean
}

interface Props {
  steps: PipelineStep[]
  active: DailyTab
  onSelect: (tab: DailyTab) => void
}

export default function PipelineRibbon({ steps, active, onSelect }: Props) {
  return (
    <div
      className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
      data-steps={steps.length}
      role="group"
      aria-label="Daily decision pipeline"
    >
      {steps.map((step) => {
        const isActive = active === step.key
        return (
          <button
            key={step.key}
            type="button"
            className={`flex min-h-20 min-w-0 flex-col items-start gap-1.5 rounded-xl border px-4 py-3 text-left transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 disabled:cursor-not-allowed disabled:opacity-60 ${
              isActive
                ? 'border-emerald-300 bg-emerald-50 text-emerald-900 shadow-xs'
                : 'border-slate-200 bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-50'
            }`}
            onClick={() => onSelect(step.key)}
            disabled={step.disabled}
            aria-pressed={isActive}
            aria-label={`${step.label}: ${step.value}. ${step.note}${step.disabled ? ' (unavailable)' : ''}`}
            title={`${step.label}: ${step.note}`}
          >
            <span className={`text-sm font-semibold ${isActive ? 'text-emerald-800' : 'text-slate-600'}`}>
              {step.label}
            </span>
            <strong className={`font-mono text-xl font-bold tabular-nums ${isActive ? 'text-emerald-900' : 'text-slate-900'}`}>
              {step.value}
            </strong>
            <span className={`text-sm leading-snug ${isActive ? 'text-emerald-800' : 'text-slate-600'}`}>
              {step.note}
            </span>
          </button>
        )
      })}
    </div>
  )
}
