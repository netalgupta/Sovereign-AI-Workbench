import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  MoreHorizontal,
  Paperclip,
  Globe,
  Send,
  ChevronRight,
  CheckCheck,
  Play,
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
} from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { sendMessage } from '../../lib/api'
import { showToast } from '../../store/toastStore'

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

export function ChatPane() {
  const messages = useChatStore((s) => s.messages)
  const addMessage = useChatStore((s) => s.addMessage)
  const sessionId = useChatStore((s) => s.sessionId)
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

  // Live timer for active mid-response thinking
  useEffect(() => {
    const timer = setInterval(() => {
      setLiveElapsed((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Expose test automation hooks
  useEffect(() => {
    window.__workbenchSetThinkingMidResponse = (active) => setIsMidResponse(active)
    window.__workbenchSetThinkingExpanded = (expanded) => setIsMidResponseExpanded(expanded)
    window.__workbenchSetCompletedPhrases = (p1, p2) => {
      if (p1) setPhraseMsg1(p1)
      if (p2) setPhraseMsg2(p2)
    }
    return () => {
      delete window.__workbenchSetThinkingMidResponse
      delete window.__workbenchSetThinkingExpanded
      delete window.__workbenchSetCompletedPhrases
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
    if (!draft.trim() || isPending) return
    const text = draft.trim()
    setDraft('')
    addMessage('user', text)
    setIsPending(true)
    try {
      const res = await sendMessage(text, sessionId)
      addMessage('assistant', res.reply)
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

        {/* Right Header Actions: Plan DAG Jump Link + Overflow Menu */}
        <div className="flex items-center gap-2">
          {/* Subtle jump link to full-screen Plan DAG per §3.4 */}
          <Link
            to="/plan/session-1"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-fast hover:bg-[var(--color-surface-hover)] shadow-xs cursor-pointer"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-accent)',
            }}
            title="Open full-screen Plan DAG execution graph (/plan)"
          >
            <Network size={13} strokeWidth={2.2} />
            <span className="text-[11px] font-semibold">Plan DAG</span>
          </Link>

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
                    style={{
                      borderLeft: '2px solid var(--color-border)',
                    }}
                  >
                    {COMPLETED_REASONING_STEPS_1.map((step) => {
                      const isStepOpen = !!expandedCompletedSteps[step.id]
                      return (
                        <div key={step.id} className="flex flex-col">
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
                  </div>
                </div>
              </div>
            </div>

            {/* Answer Text */}
            <p>
              Increasing the feed rate in the HCU beyond 110% can lead to several operational and safety risks,
              including reduced catalyst life, higher temperatures, and potential off-spec products.{' '}
              <span className="inline-flex gap-1 ml-1 select-none">
                <span
                  className="px-1.5 py-0.2 rounded border text-[10px] font-mono cursor-pointer transition-fast hover:border-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onClick={() => showToast('Citation 1: HCU_Operations_Manual.pdf, Section 4.2', 'info')}
                >
                  1
                </span>
                <span
                  className="px-1.5 py-0.2 rounded border text-[10px] font-mono cursor-pointer transition-fast hover:border-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onClick={() => showToast('Citation 2: Safety_Guidelines_2024.docx, Page 14', 'info')}
                >
                  2
                </span>
                <span
                  className="px-1.5 py-0.2 rounded border text-[10px] font-mono cursor-pointer transition-fast hover:border-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text)',
                  }}
                  onClick={() => showToast('Citation 3: Emissions_Regulations.pdf, Section 9', 'info')}
                >
                  3
                </span>
              </span>
              .
            </p>

            {/* Bullet points based on manual */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold">Based on the operator manual:</span>
              <div className="flex flex-col gap-1 pl-2">
                <div>1. Elevated reactor temperatures and potential catalyst thermal runaway</div>
                <div>2. Increased H₂ consumption leading to makeup compressor capacity limits</div>
                <div>3. Higher chance of downstream fractionation column flooding</div>
              </div>
            </div>

            {/* Code Block with QUIET, PLAIN-TEXT "python" label (Fix §2: No pill, no orange badge) */}
            <div
              className="rounded-md overflow-hidden shadow-xs border flex flex-col"
              style={{
                background: 'var(--color-code-bg)',
                borderColor: 'var(--color-code-border)',
              }}
            >
              <div
                className="flex items-center justify-between px-3.5 py-2 border-b text-xs select-none"
                style={{
                  borderColor: 'var(--color-code-border)',
                  background: 'var(--color-overlay)',
                }}
              >
                {/* Plain-text language label sitting quietly next to filename */}
                <div className="flex items-center gap-2 text-xs">
                  <span
                    className="font-mono text-xs"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    python
                  </span>
                  <span style={{ color: 'var(--color-text-faint)' }}>•</span>
                  <span
                    className="font-mono text-xs font-medium"
                    style={{ color: 'var(--color-text)' }}
                  >
                    feed_rate_guard.py
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => showToast('Sandboxed code execution — coming in Day 3-4', 'info')}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                  >
                    <Play size={11} strokeWidth={2.2} style={{ color: 'var(--color-accent)' }} />
                    <span>Run</span>
                  </button>

                  <button
                    type="button"
                    onClick={copyToClipboard}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                  >
                    {copiedCode ? (
                      <>
                        <Check size={11} strokeWidth={2.5} style={{ color: 'var(--color-success)' }} />
                        <span style={{ color: 'var(--color-success)' }}>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={11} strokeWidth={2} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div
                className="p-3.5 font-mono text-xs overflow-x-auto leading-relaxed"
                style={{ color: 'var(--color-text)' }}
              >
                <div className="flex gap-4">
                  <span className="opacity-40 select-none text-right w-3">1</span>
                  <span>if feed_rate &gt; 1.10 * design_capacity:</span>
                </div>
                <div className="flex gap-4">
                  <span className="opacity-40 select-none text-right w-3">2</span>
                  <span className="pl-4">alert("High risk: exceeds design threshold")</span>
                </div>
                <div className="flex gap-4">
                  <span className="opacity-40 select-none text-right w-3">3</span>
                  <span className="pl-4">suggest_mitigation(cool_quench=True)</span>
                </div>
              </div>
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
                    style={{
                      borderLeft: '2px solid var(--color-border)',
                    }}
                  >
                    {COMPLETED_REASONING_STEPS_2.map((step) => {
                      const isStepOpen = !!expandedCompletedSteps[step.id]
                      return (
                        <div key={step.id} className="flex flex-col">
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
                  </div>
                </div>
              </div>
            </div>

            <p>
              The current reactor inlet temperature is <span className="font-semibold">382°C</span>, which is safely
              within the normal operating range (360–400°C) with an 18°C safety margin.{' '}
              <span
                className="inline-flex px-1.5 py-0.2 rounded border text-[10px] font-mono select-none cursor-pointer hover:border-[var(--color-accent)]"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }}
                onClick={() => showToast('Citation 4: Historical_Trend_Data.csv, Row 1042', 'info')}
              >
                4
              </span>
              .
            </p>
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

          {/* Dynamic Messages sent by user during live conversation */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className="rounded-md px-4 py-2.5 text-xs leading-relaxed max-w-[76%] shadow-xs"
                style={{
                  background:
                    m.role === 'user'
                      ? 'var(--color-chat-bubble-user)'
                      : 'var(--color-chat-bubble-asst)',
                  border:
                    m.role === 'user'
                      ? '1px solid var(--color-chat-bubble-user-border)'
                      : '1px solid var(--color-chat-bubble-asst-border)',
                  color: 'var(--color-text)',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 3. Chat Composer Docked Above Status Strip ──────────────────── */}
      <div
        className="px-6 py-3 flex-shrink-0"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        <div
          className="flex items-center gap-2 px-3.5 py-2.5 rounded-md transition-fast"
          style={{
            background: 'var(--color-input-bg)',
            border: '1px solid var(--color-input-border)',
            boxShadow: 'var(--shadow-xs)',
          }}
        >
          {/* Left buttons: Paperclip + Globe */}
          <button
            type="button"
            onClick={() => showToast('Multimodal upload ready — Drop PDFs, scans, or voice notes here', 'info')}
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Attach document or audio"
          >
            <Paperclip size={15} strokeWidth={2} />
          </button>
          <button
            type="button"
            onClick={() => showToast('Grounded in 8 local sources — Zero outbound network egress', 'success')}
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Grounding scope"
          >
            <Globe size={15} strokeWidth={2} />
          </button>

          {/* Input field */}
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a follow-up or command an agentic task..."
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-[var(--color-text-faint)]"
            style={{ color: 'var(--color-text)' }}
            disabled={isPending}
          />

          {/* Model Selector Dropdown (Cosmetic only per SYSTEM.md) */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-fast cursor-pointer select-none"
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
            onClick={handleSend}
            disabled={!draft.trim() || isPending}
            className="w-8 h-8 rounded-md flex items-center justify-center text-white transition-fast shadow-xs cursor-pointer flex-shrink-0"
            style={{
              background: 'var(--color-accent)',
              opacity: draft.trim() ? 1 : 0.75,
            }}
            title="Send message"
          >
            <Send size={14} strokeWidth={2} />
          </button>
        </div>
      </div>

      {/* ── 4. Persistent System Monitor Footer Strip ─────────────────── */}
      <div
        className="px-6 py-1.5 flex-shrink-0 flex items-center justify-between text-[11px] select-none"
        style={{
          background: 'var(--color-surface)',
          borderTop: '1px solid var(--color-border)',
        }}
      >
        {/* Left: System Status Pill */}
        <div className="flex items-center gap-2">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: 'var(--color-success)' }}
          />
          <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>
            Air-gapped Sandbox Active
          </span>
          <span style={{ color: 'var(--color-text-faint)' }}>·</span>
          <span style={{ color: 'var(--color-success)' }} className="font-medium">
            Zero Egress Verified
          </span>
        </div>

        {/* Right: Three Small Telemetry Metrics + Signal Bars */}
        <div className="flex items-center gap-4 text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
          <div className="flex items-center gap-1">
            <span className="opacity-70">CPU:</span>
            <span className="font-semibold" style={{ color: 'var(--color-text)' }}>14%</span>
          </div>

          <div className="flex items-center gap-1">
            <span className="opacity-70">MEM:</span>
            <span className="font-semibold" style={{ color: 'var(--color-text)' }}>3.8 GB</span>
          </div>

          <div className="flex items-center gap-1">
            <span className="opacity-70">NET:</span>
            <span className="font-semibold" style={{ color: 'var(--color-success)' }}>0.0 MB/s</span>
          </div>

          {/* 4 Stair-step Signal Bars */}
          <div className="flex items-end gap-[2px] h-3 ml-1" title="Signal: 0 external sockets (Air-gap secure)">
            <span className="w-[2.5px] h-1 rounded-xs" style={{ background: 'var(--color-success)' }} />
            <span className="w-[2.5px] h-1.5 rounded-xs" style={{ background: 'var(--color-success)' }} />
            <span className="w-[2.5px] h-2 rounded-xs" style={{ background: 'var(--color-success)' }} />
            <span className="w-[2.5px] h-2.5 rounded-xs" style={{ background: 'var(--color-success)' }} />
          </div>
        </div>
      </div>
    </div>
  )
}
