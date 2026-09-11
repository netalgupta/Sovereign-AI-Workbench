import { useState, useEffect } from 'react'
import {
  RotateCcw,
  MoreHorizontal,
  ChevronRight,
  Search,
  Cpu,
  Calculator,
  Layers,
  FileCheck,
  Terminal,
} from 'lucide-react'
import { showToast } from '../../store/toastStore'

// Step categories mapped strictly to industrial tool-call schema
// Retrieval: "Retrieving sources" (active) / "Retrieved sources" (completed)
// Computation: "Running analysis" / "Ran analysis" or "Computing" / "Computed"
// Verification: "Checking constraints" / "Checked constraints" or "Verifying" / "Verified"
// Synthesis: "Drafting response" / "Drafted response"
// Routing/Planning: "Planning next step" / "Planned next step" or "Classifying request" / "Classified request"

const INITIAL_STEPS = [
  {
    id: 'step-retrieval',
    category: 'retrieval',
    activeLabel: 'Retrieving sources',
    completedLabel: 'Retrieved sources',
    status: 'active',
    baseSeconds: 4,
    icon: Search,
    trace: [
      { time: '10:14:05.12', text: 'Query router mapped intent to [hcu_refinery_operations, safety_sop]' },
      { time: '10:14:05.34', text: 'FAISS hybrid search on MRPL corpus (dense BGE-Large + sparse BM25)' },
      { time: '10:14:05.89', text: 'Embedding score matched 6 chunks from SOP-114-Rev3 & Benzene Safety Circular' },
      { time: '10:14:06.42', text: 'Cross-encoder reranking completed (threshold >= 0.82) -> 3 chunks isolated' },
      { time: '10:14:07.01', text: 'Zero-egress memory buffer: 2,410 tokens isolated in local sandbox' },
    ],
  },
  {
    id: 'step-verification',
    category: 'verification',
    activeLabel: 'Checking constraints',
    completedLabel: 'Checked constraints',
    status: 'completed',
    duration: '0.9s',
    icon: FileCheck,
    trace: [
      { time: '10:14:04.10', text: 'Ingested plant safety parameter matrix: API-521 & Plant SOP §14.2' },
      { time: '10:14:04.45', text: 'Evaluated boundary threshold: ΔP_max <= 420 m³/h at current feed-rate' },
      { time: '10:14:04.98', text: 'Safety margin confirmed: +18.2% operational headroom (status: PASS)' },
    ],
  },
  {
    id: 'step-computation',
    category: 'computation',
    activeLabel: 'Running analysis',
    completedLabel: 'Ran analysis',
    status: 'completed',
    duration: '1.8s',
    icon: Calculator,
    trace: [
      { time: '10:14:02.30', text: 'SymPy AST compiled for volumetric flow conversion formula' },
      { time: '10:14:02.85', text: 'Evaluated differential pressure equation: ΔP = k · Q^1.85' },
      { time: '10:14:04.05', text: 'Dimensional consistency verified across metric unit parameters' },
    ],
  },
  {
    id: 'step-planning',
    category: 'planning',
    activeLabel: 'Planning next step',
    completedLabel: 'Planned task graph',
    status: 'completed',
    duration: '1.2s',
    icon: Layers,
    trace: [
      { time: '10:14:01.05', text: 'Router parsed intent: engineering parameter validation for Unit HCU-2' },
      { time: '10:14:01.40', text: 'Constructed DAG execution plan: 5 sequential verification phases' },
      { time: '10:14:02.22', text: 'Air-gap sandbox verified: 0 external network requests permitted' },
    ],
  },
  {
    id: 'step-routing',
    category: 'routing',
    activeLabel: 'Classifying request',
    completedLabel: 'Classified request',
    status: 'completed',
    duration: '0.5s',
    icon: Cpu,
    trace: [
      { time: '10:14:00.60', text: 'Prompt tokenized: 68 tokens parsed into semantic graph' },
      { time: '10:14:00.95', text: 'Classified domain tags: [code_gen, formula_eval, safety_sop]' },
    ],
  },
]

