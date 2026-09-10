import React, { useState } from 'react'
import { Calculator, CheckCircle2, ChevronDown, ChevronRight, Clock } from 'lucide-react'
import { CANONICAL_CALC_TRACE } from './contract'

/**
 * Placeholder for CalcTraceCard component.
 * Owner: Kanishka (FRONTEND.md §3.8)
 *
 * @param {import('./contract').CalcTraceProps} props
 */
export default function Placeholder({
  expression = CANONICAL_CALC_TRACE.expression,
  steps = CANONICAL_CALC_TRACE.steps,
  finalResult = CANONICAL_CALC_TRACE.finalResult,
  isVerified = CANONICAL_CALC_TRACE.isVerified,
  timestamp = CANONICAL_CALC_TRACE.timestamp,
  variables = CANONICAL_CALC_TRACE.variables,
}) {
  const [isExpanded, setIsExpanded] = useState(true)

  return (
    <div
      className="my-3 rounded-xl border shadow-xs overflow-hidden text-xs"
      style={{
        background: 'var(--color-card-bg)',
        borderColor: 'var(--color-card-border)',
      }}
    >
      {/* Top Header & Integration Handoff Banner */}
      <div
        className="px-4 py-2.5 border-b flex flex-wrap items-center justify-between gap-2"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <Calculator size={15} style={{ color: 'var(--color-accent)' }} />
          <span className="font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
            Deterministic Calculation Trace
          </span>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
            style={{
              background: 'var(--color-overlay)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
          >
            Integration pending — owned by Kanishka
          </span>
        </div>

        <div className="flex items-center gap-2">
          {timestamp && (
            <div className="flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
              <Clock size={11} />
              <span>{timestamp}</span>
            </div>
          )}
          {/* NFR-5 Visual Proof Badge: verbatim "✓ verified by SymPy" */}
          {isVerified && (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold border"
              style={{
                background: 'var(--color-success-tint)',
                borderColor: 'rgba(34, 197, 94, 0.3)',
                color: 'var(--color-success)',
              }}
            >
              <CheckCircle2 size={12} />
              <span>✓ verified by SymPy</span>
            </div>
          )}
        </div>
      </div>

      {/* Main Formula Display */}
      <div className="p-4 flex flex-col gap-3">
        <div
          className="p-3 rounded-lg border font-mono text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
          }}
        >
          <div>
            <span className="text-[10px] uppercase font-semibold block mb-0.5" style={{ color: 'var(--color-text-muted)' }}>
              Governing Equation
            </span>
            <code className="text-amber-500 font-bold">{expression}</code>
          </div>
          <div className="text-right">
            <span className="text-[10px] uppercase font-semibold block mb-0.5" style={{ color: 'var(--color-text-muted)' }}>
              Verified Outcome
            </span>
            <span className="text-sm font-bold font-mono" style={{ color: 'var(--color-success)' }}>
              {finalResult}
            </span>
          </div>
        </div>

        {/* Variables strip if present */}
        {variables && (
          <div className="flex flex-wrap gap-2 text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
            <span className="font-semibold uppercase tracking-wider">Inputs:</span>
            {Object.entries(variables).map(([k, v]) => (
              <span key={k} className="px-1.5 py-0.5 rounded border" style={{ background: 'var(--color-overlay)', borderColor: 'var(--color-border)' }}>
                {k} = <strong style={{ color: 'var(--color-text)' }}>{v}</strong>
              </span>
            ))}
          </div>
        )}

        {/* Collapsible Step Trace Toggle */}
        <div className="pt-1">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1.5 text-xs font-semibold hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>Step-by-Step Symbolic Simplification ({steps.length} steps)</span>
          </button>

          {isExpanded && (
            <div className="mt-2.5 space-y-2 border-l-2 pl-3 ml-1.5" style={{ borderColor: 'var(--color-border)' }}>
              {steps.map((step) => (
                <div
                  key={step.stepNumber}
                  className="p-2.5 rounded-lg border font-mono text-[11px]"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center justify-between text-[10px] text-muted mb-1" style={{ color: 'var(--color-text-muted)' }}>
                    <span className="font-bold text-amber-500">Step {step.stepNumber}: {step.description}</span>
                    <span className="font-semibold">{step.result}</span>
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-text)' }}>
                    {step.intermediateFormula}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
