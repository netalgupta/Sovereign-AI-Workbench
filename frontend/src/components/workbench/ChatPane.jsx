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
  MessageSquare,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from '../../store/chatStore'
import { sendMessage } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { NetworkMonitorBar } from '../../integrations/network-monitor'
import { CalcTraceCard } from '../../integrations/calc-trace'

// Set of 12 phrases for completed thinking block word rotation

/**
 * Format rotation phrase with pipeline steps count and timing.
 * Formats grammatically without redundant "through" or awkward doubling.
 */

// Inline live-thinking trace data definitions
// Inline live-thinking trace data definitions



// Mock citation data for the STATIC demo turns (pre-loaded session)
// Grounded in actual MRPL_RAG_Test_Corpus documents

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

  // Model selector state (Cosmetic selector pointing to real models.yaml entries)
  // Kept for the trigger label only; routing is per-task, so there is no
  // "selected" model to send anywhere.
  const [selectedModel, setSelectedModel] = useState('Model registry')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)

  // ── Inline Live-Thinking State ───────────────────────────────────────────
  //
  // isMidResponse used to be useState(TRUE) with a timer seeded at 8 and
  // incremented forever. So every session opened already showing
  // "Retrieving sources - 21s", climbing, with no request behind it and
  // no way for it to finish. It was not reporting anything; it was an
  // animation. That is worse than no indicator, because it makes a real
  // in-flight request indistinguishable from idle.
  //
  // Now derived from isPending -- an actual /api/chat call in flight --
  // and the elapsed counter starts at 0 when that call starts.
  const [isMidResponseExpanded, setIsMidResponseExpanded] = useState(false)
  const [liveElapsed, setLiveElapsed] = useState(0)

  // 2. Completed message thinking blocks expansion state
  const [expandedCompletedSteps, setExpandedCompletedSteps] = useState({})

  // ── Node Click -> Scroll & Expand Tool Event Trace ───────────────────────
  useEffect(() => {
    const targetId = searchParams.get('scrollTo')
    if (!targetId) return

    const timer = setTimeout(() => {
      // (The two fixed COMPLETED_REASONING_STEPS arrays these checked
      // against described the deleted demo turns. Real steps arrive on
      // the message itself, and expandedCompletedSteps below still
      // opens whichever step id was linked to.)

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

  // Live timer, running ONLY while a request is genuinely in flight.
  // Previously this interval ran unconditionally for the lifetime of the
  // component, which is what made the counter climb on an idle screen.
  useEffect(() => {
    if (!isPending) return
    setLiveElapsed(0)
    const timer = setInterval(() => setLiveElapsed((prev) => prev + 1), 1000)
    return () => clearInterval(timer)
  }, [isPending])

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
    // __workbenchSetThinkingMidResponse is gone: the live indicator is
    // now derived from a real in-flight request, so there is no flag to
    // set. A test that could switch it on without a request was only
    // ever testing the animation.
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

  // The registry as it ACTUALLY IS, fetched from /api/models.
  //
  // This was four hardcoded display strings. Three problems:
  //
  //   1. They were decorative. Selecting one called showToast("Switched
  //      model profile to: ...") and changed nothing -- sendMessage()
  //      takes no model argument, because routing is per-task
  //      (AGENTS_SPEC §3), not per-chat. The control asserted a
  //      capability the system does not have and never acted on.
  //
  //   2. They listed models that are not pulled. "Qwen 2.5-Coder (7B
  //      Local)" is not on this machine, and "Phi-3.5 Mini" pointed at
  //      a models.yaml entry whose tag did not exist on Ollama at all.
  //      The picker was the last place anyone would look for that, and
  //      it displayed both as available.
  //
  //   3. Hardcoding model names in the UI is what CLAUDE.md constraint
  //      #2 exists to prevent: only models.yaml names a model. Adding a
  //      model to the registry should not require editing a component.
  //
  // It is now a registry VIEW, not a switcher: it shows which models the
  // task router can reach and which are missing, with the pull command.
  const [models, setModels] = useState([])
  const [modelsError, setModelsError] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/models')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (cancelled) return
        setModels(d.models || [])
        setModelsError(d.ollama_reachable ? null : d.ollama_error || 'Ollama unreachable')
      })
      .catch((e) => !cancelled && setModelsError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

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
      // Carry the REAL execution trace onto the message so the
      // thinking-block UI has something true to render. These components
      // are genuinely useful -- the problem was never the rendering, it
      // was that they were fed literals baked into the JSX.
      const msgId = addMessage('assistant', '', {
        streaming: true,
        citations: res.citations || [],
        toolCallEvents: res.tool_call_events || [],
        plan: res.plan || [],
        verification: res.verification || null,
        elapsedSeconds: liveElapsed,
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
          {/* THE THREE HARDCODED DEMO TURNS WERE DELETED HERE.
              ~480 lines of JSX that rendered on every single visit,
              before and regardless of any real conversation:

                - a user asking about reactor inlet temperature
                - an answer stating "The current reactor inlet
                  temperature is 382 C, safely within the normal
                  operating range (360-400 C) with an 18 C safety
                  margin"
                - a six-row THERMOCOUPLE ARRAY table (TC-201A..F, each
                  with a reading, a 400 C limit and a green "Normal")
                - a second user turn asking about quenching rate
                - and TURN 3: a "Retrieving sources" spinner with a
                  live-counting elapsed timer that resolved to nothing,
                  ever, because there was no request behind it

              None of it was data. The temperatures, the sensor tags,
              the limits and the green Normal statuses were literals in
              this file. On a refinery workbench that is six fabricated
              instrument readings and a safety verdict on them,
              rendered in the product's own voice, in the chat
              transcript, indistinguishable from a real answer -- and
              it was the first thing anyone saw.

              The spinner was its own problem: a permanent "Retrieving
              sources - 21s" with no request behind it, which is why
              every session appeared to be mid-work at the moment it
              opened, and why a real reply looked like just another one
              of these.

              Demo scaffolding renders in a demo. This renders in the
              product. */}

          {messages.length === 0 && !isPending && (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-12 animate-fade-in">
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
                style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
              >
                <MessageSquare size={22} />
              </div>
              <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Ask about your sources
              </h3>
              <p
                className="text-xs max-w-md mt-1.5 leading-relaxed"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Answers are grounded in the documents listed under Sources, with a
                citation for each claim. If nothing in the corpus supports an
                answer, this will say so rather than guess.
              </p>
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
                {modelsError && (
                  <div
                    className="px-3 py-1.5 text-[10px] leading-snug"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    Could not read the registry: {modelsError}
                  </div>
                )}
                {!modelsError && models.length === 0 && (
                  <div
                    className="px-3 py-1.5 text-[10px]"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    Loading registry…
                  </div>
                )}
                {models.map((m) => {
                  const ready = m.status === 'available'
                  return (
                    <div
                      key={m.id}
                      className="w-full px-3 py-1.5 text-xs flex items-center justify-between gap-2"
                      title={m.detail || `${m.model} — ${m.task_tags.join(', ')}`}
                    >
                      <div className="flex flex-col min-w-0">
                        <span
                          className="truncate"
                          style={{ color: ready ? 'var(--color-text)' : 'var(--color-text-faint)' }}
                        >
                          {m.id}
                        </span>
                        <span
                          className="truncate text-[10px]"
                          style={{ color: 'var(--color-text-muted)' }}
                        >
                          {m.model}
                          {m.size_display ? ` · ${m.size_display}` : ''}
                        </span>
                      </div>
                      {ready ? (
                        <Check size={12} strokeWidth={2.5} style={{ color: 'var(--color-accent)' }} />
                      ) : (
                        <span
                          className="text-[9px] uppercase tracking-wide whitespace-nowrap"
                          style={{ color: 'var(--color-text-faint)' }}
                        >
                          not pulled
                        </span>
                      )}
                    </div>
                  )
                })}
                <div
                  className="px-3 pt-1.5 pb-1 mt-1 text-[9px] leading-snug"
                  style={{ color: 'var(--color-text-faint)', borderTop: '1px solid var(--color-border)' }}
                >
                  Routing is per task, not per chat — the orchestrator picks
                  the model for each step.
                </div>
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
