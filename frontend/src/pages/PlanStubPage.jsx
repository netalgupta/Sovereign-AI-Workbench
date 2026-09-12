import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  GitBranch,
  Brain,
  Code2,
  Eye,
  Calculator,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useChatStore } from '../store/chatStore'
import { PlanGraphView } from '../components/plan/PlanGraphView'

export function PlanStubPage() {
  const { sessionId } = useParams()
  const plan = useChatStore((s) => s.plan) || []

  const hasLivePlan = plan.length > 0
  const doneCount = plan.filter((s) => s.status === 'done').length
  const totalCount = plan.length
  const runningStep = plan.find((s) => s.status === 'running')

  return (
    <div
      className="flex-1 flex flex-col h-full w-full overflow-hidden select-none"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Top Header Chrome ────────────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0 z-10"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        {/* Left: Back Link & Breadcrumbs */}
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
            style={{
              background: 'var(--color-overlay)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
            }}
            title="Return to workbench conversation"
          >
            <ArrowLeft size={13} strokeWidth={2.2} />
            <span>Workbench</span>
          </Link>

          <div className="h-4 w-[1px]" style={{ background: 'var(--color-border)' }} />

          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{
                background: 'rgba(234, 88, 12, 0.12)',
                color: 'var(--color-accent)',
              }}
            >
              <GitBranch size={14} strokeWidth={2.2} />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h1 className="text-xs font-semibold leading-none" style={{ color: 'var(--color-text)' }}>
                  Plan DAG Visualizer
                </h1>
                <span
                  className="px-1.5 py-0.2 rounded text-[10px] font-mono font-medium"
                  style={{
                    background: 'var(--color-overlay)',
                    color: 'var(--color-accent)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  FR-5
                </span>
              </div>
              <span className="text-[10px] leading-tight mt-0.5" style={{ color: 'var(--color-text-faint)' }}>
                Session: {sessionId || 'Refinery Turnaround Analysis'}
              </span>
            </div>
          </div>
        </div>

        {/* Center: Live Execution Progress Pill */}
        <div
          className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-full text-xs border"
          style={{
            background: 'var(--color-overlay)',
            borderColor: 'var(--color-border)',
          }}
        >
          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full animate-pulse"
              style={{ background: 'var(--color-accent)' }}
            />
            <span className="font-semibold text-[11px]" style={{ color: 'var(--color-text)' }}>
              Step {doneCount + (runningStep ? 1 : 0)} of {totalCount}
            </span>
          </div>

          <span style={{ color: 'var(--color-border)' }}>|</span>

          <span className="text-[11px] truncate max-w-[240px]" style={{ color: 'var(--color-text-muted)' }}>
            {runningStep ? runningStep.description : 'Execution in progress'}
          </span>
        </div>

        {/* Right: Sub-Agent Legend + Security Tag */}
        <div className="flex items-center gap-3">
          {/* Agent Type Pills */}
          <div className="hidden lg:flex items-center gap-2 text-[10px] font-mono">
            <span className="flex items-center gap-1 opacity-70" style={{ color: 'var(--color-text-muted)' }}>
              <Brain size={11} style={{ color: 'var(--color-accent)' }} /> Reasoning
            </span>
            <span className="flex items-center gap-1 opacity-70" style={{ color: 'var(--color-text-muted)' }}>
              <Code2 size={11} style={{ color: 'var(--color-accent)' }} /> Code
            </span>
            <span className="flex items-center gap-1 opacity-70" style={{ color: 'var(--color-text-muted)' }}>
              <Eye size={11} style={{ color: 'var(--color-accent)' }} /> Vision
            </span>
            <span className="flex items-center gap-1 opacity-70" style={{ color: 'var(--color-text-muted)' }}>
              <Calculator size={11} style={{ color: 'var(--color-accent)' }} /> Math
            </span>
          </div>

          <div className="h-4 w-[1px] hidden lg:block" style={{ background: 'var(--color-border)' }} />

          {/* Sandbox Indicator */}
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono"
            style={{
              background: 'rgba(34, 197, 94, 0.08)',
              color: 'var(--color-success)',
              border: '1px solid rgba(34, 197, 94, 0.25)',
            }}
          >
            <ShieldCheck size={12} strokeWidth={2.2} />
            <span className="font-medium">AIR-GAPPED</span>
          </div>
        </div>
      </header>

      {/* ── Sub-header Hint Banner ───────────────────────────────────── */}
      <div
        className="px-5 py-1.5 border-b flex items-center justify-between text-[11px]"
        style={{
          background: 'var(--color-overlay)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }}
      >
        <div className="flex items-center gap-2">
          <Sparkles size={12} style={{ color: 'var(--color-accent)' }} />
          <span>
            <strong>Interactive DAG:</strong> Step 1 forks into Code (Branch A) and Vision (Branch B) in parallel, converging at Math. Click any node to jump to its live execution trace in chat.
          </span>
        </div>

        {/* Status Indicators */}
        <div className="flex items-center gap-3 font-mono text-[10px]">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-success)' }} />
            Done ({doneCount})
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-accent)' }} />
            Running ({runningStep ? 1 : 0})
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-border)' }} />
            Pending ({plan.filter((s) => s.status === 'pending').length})
          </span>
        </div>
      </div>

      {/* ── Main Canvas (React Flow + Dagre) ───────────────────────── */}
      <main className="flex-1 w-full h-full relative overflow-hidden">
        {hasLivePlan ? (
          <PlanGraphView plan={plan} />
        ) : (
          <div
            className="flex flex-col items-center justify-center h-full gap-4 select-none"
            style={{ color: 'var(--color-text-faint)' }}
          >
            <GitBranch size={40} strokeWidth={1.2} style={{ opacity: 0.3 }} />
            <div className="text-center max-w-xs">
              <p className="text-sm font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                No multi-step execution plan for this turn
              </p>
              <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--color-text-faint)' }}>
                This turn used the direct response path — one retrieval, one answer.
                A DAG will appear here on the next multi-step agentic query.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
