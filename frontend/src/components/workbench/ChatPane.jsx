import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  MoreHorizontal,
  Paperclip,
  Globe,
  Send,
  ChevronRight,
  CheckCheck,
  Copy,
  Check,
  BookOpen,
  FileCode,
  Sparkles,
  Bot,
  Network,
  Layers,
  FileCheck,
  Calculator,
  Search,
  Play,
  ShieldAlert,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from '../../store/chatStore'
import { sendMessage } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { SourcesUsedList } from '../../integrations/citations'
import { NetworkMonitorBar } from '../../integrations/network'

// Set of 12 phrases for completed thinking block word rotation
const ROTATION_PHRASES = [
  'Deliberated',
  'Worked through it',
  'Traced',
  'Chewed on it',
  'Reckoned',
  'Puzzled it out',
  'Untangled it',
  'Sorted through it',
  'Mulled it over',
  'Worked it out',
  'Pieced it together',
  'Ran it down',
]

/**
 * Format rotation phrase with pipeline steps count and timing.
 * Formats grammatically without redundant "through" or awkward doubling.
 */
function formatThinkingHeader(phrase, stepCount = 4, duration = '4.7s') {
  switch (phrase) {
    case 'Worked through it':
      return `Worked through ${stepCount} pipeline steps · ${duration} total`
    case 'Sorted through it':
      return `Sorted through ${stepCount} pipeline steps · ${duration} total`
    case 'Traced':
      return `Traced through ${stepCount} pipeline steps · ${duration} total`
    case 'Deliberated':
      return `Deliberated through ${stepCount} pipeline steps · ${duration} total`
    default:
      return `${phrase} · ${stepCount} pipeline steps · ${duration} total`
  }
}

// Inline live-thinking trace data definitions
const ACTIVE_TRACE_ITEMS = [
  { time: '10:20:05.10', text: 'Router mapped intent: [quench_control, column_reflux_stabilization]' },
  { time: '10:20:05.34', text: 'Milvus hybrid search on collection "hcu_emergency_procedures" (dense + sparse BM25)' },
  { time: '10:20:05.80', text: 'Retrieved 3 SOP sections: SOP-HCU-412 §4.3 (Quench Flow Rates)' },
  { time: '10:20:06.15', text: 'Cross-encoder reranking completed: threshold >= 0.86 (2 candidate procedures isolated)' },
  { time: '10:20:06.60', text: 'Sandboxed context buffered: 2,120 tokens in zero-egress local memory' },
]

const COMPLETED_REASONING_STEPS_1 = [
  {
    id: 'step-1-verification',
    label: 'Checked constraints',
    duration: '0.9s',
    category: 'verification',
    icon: FileCheck,
    trace: [
      { time: '10:14:04.10', text: 'Ingested plant safety parameter matrix: API-521 & Plant SOP §14.2' },
      { time: '10:14:04.45', text: 'Evaluated boundary threshold: ΔP_max <= 420 m³/h at current feed-rate' },
      { time: '10:14:04.98', text: 'Safety margin confirmed: +18.2% operational headroom (status: PASS)' },
    ],
  },
  {
    id: 'step-2-computation',
    label: 'Ran analysis',
    duration: '1.8s',
    category: 'computation',
    icon: Calculator,
    trace: [
      { time: '10:14:02.30', text: 'SymPy AST compiled for volumetric flow conversion formula' },
      { time: '10:14:02.85', text: 'Evaluated differential pressure equation: ΔP = k · Q^1.85' },
      { time: '10:14:04.05', text: 'Dimensional consistency verified across metric unit parameters' },
    ],
  },
  {
    id: 'step-3-retrieval',
    label: 'Retrieved sources',
    duration: '1.2s',
    category: 'retrieval',
    icon: Search,
    trace: [
      { time: '10:14:01.40', text: 'Milvus search against collection "hcu_operations_docs"' },
      { time: '10:14:01.88', text: 'Dense embeddings matched 3 chunks from HCU_Operations_Manual.pdf' },
      { time: '10:14:02.10', text: 'Retrieved 2 chunks from Safety_Guidelines_2024.docx' },
    ],
  },
  {
    id: 'step-4-planning',
    label: 'Planned task graph',
    duration: '0.8s',
    category: 'planning',
    icon: Layers,
    trace: [
      { time: '10:14:00.60', text: 'Router parsed intent: engineering parameter validation for Unit HCU-2' },
      { time: '10:14:00.95', text: 'Constructed DAG execution plan: 5 sequential verification phases' },
    ],
  },
]

const COMPLETED_REASONING_STEPS_2 = [
  {
    id: 'step-2-1-telemetry',
    label: 'Queried sensor trends',
    duration: '0.8s',
    trace: [
      { time: '10:18:12.10', text: 'Fetched historical time-series from Historical_Trend_Data.csv (Row 1042-1090)' },
      { time: '10:18:12.45', text: 'Parsed thermocouple array TC-201A through TC-201F across 4 shifts' },
    ],
  },
  {
    id: 'step-2-2-limits',
    label: 'Evaluated operating envelope',
    duration: '0.6s',
    trace: [
      { time: '10:18:12.80', text: 'Current average: 382°C vs upper limit 400°C (headroom: 18°C)' },
      { time: '10:18:13.10', text: 'Rate of change: +0.4°C/hr (well below thermal excursion threshold of +2.0°C/hr)' },
    ],
  },
  {
    id: 'step-2-3-synthesis',
    label: 'Synthesized telemetry summary',
    duration: '0.5s',
    trace: [
      { time: '10:18:13.40', text: 'Generated verification citation [4] pointing to row-level CSV sensor log' },
    ],
  },
]

