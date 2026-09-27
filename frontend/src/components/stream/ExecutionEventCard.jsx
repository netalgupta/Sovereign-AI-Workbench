import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Terminal,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Code2,
  Sparkles,
} from 'lucide-react'
import { springs, transitions } from '../../lib/motion'

/**
 * ExecutionEventCard — Unified premium agent execution component.
 *
 * Implements:
 * - Collapsed state: single elegant event row with tool name, status, duration
 * - Expanded state: exact arguments, output on demand, estimate warnings
 * - States: pending (muted grey), running (accent / subtle pulse), done (muted green), failed (red)
 * - Safe for all tools: search_documents, traverse_graph, evaluate_expression, etc.
 */
export function ExecutionEventCard({
  toolName,
  status = 'pending',
  arguments: args,
  output,
  duration,
  seconds,
  isEstimate = false,
  eventIndex,
  id,
}) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Status mapping
  const statusConfig = {
    pending: {
      color: 'var(--color-pending)',
      bg: 'var(--color-overlay)',
      border: 'var(--color-border)',
      label: 'Queued',
    },
    running: {
      color: 'var(--color-accent)',
      bg: 'var(--color-accent-tint)',
      border: 'var(--color-accent-border)',
      label: 'Executing...',
    },
    done: {
      color: 'var(--color-success)',
      bg: 'var(--color-success-tint)',
      border: 'var(--color-border)',
      label: 'Completed',
    },
    failed: {
      color: 'var(--color-error)',
      bg: 'var(--color-error-tint)',
      border: 'var(--color-error)',
      label: 'Failed',
    },
  }[status] || {
    color: 'var(--color-pending)',
    bg: 'var(--color-overlay)',
    border: 'var(--color-border)',
    label: status,
  }

  const durationDisplay =
    duration != null
      ? `${duration}ms`
      : seconds != null
      ? `${Number(seconds).toFixed(1)}s`
      : null

  return (
    <div
      id={id}
      className="my-1.5 rounded-xl border overflow-hidden transition-all duration-200"
      style={{
        background: 'var(--color-surface)',
        borderColor: statusConfig.border,
      }}
    >
      {/* ── Collapsed Header Row ────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-left cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors select-none"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Status Indicator Icon */}
          <div
            className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0"
            style={{
              background: statusConfig.bg,
              color: statusConfig.color,
            }}
          >
            {status === 'running' ? (
              <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-ping" />
            ) : status === 'done' ? (
              <CheckCircle2 size={13} strokeWidth={2.4} />
            ) : status === 'failed' ? (
              <AlertCircle size={13} strokeWidth={2.4} />
            ) : (
              <Terminal size={12} strokeWidth={2} />
            )}
          </div>

          <div className="flex items-center gap-2 truncate">
            <span
              className="font-mono font-semibold tracking-tight text-[12px]"
              style={{ color: 'var(--color-text)' }}
            >
              {toolName}
            </span>

            {isEstimate && (
              <span
                className="px-1.5 py-0.2 rounded text-[9.5px] font-mono font-bold tracking-wider uppercase border"
                style={{
                  background: 'var(--color-warning-tint)',
                  color: 'var(--color-warning)',
                  borderColor: 'var(--color-border)',
                }}
                title="Model estimate — not a physical measurement (CHART_STRESS_REPORT.md)"
              >
                ESTIMATE
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono flex-shrink-0">
          {durationDisplay && (
            <span
              className="flex items-center gap-1"
              style={{ color: 'var(--color-text-muted)' }}
            >
              <Clock size={11} />
              {durationDisplay}
            </span>
          )}

          <span
            className="font-medium text-[11px]"
            style={{ color: statusConfig.color }}
          >
            {statusConfig.label}
          </span>

          <div className="text-[var(--color-text-muted)] ml-1">
            {isExpanded ? (
              <ChevronDown size={14} strokeWidth={2} />
            ) : (
              <ChevronRight size={14} strokeWidth={2} />
            )}
          </div>
        </div>
      </button>

      {/* ── Expanded Parameters & Output ────────────────────────────── */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={transitions.fast}
            className="border-t px-3.5 py-2.5 flex flex-col gap-2.5 text-xs"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg)',
            }}
          >
            {/* Input Arguments */}
            {args && (
              <div className="flex flex-col gap-1">
                <span
                  className="text-[10px] font-mono uppercase tracking-wider font-semibold"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  ARGUMENTS
                </span>
                <pre
                  className="p-2 rounded-lg font-mono text-[11px] overflow-x-auto border"
                  style={{
                    background: 'var(--color-code-bg)',
                    borderColor: 'var(--color-code-border)',
                    color: 'var(--color-text)',
                  }}
                >
                  {typeof args === 'string'
                    ? args
                    : JSON.stringify(args, null, 2)}
                </pre>
              </div>
            )}

            {/* Output Result */}
            {output != null && (
              <div className="flex flex-col gap-1">
                <span
                  className="text-[10px] font-mono uppercase tracking-wider font-semibold"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  OUTPUT RESULT
                </span>
                <pre
                  className="p-2 rounded-lg font-mono text-[11px] max-h-48 overflow-y-auto border leading-relaxed"
                  style={{
                    background: 'var(--color-code-bg)',
                    borderColor: 'var(--color-code-border)',
                    color: 'var(--color-text)',
                  }}
                >
                  {typeof output === 'string'
                    ? output
                    : JSON.stringify(output, null, 2)}
                </pre>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
