import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  MoreHorizontal,
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
import { sendMessageStream, uploadFilesToCorpus, analyseAttachment } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { NetworkMonitorBar } from '../../integrations/network-monitor'
import { MultimodalUpload } from '../../integrations/multimodal-upload'
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
  const updateMessage = useChatStore((s) => s.updateMessage)
  const addToolCallEvent = useChatStore((s) => s.addToolCallEvent)
  const appendStreamChunk = useChatStore((s) => s.appendStreamChunk)
  const finishStreaming = useChatStore((s) => s.finishStreaming)
  const sessionId = useChatStore((s) => s.sessionId)
  const plan = useChatStore((s) => s.plan) || []
  const setPlan = useChatStore((s) => s.setPlan)
  const updatePlanStepStatus = useChatStore((s) => s.updatePlanStepStatus)
  const activeDocuments = useChatStore((s) => s.activeDocuments)
  const awaitingHumanApproval = useChatStore((s) => s.awaitingHumanApproval)
  const setAwaitingApproval = useChatStore((s) => s.setAwaitingApproval)
  const openApprovalModal = useChatStore((s) => s.openApprovalModal)
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState('')
  const [isPending, setIsPending] = useState(false)

  // Files queued via the MultimodalUpload integration (§3.13). Each item's
  // status/progress is driven ONLY by the real upload/OCR steps below.
  const [attachments, setAttachments] = useState([])

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
    window.__workbenchSetCompletedPhrases = () => {}
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
    const text = draft.trim()
    const hasAttachments = attachments.length > 0
    if ((!text && !hasAttachments) || isPending || awaitingHumanApproval) return
    setDraft('')

    // ── Attachment pipeline before sending (real upload + OCR/vision) ──
    // Uploads write the file into the corpus (so grounded answers can cite
    // it), then images/audio run through the registered vision tools. Every
    // tool event below carries genuine backend output; a failure becomes a
    // visible 'failed' event instead of a silent pretend success.
    let pipelineEvents = []
    if (hasAttachments) {
      setAttachments((prev) => prev.map((a) => ({ ...a, status: 'uploading', progress: 10 })))

      const saved = new Map()
      try {
        const up = await uploadFilesToCorpus(attachments)
        ;(up.saved || []).forEach((s) => {
          const p = s.path || s.fullPath || ''
          if (p) saved.set(s.name, p)
        })
        pipelineEvents.push({
          tool_name: 'source_ingest',
          status: 'done',
          output: {
            count: up.count,
            total_chunks: up.total_chunks,
            message: up.message || '',
          },
        })
      } catch (err) {
        pipelineEvents.push({
          tool_name: 'source_ingest',
          status: 'failed',
          error: String(err?.message || err).slice(0, 240),
        })
      }

      const toolFor = (name) => {
        const ext = (name || '').toLowerCase().split('.').pop()
        if (['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'webp'].includes(ext)) return 'extract_printed_text'
        if (['wav', 'mp3', 'm4a', 'ogg', 'flac'].includes(ext)) return 'transcribe_voice_note'
        return 'source_ingest'
      }

      for (const a of attachments) {
        const path = saved.get(a.name)
        if (!path) {
          setAttachments((prev) => prev.map((i) => (i.id === a.id ? { ...i, status: 'error' } : i)))
          continue
        }
        setAttachments((prev) => prev.map((i) => (i.id === a.id ? { ...i, status: 'processing' } : i)))
        try {
          const tool = toolFor(a.name)
          if (tool === 'source_ingest') {
            setAttachments((prev) => prev.map((i) => (i.id === a.id ? { ...i, status: 'ready', progress: 100 } : i)))
            continue
          }
          const result = await analyseAttachment(a, path)
          if (result) {
            pipelineEvents.push({
              tool_name: tool,
              status: 'done',
              output: result.full_text !== undefined ? { full_text: String(result.full_text).slice(0, 6000) } : result,
            })
          }
          setAttachments((prev) => prev.map((i) => (i.id === a.id ? { ...i, status: 'ready', progress: 100 } : i)))
        } catch (err) {
          setAttachments((prev) => prev.map((i) => (i.id === a.id ? { ...i, status: 'error' } : i)))
          pipelineEvents.push({
            tool_name: toolFor(a.name),
            status: 'failed',
            error: String(err?.message || err).slice(0, 240),
          })
        }
      }
    }

    const names = attachments.map((a) => a.name)
    const userText = hasAttachments && !text ? `Analyse the attached file${names.length > 1 ? 's' : ''}: ${names.join(', ')}` : text
    const attachNote =
      hasAttachments && text ? `\n\n_Attached: ${names.join(', ')}_` : ''
    addMessage('user', userText + attachNote)

    setIsPending(true)

    // Add the assistant message immediately with streaming=true so MessageBubble
    // starts typewriter draining as real SSE chunks arrive, and TurnTrace shows
    // in-flight agent activity live as it happens.
    const startTime = Date.now()
    const msgId = addMessage('assistant', '', {
      streaming: true,
      // The attachment pipeline above ran BEFORE the stream: upload into the
      // corpus, then OCR/vision per file. Seed its events into the trace so
      // the thinking-block renders what actually happened to the attachments
      // rather than nothing.
      citations: [],
      toolCallEvents: [...pipelineEvents],
      userRequest: userText,
      plan: [],
      verification: null,
      route: null,
      elapsedSeconds: 0,
    })

    try {
      await sendMessageStream(userText, sessionId, {
        onPlan: (planEv) => {
          // Receive the plan DAG emitted before any tool work starts.
          // Normalise the step_id field (backend uses step_id, not id).
          const steps = (planEv.steps || []).map((s) => ({
            ...s,
            id: s.step_id || s.id,
            step_id: s.step_id || s.id,
          }))
          setPlan(steps)
          updateMessage(msgId, { plan: steps, planPath: planEv.path || '' })
        },
        onMemory: (memEv) => {
          // What the system remembered, attached to the turn it shaped.
          // Memory changes what gets RETRIEVED -- a follow-up is
          // rewritten, focus documents steer the search -- and none of
          // that was visible. An answer that differs because of
          // something remembered two turns ago, with no sign that
          // anything was remembered, reads as the system being
          // inconsistent.
          updateMessage(msgId, { memory: memEv })
        },
        onRoute: (routeEv) => {
          updateMessage(msgId, { route: routeEv })
        },
        onToolCall: (call) => {
          // Mark the plan step for this tool as running when the call starts.
          // We match by tool name → assigned_agent heuristic: any step
          // whose step_id contains the tool name prefix, or the first pending
          // step if we cannot match exactly.
          updatePlanStepStatus(
            call.id?.split('-')[0] || call.name,
            'running'
          )
          addToolCallEvent(msgId, {
            id: call.id,
            name: call.name,
            tool_name: call.name,
            arguments: call.arguments,
            input_params: call.arguments,
            status: 'running',
          })
        },
        onToolResult: (resEv) => {
          // Mark the corresponding plan step done or failed.
          updatePlanStepStatus(
            resEv.id?.split('-')[0] || resEv.name,
            resEv.status === 'failed' ? 'failed' : 'done'
          )
          addToolCallEvent(msgId, {
            id: resEv.id,
            name: resEv.name,
            tool_name: resEv.name,
            output: resEv.output,
            status: resEv.status || 'done',
            seconds: resEv.seconds,
          })
        },
        onTextDelta: (delta) => {
          appendStreamChunk(msgId, delta)
        },
        onApprovalRequired: (appEv) => {
          const actionPayload = appEv.action || {
            id: appEv.id,
            title: 'Confirm Critical Parameter Modification',
            action_type: appEv.name || 'DCS_SETPOINT_WRITE',
            description: appEv.effect || 'Critical parameter change intercepted',
            arguments: appEv.arguments,
            target: appEv.arguments?.target || appEv.name,
            proposed_value: appEv.arguments ? JSON.stringify(appEv.arguments) : '',
          }
          setAwaitingApproval(true, actionPayload)
        },
        onDone: (doneEv) => {
          const normCitations = (doneEv.citations || []).map((c, idx) => ({
            id: c.id ?? idx + 1,
            doc: c.doc || c.source_document || c.document_name || 'Document',
            section: c.section || (c.page_number ? `p. ${c.page_number}` : ''),
            passage: c.passage || c.text || c.excerpt || '',
            score: c.score,
            page_number: c.page_number,
            source_document: c.source_document || c.doc,
          }))

          if (doneEv.plan && doneEv.plan.length > 0) {
            setPlan(doneEv.plan)
          }

          updateMessage(msgId, {
            citations: normCitations,
            plan: doneEv.plan || [],
            verification: doneEv.verification || null,
            elapsedSeconds:
              doneEv.seconds ??
              Number(((Date.now() - startTime) / 1000).toFixed(1)),
          })

          // Ensure any tail reply content is synchronized
          if (doneEv.reply) {
            const cur = useChatStore.getState().messages.find((m) => m.id === msgId)
            if (!cur || !cur.content || cur.content.length < doneEv.reply.length) {
              appendStreamChunk(msgId, doneEv.reply.slice(cur?.content?.length || 0))
            }
          }

          finishStreaming(msgId)
        },
        onError: (errMsg) => {
          appendStreamChunk(msgId, `\n\n> ⚠️ **Error:** ${errMsg}`)
          finishStreaming(msgId)
        },
      }, { activeDocuments })
    } catch (err) {
      appendStreamChunk(msgId, `\n\n> ⚠️ **Turn Error:** ${err?.message || err}`)
      finishStreaming(msgId)
    } finally {
      setIsPending(false)
      attachments.forEach((a) => a.previewUrl && URL.revokeObjectURL(a.previewUrl))
      setAttachments([])
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
          {/* Left buttons: MultimodalUpload (paperclip + tray) + Globe */}
          <MultimodalUpload
            isCompact
            disabled={isPending || awaitingHumanApproval}
            pendingFiles={attachments}
            onUpload={(newItems) => setAttachments((prev) => [...prev, ...newItems])}
            onRemove={(id) => setAttachments((prev) => prev.filter((i) => i.id !== id))}
          />
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
            disabled={
              (!draft.trim() && attachments.length === 0) || isPending || awaitingHumanApproval
            }
            className={`w-8 h-8 rounded-md flex items-center justify-center text-white transition-fast shadow-xs flex-shrink-0 ${
              awaitingHumanApproval || (!draft.trim() && attachments.length === 0)
                ? 'cursor-not-allowed opacity-40'
                : 'cursor-pointer'
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
