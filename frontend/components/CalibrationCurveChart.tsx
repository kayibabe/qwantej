"use client"

import { useState } from "react"
import type { CalibrationBinOut } from "@/lib/types"

interface CalibrationCurveChartProps {
  bins: CalibrationBinOut[]
}

const SIZE = 320
const PAD = 36

function x(p: number) {
  return PAD + p * (SIZE - 2 * PAD)
}

function y(p: number) {
  return SIZE - PAD - p * (SIZE - 2 * PAD)
}

export default function CalibrationCurveChart({ bins }: CalibrationCurveChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const sorted = [...bins].sort((a, b) => a.predicted_probability - b.predicted_probability)
  const maxCount = Math.max(...sorted.map((b) => b.count))
  const totalCount = sorted.reduce((sum, b) => sum + b.count, 0)

  function radius(count: number) {
    // r in [4, 9] (>=8px marker floor), scaled by sqrt(count) so bin weight is visible.
    const t = maxCount > 0 ? Math.sqrt(count / maxCount) : 0
    return 4 + t * 5
  }

  const linePoints = sorted
    .map((b) => `${x(b.predicted_probability)},${y(b.observed_frequency)}`)
    .join(" ")

  const active = hoverIdx !== null ? sorted[hoverIdx] : null

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--surface-shadow)]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Calibration curve</h3>
        <div className="flex items-center gap-4 text-[10px] text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded-full bg-[var(--accent)]" aria-hidden="true" />
            Model
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0 w-4 border-t-2 border-dashed border-[var(--text-muted)]"
              aria-hidden="true"
            />
            Perfect calibration
          </span>
        </div>
      </div>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        Predicted probability vs. observed win rate — {totalCount} settled predictions across{" "}
        {sorted.length} bin{sorted.length !== 1 ? "s" : ""}.
      </p>

      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="mx-auto mt-4 w-full max-w-sm"
        role="img"
        aria-label={`Calibration reliability diagram: ${totalCount} settled predictions across ${sorted.length} bins`}
      >
        <line x1={PAD} y1={SIZE - PAD} x2={SIZE - PAD} y2={SIZE - PAD} stroke="var(--border)" strokeWidth={1} />
        <line x1={PAD} y1={PAD} x2={PAD} y2={SIZE - PAD} stroke="var(--border)" strokeWidth={1} />

        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <text x={x(t)} y={SIZE - PAD + 16} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
              {t}
            </text>
            <text x={PAD - 8} y={y(t) + 3} textAnchor="end" fontSize="10" fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}

        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(1)}
          y2={y(1)}
          stroke="var(--text-muted)"
          strokeWidth={2}
          strokeDasharray="4 3"
        />

        <polyline
          points={linePoints}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {sorted.map((b, i) => (
          <circle
            key={`${b.predicted_probability}-${i}`}
            cx={x(b.predicted_probability)}
            cy={y(b.observed_frequency)}
            r={radius(b.count)}
            fill="var(--accent)"
            stroke="var(--bg-surface)"
            strokeWidth={2}
            className="cursor-pointer outline-none focus-visible:stroke-[var(--text-primary)]"
            tabIndex={0}
            role="button"
            aria-label={`Bin ${i + 1}: predicted ${(b.predicted_probability * 100).toFixed(1)}%, observed ${(b.observed_frequency * 100).toFixed(1)}%, ${b.count} predictions`}
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx((cur) => (cur === i ? null : cur))}
            onFocus={() => setHoverIdx(i)}
            onBlur={() => setHoverIdx((cur) => (cur === i ? null : cur))}
          />
        ))}

        <text x={SIZE / 2} y={SIZE - 6} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
          Predicted probability
        </text>
        <text
          x={12}
          y={SIZE / 2}
          textAnchor="middle"
          fontSize="10"
          fill="var(--text-muted)"
          transform={`rotate(-90 12 ${SIZE / 2})`}
        >
          Observed frequency
        </text>
      </svg>

      <div className="mt-3 flex min-h-[2.25rem] items-center rounded-md border border-[var(--border)] bg-[var(--bg-raised)] px-3 py-2 text-xs text-[var(--text-secondary)]">
        {active ? (
          <span>
            Predicted{" "}
            <span className="font-mono text-[var(--text-primary)]">
              {(active.predicted_probability * 100).toFixed(1)}%
            </span>
            {" · "}Observed{" "}
            <span className="font-mono text-[var(--text-primary)]">
              {(active.observed_frequency * 100).toFixed(1)}%
            </span>
            {" · "}n=<span className="font-mono text-[var(--text-primary)]">{active.count}</span>
          </span>
        ) : (
          <span className="text-[var(--text-muted)]">Hover a point for its exact predicted/observed values.</span>
        )}
      </div>
    </div>
  )
}
