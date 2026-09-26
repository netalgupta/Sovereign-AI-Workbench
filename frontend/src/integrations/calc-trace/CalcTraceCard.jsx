import React, { useState } from 'react'
import { Calculator, CheckCircle2, AlertTriangle, ChevronDown, ChevronRight, Clock, Variable } from 'lucide-react'

/**
 * CalcTraceCard — Calculation Trace Viewer delivered by Kanishka (CARD 08 / FRONTEND.md §3.8 / row 41).
 *
 * Visualizes deterministic mathematical derivations with step-by-step simplification,
 * input variable mappings, and the load-bearing NFR-5 verification proof badge.
 *
 * Constraint: Verbatim "✓ verified by SymPy" badge is rendered ONLY when isVerified === true.
 * When isVerified === false, renders explicit unverified warning (CLAUDE.md Hard Constraint #3).
 */
export default function CalcTraceCard({
  expression = '',
  steps = [],
  finalResult = '',
  isVerified = false,
  timestamp = '',
  unit = '',
  variables = [],
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
      {/* ── Top Header ────────────────────────────────────────────────────── */}
      <div
        className="px-4 py-2.5 border-b flex flex-wrap items-center justify-between gap-2"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{
              background: 'var(--color-accent-tint)',
              color: 'var(--color-accent)',
            }}
          >
            <Calculator size={14} />
          </div>
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
            SymPy Engine (Row 41)
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
          {isVerified ? (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold border"
              style={{
                background: 'var(--color-success-tint)',
                borderColor: 'rgba(34, 197, 94, 0.3)',
                color: 'var(--color-success)',
              }}
            >
              <CheckCircle2 size={12} strokeWidth={2.5} />
              <span>✓ verified by SymPy</span>
            </div>
          ) : (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold border"
              style={{
                background: 'rgba(239, 68, 68, 0.1)',
                borderColor: 'rgba(239, 68, 68, 0.3)',
                color: '#ef4444',
              }}
            >
              <AlertTriangle size={12} strokeWidth={2.5} />
              <span>⚠ unverified arithmetic</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
            aria-label={isExpanded ? 'Collapse trace' : 'Expand trace'}
          >
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
      </div>

      {/* ── Primary Expression Banner ────────────────────────────────────── */}
      <div
        className="px-4 py-2 border-b flex items-center justify-between gap-3 font-mono text-[11px]"
        style={{
          background: 'var(--color-overlay)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2 overflow-x-auto">
          <span style={{ color: 'var(--color-text-muted)' }}>Formula:</span>
          <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
            {expression}
          </span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span style={{ color: 'var(--color-text-muted)' }}>Result:</span>
          <span className="font-bold text-emerald-500 font-mono">
            {finalResult} {unit && !finalResult.includes(unit) ? unit : ''}
          </span>
        </div>
      </div>

      {/* ── Collapsible Steps & Variables ─────────────────────────────────── */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Variables Grid */}
          {variables && Object.keys(variables).length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2 text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                <Variable size={11} />
                <span>Input Parameters &amp; Sensor Telemetry</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {Object.entries(variables).map(([k, v]) => (
                  <div
                    key={k}
                    className="p-2 rounded-lg border font-mono text-[11px]"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                    }}
                  >
                    <span style={{ color: 'var(--color-text-muted)' }}>{k}: </span>
                    <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
                      {String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Derivation Steps */}
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 mb-2">
              Derivation Steps ({steps.length})
            </div>
            <div className="space-y-2 font-mono">
              {steps.map((s, idx) => (
                <div
                  key={s.stepNumber || idx}
                  className="p-2.5 rounded-lg border flex flex-col gap-1 text-[11px]"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
                      Step {s.stepNumber || idx + 1}: {s.description}
                    </span>
                    <span className="text-emerald-500 font-bold flex-shrink-0">{s.result}</span>
                  </div>
                  {s.intermediateFormula && (
                    <div
                      className="p-1.5 rounded bg-black/5 dark:bg-white/5 text-[10px] mt-0.5 overflow-x-auto"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      <code>{s.intermediateFormula}</code>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