// Mock citation data for the STATIC demo turns (pre-loaded session)
// These match the same shape as api.js MOCK_CITATIONS.
const DEMO_CITATIONS = [
  {
    id: 1,
    doc: 'HCU_Operations_Manual.pdf',
    section: 'Section 4.2 — Feed Rate Operating Limits',
    passage:
      'The design-basis feed rate for the Hydrocracking Unit (HCU-2) shall not exceed 110 % of the nameplate capacity (Q_d = 1,450 m³/h) under any continuous operating mode. Exceedance for more than 15 minutes triggers an automatic interlock via DCS feed-forward controller (FFC-201).',
  },
  {
    id: 2,
    doc: 'Safety_Guidelines_2024.docx',
    section: 'Page 14 — High-Temperature Catalyst Runaway Prevention',
    passage:
      'At LHSV > 1.8 h⁻¹, exothermic quench reactions become thermally unstable. H₂/HC ratio must be maintained above 1,000 Nm³/m³ to suppress runaway. See Table 3-A for alarm setpoints.',
  },
  {
    id: 3,
    doc: 'Emissions_Regulations_2024.pdf',
    section: 'Section 9 — Downstream Fractionation Column Flooding Criteria',
    passage:
      'At feed rates above 110 % of design capacity, flooding probability increases to 34 % based on the correlation: F_factor = u_v × √ρ_v. Immediate operator intervention is required per MOC procedure.',
  },
  {
    id: 4,
    doc: 'Historical_Trend_Data.csv',
    section: 'Row 1042–1090 — Thermocouple Array TC-201 (4 Shifts)',
    passage:
      'TC-201A: 381.4 °C · TC-201B: 382.1 °C · TC-201C: 383.0 °C. Rolling average: 381.95 °C. Upper limit: 400 °C. Rate-of-change: +0.4 °C/hr.',
  },
]