const PLAN_PHASES = [
  { num: 1, label: 'Understand query', status: 'done' },
  { num: 2, label: 'Retrieve information', status: 'active' },
  { num: 3, label: 'Analyze & reason', status: 'pending' },
  { num: 4, label: 'Generate response', status: 'pending' },
  { num: 5, label: 'Validate & finalize', status: 'pending' },
]

export function PlanRail() {
  // Live date/time display
  const [currentDateTime, setCurrentDateTime] = useState('')

  // Live elapsed counter for active step (e.g. "4s", "5s"...)
  const [activeElapsed, setActiveElapsed] = useState(4)

  // Track expanded state for each step independently (collapsed by default)
  const [expandedSteps, setExpandedSteps] = useState({})

  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      const formatted =
        now.toLocaleDateString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
        }) +
        ', ' +
        now.toLocaleTimeString('en-GB', {
          hour: '2-digit',
          minute: '2-digit',
        })
      setCurrentDateTime(formatted)
    }
    updateTime()
    const clockTimer = setInterval(updateTime, 30000)
    return () => clearInterval(clockTimer)
  }, [])

  // Live timer for active step elapsed seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveElapsed((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Expose toggle to window for automated testing/capture
  useEffect(() => {
    window.__workbenchToggleStep = (stepId) => {
      setExpandedSteps((prev) => ({
        ...prev,
        [stepId]: !prev[stepId],
      }))
    }
    window.__workbenchExpandStep = (stepId, expand = true) => {
      setExpandedSteps((prev) => ({
        ...prev,
        [stepId]: expand,
      }))
    }
    return () => {
      delete window.__workbenchToggleStep
      delete window.__workbenchExpandStep
    }
  }, [])

  const toggleStep = (stepId) => {
    setExpandedSteps((prev) => ({
      ...prev,
      [stepId]: !prev[stepId],
    }))
  }

  return (
    <aside
      className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden relative"
      style={{
        width: 320,
        background: 'var(--color-bg)',
        borderLeft: '1px solid var(--color-border)',
      }}
      aria-label="Task execution plan and live reasoning trace"
    >
      {/* ── 1. Rail Header: Title + Replan Button + Live Time + Options ─── */}
      <div
        className="flex flex-col px-4 pt-3 pb-2.5 flex-shrink-0 gap-1.5"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2
              className="text-sm font-bold tracking-tight leading-tight"
              style={{ color: 'var(--color-text)' }}
            >
              Plan
            </h2>

            {/* Replan Button */}
            <button
              type="button"
              onClick={() =>
                showToast(
                  'Replanning — triggers adaptive task graph regeneration (CARD 10 / AGENTS_SPEC.md)',
                  'info'
                )
              }
              className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] shadow-xs"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-accent)',
              }}
              title="Trigger agent re-planning loop"
            >
              <RotateCcw size={10} strokeWidth={2.5} />
              <span>Replan</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-mono tracking-tight"
              style={{ color: 'var(--color-text-muted)' }}
              title="System local time"
            >
              {currentDateTime}
            </span>

            <button
              type="button"
              onClick={() =>
                showToast('Execution graph settings — dagre graph available in /plan', 'info')
              }
              className="w-6 h-6 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
              style={{ color: 'var(--color-text-muted)' }}
              title="Plan options"
            >
              <MoreHorizontal size={14} strokeWidth={2} />
            </button>
          </div>
        </div>

        {/* ── Compact Plan Strip (Tick marks / Progress bar, not circle tracker) ── */}
        <div className="flex flex-col gap-1.5 pt-1">
          {/* Segmented Progress Ticks */}
          <div className="grid grid-cols-5 gap-1.5 w-full items-center" title="Plan Progress: Step 2 of 5 active (40%)">
            {PLAN_PHASES.map((phase) => {
              const isDone = phase.status === 'done'
              const isActive = phase.status === 'active'
              return (
                <div
                  key={phase.num}
                  className="h-1.5 rounded-xs transition-fast relative overflow-hidden"
                  style={{
                    background: isDone
                      ? 'var(--color-success)'
                      : isActive
                      ? 'var(--color-accent)'
                      : 'var(--color-border)',
                  }}
                >
                  {isActive && (
                    <div
                      className="absolute inset-0 opacity-40 animate-pulse"
                      style={{ background: 'white' }}
                    />
                  )}
                </div>
              )
            })}
          </div>

          {/* Compact Step Status Row */}
          <div className="flex items-center justify-between text-[11px] leading-tight">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
                Step 2/5
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>·</span>
              <span className="truncate" style={{ color: 'var(--color-text-muted)' }}>
                Retrieve information
              </span>
            </div>
            <span className="font-mono text-[10px] font-medium" style={{ color: 'var(--color-accent)' }}>
              40%
            </span>
          </div>
        </div>
      </div>

      {/* ── 2. Scrollable Rail Body: Collapsible Reasoning Trace Stack ─── */}
      <div className="flex-1 overflow-y-auto px-4 py-3 z-10 flex flex-col gap-4">
        {/* Section Header */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Terminal size={12} strokeWidth={2.4} style={{ color: 'var(--color-accent)' }} />
              <span
                className="text-xs font-bold tracking-tight uppercase"
                style={{ color: 'var(--color-text)' }}
              >
                Reasoning Trace
              </span>
            </div>
            <button
              type="button"
              onClick={() =>
                showToast('Audit log exporter — full execution trail (CARD 10 / FRONTEND.md §3.10)', 'info')
              }
              className="text-[10px] font-medium transition-fast hover:underline cursor-pointer"
              style={{ color: 'var(--color-text-muted)' }}
              title="View full audit trail"
            >
              Audit log
            </button>
          </div>

          {/* ── Collapsible Steps Stack (Most recent at top) ───────────── */}
          <div className="flex flex-col gap-1.5">
            {INITIAL_STEPS.map((step) => {
              const isActive = step.status === 'active'
              const isExpanded = !!expandedSteps[step.id]
              const displayLabel = isActive ? step.activeLabel : step.completedLabel
              const displayDuration = isActive ? `${activeElapsed}s` : step.duration

              return (
                <div
                  key={step.id}
                  className="flex flex-col rounded-md transition-fast"
                  style={{
                    background: isExpanded
                      ? 'var(--color-surface)'
                      : 'transparent',
                  }}
                >
                  {/* Collapsed Single-Line Row (Clickable) */}
                  <button
                    type="button"
                    onClick={() => toggleStep(step.id)}
                    aria-expanded={isExpanded}
                    className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-left transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] group"
                    style={{
                      border: isExpanded ? '1px solid var(--color-border)' : '1px solid transparent',
                    }}
                    title={`Click to ${isExpanded ? 'collapse' : 'expand'} reasoning trace for this step`}
                  >
                    {/* Left: Indicator dot + Status word + Duration */}
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      {/* Status Dot: Pulsing breathing dot while active, static muted dot once completed */}
                      {isActive ? (
                        <div className="relative flex items-center justify-center w-2 h-2 flex-shrink-0">
                          <span
                            className="w-2 h-2 rounded-full animate-breathing-dot"
                            style={{
                              background: 'var(--color-accent)',
                              color: 'var(--color-accent)',
                            }}
                          />
                        </div>
                      ) : (
                        <div
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{ background: 'var(--color-text-faint)' }}
                        />
                      )}

                      {/* Status text + Elapsed time in a single row */}
                      <div className="flex items-center gap-1.5 min-w-0 text-xs truncate">
                        <span
                          className={`truncate font-medium transition-fast ${
                            isActive ? 'font-semibold' : ''
                          }`}
                          style={{
                            color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                          }}
                        >
                          {displayLabel}
                        </span>
                        <span
                          className="text-[10px]"
                          style={{ color: 'var(--color-text-faint)' }}
                        >
                          ·
                        </span>
                        <span
                          className="font-mono text-[11px] flex-shrink-0"
                          style={{
                            color: isActive ? 'var(--color-accent)' : 'var(--color-text-faint)',
                          }}
                        >
                          {displayDuration}
                        </span>
                      </div>
                    </div>

                    {/* Right: Chevron indicator (smooth rotation) */}
                    <div
                      className="ml-2 transition-transform duration-200 flex-shrink-0"
                      style={{
                        transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                        color: 'var(--color-text-muted)',
                      }}
                    >
                      <ChevronRight size={13} strokeWidth={2.2} />
                    </div>
                  </button>

                  {/* ── Expanded Recessed Panel (Smooth Height Transition) ── */}
                  <div className={`collapsible-grid ${isExpanded ? 'is-expanded' : ''}`}>
                    <div className="collapsible-inner">
                      <div
                        className="mx-1 mt-1 mb-1.5 p-2.5 rounded-md font-mono text-[11px] leading-relaxed flex flex-col gap-1.5"
                        style={{
                          background: 'var(--color-overlay)',
                          color: 'var(--color-text)',
                        }}
                      >
                        {step.trace.map((item, idx) => (
                          <div
                            key={idx}
                            className="flex items-start gap-1.5 text-[11px] leading-normal"
                          >
                            <span
                              className="text-[9px] flex-shrink-0 select-none opacity-60 mt-0.5"
                              style={{ color: 'var(--color-text-muted)' }}
                            >
                              {item.time}
                            </span>
                            <span
                              className="break-words flex-1"
                              style={{ color: 'var(--color-text)' }}
                            >
                              {item.text}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ── 3. Toned-Down System Monitor ─────────────────────────────── */}
        <div className="flex flex-col gap-2 mt-auto pt-2" style={{ borderTop: '1px solid var(--color-border)' }}>
          <div className="flex items-center justify-between">
            <span
              className="text-[11px] font-bold tracking-tight uppercase"
              style={{ color: 'var(--color-text-muted)' }}
            >
              System Monitor
            </span>
            <div className="flex items-center gap-1.5" title="Air-gapped Sandbox Verified">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: 'var(--color-success)' }}
              />
              <span className="text-[10px] font-medium" style={{ color: 'var(--color-success)' }}>
                Isolated
              </span>
            </div>
          </div>

          {/* Compact Telemetry Metrics (3-Column Grid) */}
          <div className="grid grid-cols-3 gap-1.5">
            {/* CPU */}
            <div
              className="p-1.5 rounded-md flex flex-col gap-0.5"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-[9px]" style={{ color: 'var(--color-text-muted)' }}>
                <span>CPU</span>
                <span className="font-mono font-semibold" style={{ color: 'var(--color-text)' }}>14%</span>
              </div>
              <svg className="w-full h-3.5" viewBox="0 0 60 14" fill="none">
                <path
                  d="M0 11 Q 15 8, 30 10 T 60 7"
                  stroke="var(--color-accent)"
                  strokeWidth="1.2"
                  fill="none"
                />
              </svg>
            </div>

            {/* Memory */}
            <div
              className="p-1.5 rounded-md flex flex-col gap-0.5"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-[9px]" style={{ color: 'var(--color-text-muted)' }}>
                <span>MEM</span>
                <span className="font-mono font-semibold" style={{ color: 'var(--color-text)' }}>3.8 GB</span>
              </div>
              <svg className="w-full h-3.5" viewBox="0 0 60 14" fill="none">
                <path
                  d="M0 10 Q 15 7, 30 9 T 60 6"
                  stroke="var(--color-warning)"
                  strokeWidth="1.2"
                  fill="none"
                />
              </svg>
            </div>

            {/* Zero Egress Network */}
            <div
              className="p-1.5 rounded-md flex flex-col gap-0.5"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-[9px]" style={{ color: 'var(--color-text-muted)' }}>
                <span>NET</span>
                <span className="font-mono font-semibold" style={{ color: 'var(--color-success)' }}>0.0 MB/s</span>
              </div>
              <svg className="w-full h-3.5" viewBox="0 0 60 14" fill="none">
                <line
                  x1="0"
                  y1="10"
                  x2="60"
                  y2="10"
                  stroke="var(--color-success)"
                  strokeWidth="1.2"
                />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
