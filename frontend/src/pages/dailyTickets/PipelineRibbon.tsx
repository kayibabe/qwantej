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
    <div className="flow-ribbon" data-steps={steps.length} role="group" aria-label="Daily decision pipeline">
      {steps.map((step, index) => (
        <button
          key={step.key}
          type="button"
          className={`flow-step${active === step.key ? ' active' : ''}`}
          onClick={() => onSelect(step.key)}
          disabled={step.disabled}
          aria-pressed={active === step.key}
          title={`${step.label}: ${step.note}`}
        >
          <span className="flow-step-label">
            <span className="flow-step-index" aria-hidden="true">{index + 1}</span>
            {step.label}
          </span>
          <strong className="flow-step-value">{step.value}</strong>
          <span className="flow-step-note">{step.note}</span>
        </button>
      ))}
    </div>
  )
}