export function ChatPane() {
  const messages = useChatStore((s) => s.messages)
  const addMessage = useChatStore((s) => s.addMessage)
  const appendStreamChunk = useChatStore((s) => s.appendStreamChunk)
  const finishStreaming = useChatStore((s) => s.finishStreaming)
  const sessionId = useChatStore((s) => s.sessionId)
  const plan = useChatStore((s) => s.plan) || []
  const setPlan = useChatStore((s) => s.setPlan)
  const awaitingHumanApproval = useChatStore((s) => s.awaitingHumanApproval)
  const setAwaitingApproval = useChatStore((s) => s.setAwaitingApproval)
  const openApprovalModal = useChatStore((s) => s.openApprovalModal)
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState('')
  const [isPending, setIsPending] = useState(false)

  // Top tabs: Chat / Notebooks / Artifacts
  const [activeTab, setActiveTab] = useState('chat')

  // Code block copy state
  const [copiedCode, setCopiedCode] = useState(false)

  // Model selector state (Cosmetic only)
  const [selectedModel, setSelectedModel] = useState('GPT-4o (Engineering)')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)

  // ── Word Rotation for Completed Thinking Blocks ─────────────────────────
  // Pick two distinct words for the two completed messages in the session
  const [phraseMsg1, setPhraseMsg1] = useState(() => {
    return ROTATION_PHRASES[Math.floor(Math.random() * ROTATION_PHRASES.length)]
  })
  const [phraseMsg2, setPhraseMsg2] = useState(() => {
    const remaining = ROTATION_PHRASES.filter((p) => p !== 'Untangled it')
    return remaining[Math.floor(Math.random() * remaining.length)]
  })

  // ── Inline Live-Thinking States ──────────────────────────────────────────
  // 1. Mid-response active turn (single line dot + present-participle + elapsed)
  const [isMidResponse, setIsMidResponse] = useState(true)
  const [isMidResponseExpanded, setIsMidResponseExpanded] = useState(false)
  const [liveElapsed, setLiveElapsed] = useState(8)

  // 2. Completed message thinking blocks expansion state
  const [isCompleted1Expanded, setIsCompleted1Expanded] = useState(false)
  const [isCompleted2Expanded, setIsCompleted2Expanded] = useState(false)
  const [expandedCompletedSteps, setExpandedCompletedSteps] = useState({})

  // ── Node Click -> Scroll & Expand Tool Event Trace ───────────────────────
  useEffect(() => {
    const targetId = searchParams.get('scrollTo')
    if (!targetId) return

    const timer = setTimeout(() => {
      if (COMPLETED_REASONING_STEPS_1.some((s) => s.id === targetId)) {
        setIsCompleted1Expanded(true)
      }
      if (COMPLETED_REASONING_STEPS_2.some((s) => s.id === targetId)) {
        setIsCompleted2Expanded(true)
      }

      setExpandedCompletedSteps((prev) => ({ ...prev, [targetId]: true }))

      const el = document.getElementById(targetId)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.style.transition = 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)'
        el.style.outline = '2px solid var(--color-accent)'
        el.style.borderRadius = '4px'
        el.style.padding = '4px 8px'
        el.style.background = 'var(--color-surface-hover)'
        setTimeout(() => {
          el.style.outline = 'none'
          el.style.background = 'transparent'
          el.style.padding = '0px'
        }, 2400)
      }
    }, 50)

    searchParams.delete('scrollTo')
    setSearchParams(searchParams, { replace: true })

    return () => clearTimeout(timer)
  }, [searchParams, setSearchParams])

  // Live timer for active mid-response thinking
  useEffect(() => {
    const timer = setInterval(() => {
      setLiveElapsed((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Auto-scroll chat container to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > 0) {
      const el = document.getElementById('chat-messages-container')
      if (el) {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      }
    }
  }, [messages.length])

  // Expose test automation hooks
  useEffect(() => {
    window.__workbenchSetThinkingMidResponse = (active) => setIsMidResponse(active)
    window.__workbenchSetThinkingExpanded = (expanded) => setIsMidResponseExpanded(expanded)
    window.__workbenchSetCompletedPhrases = (p1, p2) => {
      if (p1) setPhraseMsg1(p1)
      if (p2) setPhraseMsg2(p2)
    }
    window.__workbenchTriggerApproval = (action) => useChatStore.getState().setAwaitingApproval(true, action)
    window.__workbenchResolveApproval = (confirmed) => useChatStore.getState().resolveApproval(confirmed)
    return () => {
      delete window.__workbenchSetThinkingMidResponse
      delete window.__workbenchSetThinkingExpanded
      delete window.__workbenchSetCompletedPhrases
      delete window.__workbenchTriggerApproval
      delete window.__workbenchResolveApproval
    }
  }, [])

  const MODELS = [
    'GPT-4o (Engineering)',
    'Qwen 2.5-Coder (7B Local)',
    'Qwen 2.5-14B (Reasoning)',
    'Phi-3.5 Mini (Fast Router)',
  ]

  const CODE_SNIPPET = `if feed_rate > 1.10 * design_capacity:
    alert("High risk: exceeds design threshold")
    suggest_mitigation(cool_quench=True)`

  const handleSend = async () => {
    if (!draft.trim() || isPending || awaitingHumanApproval) return
    const text = draft.trim()
    setDraft('')
    addMessage('user', text)
    setIsPending(true)
    try {
      const res = await sendMessage(text, sessionId)
      if (res.plan) {
        setPlan(res.plan)
      }
      if (res.awaiting_human_approval) {
        setAwaitingApproval(true, res.approval_action)
      }
      // Add the assistant message with streaming=true so MessageBubble
      // starts the typewriter reveal. appendStreamChunk pushes the full
      // text into the queue (mock: one chunk; real SSE: called per chunk).
      const msgId = addMessage('assistant', '', {
        streaming: true,
        citations: res.citations || [],
      })
      appendStreamChunk(msgId, res.reply)
      finishStreaming(msgId)
    } finally {
      setIsPending(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(CODE_SNIPPET)
      setCopiedCode(true)
      showToast('Code copied to clipboard', 'success')
      setTimeout(() => setCopiedCode(false), 2000)
    } catch (err) {
      console.error('Failed to copy code:', err)
      showToast('Could not copy code to clipboard', 'warning')
    }
  }

  const toggleCompletedStep = (id) => {
    setExpandedCompletedSteps((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  return (
    <div
      className="flex-1 flex flex-col overflow-hidden min-w-0 relative"
      style={{
        background: 'var(--color-bg)',
      }}
    >
      {/* ── 1. Chat Header: Title + Tab Row + Plan DAG Link + Options ──── */}
      <div
        className="flex items-center justify-between px-6 pt-3.5 pb-3 flex-shrink-0 select-none gap-4"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        {/* Left: Title + Tagline */}
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <h2
              className="text-base font-bold tracking-tight leading-tight"
              style={{ color: 'var(--color-text)' }}
            >
              Chat
            </h2>
            <span
              className="text-[11px] italic leading-tight mt-0.5"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Ask. Analyze. Act.
            </span>
          </div>

          {/* Segmented Control Tab Row (Chat / Notebooks / Artifacts) */}
          <div
            className="flex items-center p-0.5 rounded-md text-xs font-medium ml-2"
            style={{ background: 'var(--color-overlay)' }}
          >
            {[
              { id: 'chat', label: 'Chat', icon: Bot },
              { id: 'notebooks', label: 'Notebooks', icon: BookOpen },
              { id: 'artifacts', label: 'Artifacts', icon: FileCode },
            ].map((tab) => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => {
                    setActiveTab(tab.id)
                    if (tab.id !== 'chat') {
                      showToast(`${tab.label} module — Coming soon`, 'info')
                    }
                  }}
                  className="flex items-center gap-1.5 px-3 py-1 rounded text-xs transition-fast cursor-pointer"
                  style={{
                    background: isActive ? 'var(--color-surface)' : 'transparent',
                    color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                    fontWeight: isActive ? 600 : 500,
                    boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                  }}
                >
                  <tab.icon size={13} strokeWidth={2} />
                  <span>{tab.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Right Header Actions: Plan DAG Compact Progress Strip + Overflow Menu */}
        <div className="flex items-center gap-2">
          {(() => {
            const doneSteps = plan.filter((s) => s.status === 'done').length
            const runningStep = plan.find((s) => s.status === 'running')
            const currentStepNum = doneSteps + (runningStep ? 1 : 0)
            const totalSteps = plan.length || 5

            return (
              <Link
                to={`/plan/${sessionId}`}
                className="group flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-medium transition-fast hover:bg-[var(--color-surface-hover)] shadow-xs cursor-pointer select-none"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                }}
                title="Open full-screen Plan DAG execution graph (/plan)"
              >
                <div className="flex items-center gap-1.5" style={{ color: 'var(--color-accent)' }}>
                  <Network size={13} strokeWidth={2.2} className="group-hover:scale-110 transition-transform" />
                  <span className="text-[11px] font-semibold">Plan DAG</span>
                </div>

                <div className="w-[1px] h-3" style={{ background: 'var(--color-border)' }} />

                <span className="font-mono text-[10px] font-medium" style={{ color: 'var(--color-text)' }}>
                  Step {currentStepNum}/{totalSteps}
                </span>

                {/* Segmented Progress Ticks */}
                <div
                  className="flex items-center gap-1 w-12"
                  title={`Plan Progress: Step ${currentStepNum} of ${totalSteps} active`}
                >
                  {plan.map((step, idx) => {
                    const isDone = step.status === 'done'
                    const isRunning = step.status === 'running'
                    return (
                      <div
                        key={step.id || idx}
                        className="h-1 flex-1 rounded-xs transition-all relative overflow-hidden"
                        style={{
                          background: isDone
                            ? 'var(--color-success)'
                            : isRunning
                            ? 'var(--color-accent)'
                            : 'var(--color-border)',
                        }}
                      >
                        {isRunning && (
                          <div
                            className="absolute inset-0 opacity-60 animate-pulse"
                            style={{ background: 'white' }}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              </Link>
            )
          })()}

          <button
            type="button"
            onClick={() =>
              showToast(
                'Conversation session: Refinery Turnaround Analysis (Zero-Egress Sandbox)',
                'info'
              )
            }
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Chat options"
          >
            <MoreHorizontal size={16} strokeWidth={2} />
          </button>
        </div>
      </div>

      {/* ── 2. Active Tab Content ──────────────────────────────────────── */}
      {activeTab !== 'chat' ? (
        /* Non-functional Stub State for Notebooks / Artifacts */
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center animate-fade-in">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
            style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
          >
            {activeTab === 'notebooks' ? <BookOpen size={24} /> : <FileCode size={24} />}
          </div>
          <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
            {activeTab === 'notebooks' ? 'Interactive Notebooks' : 'Artifacts & Document Deliverables'}
          </h3>
          <p className="text-xs max-w-sm mt-1 mb-4 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
            {activeTab === 'notebooks'
              ? 'Jupyter-compatible interactive engineering notebooks with SymPy verified math are scheduled for Day 8.'
              : 'Generated DOCX approval notes, XLSX spreadsheets, and inspection overlays will be cataloged here once verification passes.'}
          </p>
          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className="px-4 py-1.5 rounded-xl text-xs font-semibold transition-fast cursor-pointer shadow-xs text-white"
            style={{ background: 'var(--color-accent)' }}
          >
            Return to Chat
          </button>
        </div>
      ) : (
        /* Primary Chat Message Stream with Inline Thinking */
        <div
          id="chat-messages-container"
          className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-6"
        >
          {/* ── TURN 1: User Query 1 ───────────────────────────────────── */}
          <div className="flex justify-end">
            <div
              className="rounded-md px-4 py-2.5 text-xs leading-relaxed max-w-[72%] shadow-xs"
              style={{
                background: 'var(--color-chat-bubble-user)',
                border: '1px solid var(--color-chat-bubble-user-border)',
                color: 'var(--color-text)',
              }}
            >
              <div>What are the key risks in increasing feed rate in the HCU beyond 110%?</div>
              <div
                className="flex items-center justify-end gap-1 mt-1 text-[10px]"
                style={{ color: 'var(--color-accent)' }}
              >
                <span>10:14 AM</span>
                <CheckCheck size={13} strokeWidth={2.2} />
              </div>
            </div>
          </div>

          {/* ── TURN 1: Assistant Response with Completed Thinking Block ── */}
          <div className="flex flex-col gap-3 max-w-[88%] text-xs leading-relaxed" style={{ color: 'var(--color-text)' }}>
            {/* Inline Thinking Block (FLUSH TEXT sitting directly in flow, no card/border container!) */}
            <div className="flex flex-col">
              {/* Summary Toggle Line (Flush inline text, no border, no background fill) */}
              <button
                type="button"
                onClick={() => setIsCompleted1Expanded(!isCompleted1Expanded)}
                className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
                style={{ background: 'transparent', border: 'none' }}
                title="Click to review reasoning process steps"
              >
                <div
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: 'var(--color-text-faint)' }}
                />
                <span className="font-medium" style={{ color: 'var(--color-text-muted)' }}>
                  {formatThinkingHeader(phraseMsg1, 4, '4.7s')}
                </span>
                <ChevronRight
                  size={12}
                  strokeWidth={2.2}
                  className="transition-transform duration-200 ml-0.5"
                  style={{
                    transform: isCompleted1Expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    color: 'var(--color-text-faint)',
                  }}
                />
              </button>

              {/* Stacked Step Lines (Flush inline text, no border container) */}
              <div className={`collapsible-grid ${isCompleted1Expanded ? 'is-expanded' : ''}`}>
                <div className="collapsible-inner">
                  <div
                    className="pl-3.5 my-1.5 flex flex-col gap-1.5"
                    style={{ borderLeft: '2px solid var(--color-border)' }}
                  >
                    {COMPLETED_REASONING_STEPS_1.map((step) => {
                      const isStepOpen = !!expandedCompletedSteps[step.id]
                      return (
                        <div key={step.id} id={step.id} data-tool-event-id={step.id} className="flex flex-col scroll-mt-12 transition-all rounded-xs">
                          <button
                            type="button"
                            onClick={() => toggleCompletedStep(step.id)}
                            className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
                            style={{ background: 'transparent', border: 'none' }}
                          >
                            <div
                              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                              style={{ background: 'var(--color-text-faint)' }}
                            />
                            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                              {step.label}
                            </span>
                            <span style={{ color: 'var(--color-text-faint)' }}>·</span>
                            <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-faint)' }}>
                              {step.duration}
                            </span>
                            <ChevronRight
                              size={11}
                              strokeWidth={2}
                              className="transition-transform duration-200 ml-0.5"
                              style={{
                                transform: isStepOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                                color: 'var(--color-text-faint)',
                              }}
                            />
                          </button>

                          {/* Recessed Monospace Trace Details (Indented flush text) */}
                          <div className={`collapsible-grid ${isStepOpen ? 'is-expanded' : ''}`}>
                            <div className="collapsible-inner">
                              <div
                                className="pl-3 my-1 font-mono text-[10px] leading-relaxed flex flex-col gap-1"
                                style={{ color: 'var(--color-text)' }}
                              >
                                {step.trace.map((item, i) => (
                                  <div key={i} className="flex items-start gap-1.5">
                                    <span className="opacity-60 flex-shrink-0">{item.time}</span>
                                    <span className="break-words flex-1">{item.text}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}

                    {/* Sources used — below pipeline steps, same indent/border */}
                    <SourcesUsedList citations={DEMO_CITATIONS} />
                  </div>
                </div>
              </div>
            </div>

            {/* Answer Text — plain, no inline citation markers */}
            <p className="leading-relaxed">
              Increasing the feed rate in the HCU beyond 110% can lead to several operational and safety
              risks, including reduced catalyst life, higher temperatures, and potential off-spec products.
            </p>

            {/* Bullet points */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold">Based on the operator manual:</span>
              <div className="flex flex-col gap-1 pl-2">
                <div>1. Elevated reactor temperatures and potential catalyst thermal runaway</div>
                <div>2. Increased H₂ consumption leading to makeup compressor capacity limits</div>
                <div>3. Higher chance of downstream fractionation column flooding</div>
              </div>
            </div>

            {/* Code Block — real syntax highlighting (§3.1) */}
            <div
              className="rounded-md overflow-hidden shadow-xs border flex flex-col"
              style={{ borderColor: 'var(--color-code-border)' }}
            >
              {/* Header bar: plain-text language + filename + action buttons */}
              <div
                className="flex items-center justify-between px-3.5 py-2 border-b text-xs select-none"
                style={{
                  borderColor: 'var(--color-code-border)',
                  background: 'var(--color-overlay)',
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs" style={{ color: 'var(--color-text-muted)' }}>python</span>
                  <span style={{ color: 'var(--color-text-faint)' }}>•</span>
                  <span className="font-mono text-xs font-medium" style={{ color: 'var(--color-text)' }}>feed_rate_guard.py</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => showToast('Sandboxed code execution — coming in Day 5', 'info')}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                    style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
                  >
                    <Play size={11} strokeWidth={2.2} style={{ color: 'var(--color-accent)' }} />
                    <span>Run</span>
                  </button>
                  <button
                    type="button"
                    onClick={copyToClipboard}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                    style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
                  >
                    {copiedCode ? (
                      <><Check size={11} strokeWidth={2.5} style={{ color: 'var(--color-success)' }} /><span style={{ color: 'var(--color-success)' }}>Copied!</span></>
                    ) : (
                      <><Copy size={11} strokeWidth={2} /><span>Copy</span></>
                    )}
                  </button>
                </div>
              </div>
              {/* Real syntax-highlighted Python code */}
              <SyntaxHighlighter
                language="python"
                style={document.documentElement.dataset.theme === 'dark' ? oneDark : oneLight}
                customStyle={{
                  margin: 0,
                  borderRadius: 0,
                  fontSize: '11px',
                  background: 'var(--color-code-bg)',
                  padding: '12px 14px',
                  lineHeight: 1.6,
                }}
                codeTagProps={{ style: { fontFamily: 'var(--font-mono)' } }}
              >
                {CODE_SNIPPET}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* ── TURN 2: User Query 2 ───────────────────────────────────── */}
          <div className="flex justify-end mt-1">
            <div
              className="rounded-md px-4 py-2.5 text-xs leading-relaxed max-w-[72%] shadow-xs"
              style={{
                background: 'var(--color-chat-bubble-user)',
                border: '1px solid var(--color-chat-bubble-user-border)',
                color: 'var(--color-text)',
              }}
            >
              <div>Can you check the latest trend data for reactor inlet temp and verify against plant limits?</div>
              <div
                className="flex items-center justify-end gap-1 mt-1 text-[10px]"
                style={{ color: 'var(--color-accent)' }}
              >
                <span>10:18 AM</span>
                <CheckCheck size={13} strokeWidth={2.2} />
              </div>
            </div>
          </div>

          {/* ── TURN 2: Assistant Response 2 with SECOND ROTATION WORD ─── */}
          <div className="flex flex-col gap-3 max-w-[88%] text-xs leading-relaxed" style={{ color: 'var(--color-text)' }}>
            {/* Second Completed Thinking Block (Showing distinct rotated phrase) */}
            <div className="flex flex-col">
              <button
                type="button"
                onClick={() => setIsCompleted2Expanded(!isCompleted2Expanded)}
                className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
                style={{ background: 'transparent', border: 'none' }}
                title="Click to review reasoning process steps"
              >
                <div
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: 'var(--color-text-faint)' }}
                />
                <span className="font-medium" style={{ color: 'var(--color-text-muted)' }}>
                  {formatThinkingHeader(phraseMsg2, 3, '1.9s')}
                </span>
                <ChevronRight
                  size={12}
                  strokeWidth={2.2}
                  className="transition-transform duration-200 ml-0.5"
                  style={{
                    transform: isCompleted2Expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    color: 'var(--color-text-faint)',
                  }}
                />
              </button>

              {/* Stacked Step Lines for Message 2 */}
              <div className={`collapsible-grid ${isCompleted2Expanded ? 'is-expanded' : ''}`}>
                <div className="collapsible-inner">
                  <div
                    className="pl-3.5 my-1.5 flex flex-col gap-1.5"
                    style={{ borderLeft: '2px solid var(--color-border)' }}
                  >
                    {COMPLETED_REASONING_STEPS_2.map((step) => {
                      const isStepOpen = !!expandedCompletedSteps[step.id]
                      return (
                        <div key={step.id} id={step.id} data-tool-event-id={step.id} className="flex flex-col scroll-mt-12 transition-all rounded-xs">
                          <button
                            type="button"
                            onClick={() => toggleCompletedStep(step.id)}
                            className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
                            style={{ background: 'transparent', border: 'none' }}
                          >
                            <div
                              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                              style={{ background: 'var(--color-text-faint)' }}
                            />
                            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                              {step.label}
                            </span>
                            <span style={{ color: 'var(--color-text-faint)' }}>·</span>
                            <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-faint)' }}>
                              {step.duration}
                            </span>
                            <ChevronRight
                              size={11}
                              strokeWidth={2}
                              className="transition-transform duration-200 ml-0.5"
                              style={{
                                transform: isStepOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                                color: 'var(--color-text-faint)',
                              }}
                            />
                          </button>

                          <div className={`collapsible-grid ${isStepOpen ? 'is-expanded' : ''}`}>
                            <div className="collapsible-inner">
                              <div
                                className="pl-3 my-1 font-mono text-[10px] leading-relaxed flex flex-col gap-1"
                                style={{ color: 'var(--color-text)' }}
                              >
                                {step.trace.map((item, i) => (
                                  <div key={i} className="flex items-start gap-1.5">
                                    <span className="opacity-60 flex-shrink-0">{item.time}</span>
                                    <span className="break-words flex-1">{item.text}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}

                    {/* Sources used — Turn 2 citations (sensor data) */}
                    <SourcesUsedList citations={[DEMO_CITATIONS[3]]} />
                  </div>
                </div>
              </div>
            </div>

            {/* Answer — plain text, no inline citation markers */}
            <p className="leading-relaxed">
              The current reactor inlet temperature is <span className="font-semibold">382°C</span>, safely
              within the normal operating range (360–400°C) with an 18°C safety margin.
            </p>

            {/* Markdown table demo — proves §3.1 table rendering works */}
            <div className="mt-1">
              <div
                className="text-[10px] font-semibold uppercase tracking-wide mb-1.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Thermocouple Array — Last 4 Shifts
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '11px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                  }}
                >
                  <thead>
                    <tr style={{ background: 'var(--color-surface)' }}>
                      {['Sensor', 'Reading (°C)', 'Limit (°C)', 'Status'].map((h) => (
                        <th
                          key={h}
                          style={{
                            padding: '5px 10px',
                            textAlign: 'left',
                            fontWeight: 600,
                            fontSize: '10px',
                            letterSpacing: '0.03em',
                            color: 'var(--color-text-muted)',
                            borderBottom: '1px solid var(--color-border)',
                            whiteSpace: 'nowrap',
                          }}
                        >{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['TC-201A', '381.4', '400', '✓ Normal'],
                      ['TC-201B', '382.1', '400', '✓ Normal'],
                      ['TC-201C', '383.0', '400', '✓ Normal'],
                      ['TC-201D', '380.9', '400', '✓ Normal'],
                      ['TC-201E', '382.6', '400', '✓ Normal'],
                      ['TC-201F', '381.7', '400', '✓ Normal'],
                    ].map((row, i) => (
                      <tr
                        key={i}
                        style={{ borderBottom: '1px solid var(--color-border)' }}
                      >
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            style={{
                              padding: '4px 10px',
                              color: j === 3 ? 'var(--color-success)' : 'var(--color-text)',
                              fontFamily: j === 0 ? 'var(--font-mono)' : 'inherit',
                              fontWeight: j === 0 ? 500 : 400,
                            }}
                          >{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ── TURN 3: User Query 3 (Actively being processed) ───────── */}
          <div className="flex justify-end mt-1">
            <div
              className="rounded-md px-4 py-2.5 text-xs leading-relaxed max-w-[72%] shadow-xs"
              style={{
                background: 'var(--color-chat-bubble-user)',
                border: '1px solid var(--color-chat-bubble-user-border)',
                color: 'var(--color-text)',
              }}
            >
              <div>Should we increase the quenching rate or adjust the column reflux to stabilize?</div>
              <div
                className="flex items-center justify-end gap-1 mt-1 text-[10px]"
                style={{ color: 'var(--color-accent)' }}
              >
                <span>10:20 AM</span>
                <CheckCheck size={13} strokeWidth={2.2} />
              </div>
            </div>
          </div>

          {/* ── TURN 3: Active Mid-Response Live-Thinking Block (FLUSH TEXT, NO CARD/BORDER) ── */}
          {isMidResponse && (
            <div className="max-w-[88%] flex flex-col">
              {/* Single Collapsed Line: Breathing Dot + Status Word + Live Elapsed Time (Flush inline text) */}
              <button
                type="button"
                onClick={() => setIsMidResponseExpanded(!isMidResponseExpanded)}
                className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
                style={{
                  background: 'transparent',
                  border: 'none',
                }}
                title={isMidResponseExpanded ? 'Click to collapse reasoning trace' : 'Click to expand reasoning trace'}
              >
                {/* Breathing dot */}
                <div className="relative flex items-center justify-center w-2 h-2 flex-shrink-0">
                  <span
                    className="w-2 h-2 rounded-full animate-breathing-dot"
                    style={{
                      background: 'var(--color-accent)',
                      color: 'var(--color-accent)',
                    }}
                  />
                </div>

                <span className="font-semibold text-xs leading-tight" style={{ color: 'var(--color-text)' }}>
                  Retrieving sources
                </span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-faint)' }}>·</span>
                <span className="font-mono text-[11px]" style={{ color: 'var(--color-accent)' }}>
                  {liveElapsed}s
                </span>

                <ChevronRight
                  size={13}
                  strokeWidth={2.2}
                  className="transition-transform duration-200 ml-0.5 flex-shrink-0"
                  style={{
                    transform: isMidResponseExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    color: 'var(--color-text-muted)',
                  }}
                />
              </button>

              {/* Inline Recessed Monospace Trace (Flush indented guide line, no box card) */}
              <div className={`collapsible-grid ${isMidResponseExpanded ? 'is-expanded' : ''}`}>
                <div className="collapsible-inner">
                  <div
                    className="pl-3.5 my-1.5 font-mono text-[11px] leading-relaxed flex flex-col gap-1.5"
                    style={{
                      borderLeft: '2px solid var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                  >
                    {ACTIVE_TRACE_ITEMS.map((item, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span
                          className="text-[9px] opacity-60 flex-shrink-0 select-none mt-0.5"
                          style={{ color: 'var(--color-text-muted)' }}
                        >
                          {item.time}
                        </span>
                        <span className="break-words flex-1" style={{ color: 'var(--color-text)' }}>
                          {item.text}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* In mid-response, the reply text is NOT rendered yet per prompt spec */}
            </div>
          )}

          {/* Dynamic Messages — streaming typewriter + markdown + citation chips */}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>
      )}

      {/* ── 3. Chat Composer Docked Above Status Strip ──────────────────── */}
      <div
        className="px-6 py-3 flex-shrink-0"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        {/* Safety Gate Locked Banner when approval is pending (§3.12 / FR-15) */}
        {awaitingHumanApproval && (
          <div
            id="composer-approval-locked-banner"
            className="mb-2.5 px-3 py-2 rounded-md flex items-center justify-between gap-3 text-xs animate-fade-in border"
            style={{
              background: 'var(--color-error-tint)',
              borderColor: 'var(--color-accent-border)',
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <ShieldAlert
                size={16}
                strokeWidth={2.2}
                className="flex-shrink-0"
                style={{ color: 'var(--color-accent)' }}
              />
              <span
                className="font-medium truncate text-xs"
                style={{ color: 'var(--color-text)' }}
              >
                <strong className="font-semibold">Safety Gate Active:</strong> Critical setpoint change awaiting operator authorization.
              </span>
            </div>
            <button
              type="button"
              id="review-approval-gate-btn"
              onClick={openApprovalModal}
              className="px-2.5 py-1 rounded text-[11px] font-bold text-white transition-fast cursor-pointer hover:brightness-110 flex-shrink-0 shadow-xs"
              style={{ background: 'var(--color-accent)' }}
            >
              Review Gate
            </button>
          </div>
        )}

        <div
          className="flex items-center gap-2 px-3.5 py-2.5 rounded-md transition-fast"
          style={{
            background: 'var(--color-input-bg)',
            border: awaitingHumanApproval
              ? '1px dashed var(--color-accent)'
              : '1px solid var(--color-input-border)',
            boxShadow: 'var(--shadow-xs)',
            opacity: awaitingHumanApproval ? 0.75 : 1,
          }}
        >
          {/* Left buttons: Paperclip + Globe */}
          <button
            type="button"
            disabled={awaitingHumanApproval}
            onClick={() => showToast('Multimodal upload ready — Drop PDFs, scans, or voice notes here', 'info')}
            className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
              awaitingHumanApproval
                ? 'cursor-not-allowed opacity-40'
                : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
            }`}
            style={{ color: 'var(--color-text-muted)' }}
            title="Attach document or audio"
          >
            <Paperclip size={15} strokeWidth={2} />
          </button>
          <button
            type="button"
            disabled={awaitingHumanApproval}
            onClick={() => showToast('Grounded in 8 local sources — Zero outbound network egress', 'success')}
            className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
              awaitingHumanApproval
                ? 'cursor-not-allowed opacity-40'
                : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
            }`}
            style={{ color: 'var(--color-text-muted)' }}
            title="Grounding scope"
          >
            <Globe size={15} strokeWidth={2} />
          </button>

          {/* Input field */}
          <input
            type="text"
            id="chat-composer-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              awaitingHumanApproval
                ? 'Composer locked: Human authorization required at approval gate...'
                : 'Ask a follow-up or command an agentic task...'
            }
            className={`flex-1 bg-transparent text-xs outline-none placeholder:text-[var(--color-text-faint)] ${
              awaitingHumanApproval ? 'cursor-not-allowed text-[var(--color-text-muted)]' : ''
            }`}
            style={{ color: 'var(--color-text)' }}
            disabled={isPending || awaitingHumanApproval}
          />

          {/* Model Selector Dropdown (Cosmetic only per SYSTEM.md) */}
          <div className="relative">
            <button
              type="button"
              disabled={awaitingHumanApproval}
              onClick={() => !awaitingHumanApproval && setModelDropdownOpen(!modelDropdownOpen)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-fast select-none ${
                awaitingHumanApproval ? 'cursor-not-allowed opacity-40' : 'cursor-pointer'
              }`}
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text)',
              }}
              title="Model registry profile (cosmetic selector)"
            >
              <Sparkles size={11} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
              <span className="truncate max-w-[130px]">{selectedModel}</span>
              <ChevronRight size={11} strokeWidth={2} className="rotate-90" style={{ color: 'var(--color-text-muted)' }} />
            </button>

            {modelDropdownOpen && (
              <div
                className="absolute right-0 bottom-full mb-1.5 w-56 rounded-xl py-1.5 z-50 animate-fade-in shadow-lg border"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                <div
                  className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: 'var(--color-text-faint)' }}
                >
                  Active Model Registry
                </div>
                {MODELS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => {
                      setSelectedModel(m)
                      setModelDropdownOpen(false)
                      showToast(`Switched model profile to: ${m}`, 'info')
                    }}
                    className="w-full px-3 py-1.5 text-left text-xs flex items-center justify-between transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
                    style={{ color: selectedModel === m ? 'var(--color-accent)' : 'var(--color-text)' }}
                  >
                    <span>{m}</span>
                    {selectedModel === m && <Check size={12} strokeWidth={2.5} />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Send Button */}
          <button
            type="button"
            id="chat-composer-send-btn"
            onClick={handleSend}
            disabled={!draft.trim() || isPending || awaitingHumanApproval}
            className={`w-8 h-8 rounded-md flex items-center justify-center text-white transition-fast shadow-xs flex-shrink-0 ${
              awaitingHumanApproval || !draft.trim() ? 'cursor-not-allowed opacity-40' : 'cursor-pointer'
            }`}
            style={{
              background: 'var(--color-accent)',
            }}
            title={awaitingHumanApproval ? 'Composer locked until approval is resolved' : 'Send message'}
          >
            <Send size={14} strokeWidth={2} />
          </button>
        </div>
      </div>

      {/* ── 4. Persistent Bottom System / Network Monitor Bar (§3.9) ───── */}
      <NetworkMonitorBar />
    </div>
  )
}
