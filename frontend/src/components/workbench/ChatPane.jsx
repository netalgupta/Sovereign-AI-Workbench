import { useState, useEffect, useRef, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  MoreHorizontal,
  Paperclip,
  Mic,
  MicOff,
  Code,
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
  FilePlus,
  FolderPlus,
  Image as ImageIcon,
  Shield,
  ShieldCheck,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from '../../store/chatStore'
import { useIngestionStore } from '../../store/ingestionStore'
import { sendMessageStream } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { CalcTraceCard } from '../../integrations/calc-trace'
import LiveAudioVisualizer from './LiveAudioVisualizer'

// Helper to convert browser File object to Base64
const readFileAsBase64 = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      const base64 = typeof result === 'string' ? result.split(',')[1] || '' : ''
      resolve(base64)
    }
    reader.onerror = (err) => reject(err)
    reader.readAsDataURL(file)
  })
}

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
  const addThoughtEvent = useChatStore((s) => s.addThoughtEvent)
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

  // Top tabs: Chat / Notebooks / Artifacts
  const [activeTab, setActiveTab] = useState('chat')

  // Code block copy state
  const [copiedCode, setCopiedCode] = useState(false)

  // Model selector state (Cosmetic selector pointing to real models.yaml entries)
  // Kept for the trigger label only; routing is per-task, so there is no
  // "selected" model to send anywhere.
  const [selectedModel, setSelectedModel] = useState('Model registry')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)

  // ── Voice Dictation & Multi-line Composer State ───────────────────────────
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef(null)
  const audioStreamRef = useRef(null)
  const textareaRef = useRef(null)
  const [interimTranscript, setInterimTranscript] = useState('')
  const [sessionTranscript, setSessionTranscript] = useState('')
  const [recordingDuration, setRecordingDuration] = useState(0)
  const baseDraftRef = useRef('')

  // ── Attachment Popover & Ingestion State ───────────────────────────────────
  const [isAttachMenuOpen, setIsAttachMenuOpen] = useState(false)
  const [temporaryAttachments, setTemporaryAttachments] = useState([])
  const attachMenuRef = useRef(null)
  const docFileInputRef = useRef(null)
  const photoFileInputRef = useRef(null)
  const startTrackingIngestion = useIngestionStore((s) => s.startTracking)

  // ── Real-Time Network Monitor Telemetry for Header Button ─────────────────
  const [networkStatus, setNetworkStatus] = useState({ isAirGapped: true, socketCount: 0, available: false })

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const res = await fetch('/api/network/status')
        if (res.ok && active) {
          const data = await res.json()
          setNetworkStatus({
            isAirGapped: data.is_air_gapped !== false,
            socketCount: Array.isArray(data.connections) ? data.connections.length : (data.externalCount ?? 0),
            available: data.status !== 'error' && data.status !== 'unknown',
          })
        }
      } catch {
        // preserve fallback
      }
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  // Close attachment dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (attachMenuRef.current && !attachMenuRef.current.contains(e.target)) {
        setIsAttachMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Attachment flow handlers: Temporary Attachments vs Permanent Sources
  const handleAddDocument = () => {
    setIsAttachMenuOpen(false)
    docFileInputRef.current?.click()
  }

  const handleAddPhoto = () => {
    setIsAttachMenuOpen(false)
    photoFileInputRef.current?.click()
  }

  const handleAddSourceDirectory = () => {
    setIsAttachMenuOpen(false)
    window.dispatchEvent(new CustomEvent('open-add-source-modal'))
  }

  const handleBrowserFilesUpload = async (e, label) => {
    const fileList = Array.from(e.target.files || [])
    if (fileList.length === 0) return
    e.target.value = ''

    const newAttachments = []
    for (const file of fileList) {
      let previewUrl = null
      let textContent = null
      if (file.type.startsWith('image/')) {
        previewUrl = URL.createObjectURL(file)
      } else if (
        file.size < 500_000 &&
        (file.name.endsWith('.txt') ||
          file.name.endsWith('.md') ||
          file.name.endsWith('.json') ||
          file.name.endsWith('.csv') ||
          file.name.endsWith('.py') ||
          file.name.endsWith('.yaml') ||
          file.name.endsWith('.yml'))
      ) {
        try {
          textContent = await file.text()
        } catch {}
      }
      newAttachments.push({
        id: `temp_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
        name: file.name,
        size: file.size,
        type: label || 'document',
        previewUrl,
        textContent,
      })
    }
    setTemporaryAttachments((prev) => [...prev, ...newAttachments])
    showToast(`Attached ${newAttachments.length} temporary ${label || 'file'}(s) to this message`, 'info')
  }

  // Detect code or markdown structure in draft
  const isCodeOrMarkdown = useMemo(() => {
    if (!draft || !draft.includes('\n')) return false
    const trimmed = draft.trim()
    if (trimmed.startsWith('```') || trimmed.includes('\n```')) return true
    if (trimmed.includes('---') || trimmed.startsWith('# ') || trimmed.includes('\n# ')) return true
    const lines = draft.split('\n')
    if (lines.length < 2) return false
    const codePatterns = [
      /^\s*(import|from|export|const|let|var|function|def|class|return|if|for|while)\b/,
      /[{};=><]\s*$/,
      /^\s*(\/\/|#|\/\*|\*)/,
      /^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\b/i,
      /^\s*<[a-zA-Z0-9_-]+.*>/,
      /^\s*print\(|console\.log\(/,
    ]
    let codeCount = 0
    for (const line of lines) {
      if (codePatterns.some((p) => p.test(line))) codeCount++
    }
    return codeCount >= 2
  }, [draft])

  // Auto-resize textarea height as content grows
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 180) + 'px'
    }
  }, [draft])

  // Clean up speech recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop()
        } catch (e) {}
      }
    }
  }, [])

  // Timer and keyboard escape handler for voice dictation
  useEffect(() => {
    let interval = null
    if (isListening) {
      interval = setInterval(() => {
        setRecordingDuration((d) => d + 1)
      }, 1000)
    } else {
      setRecordingDuration(0)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isListening])

  useEffect(() => {
    if (!isListening) return
    const handleGlobalKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        cancelListening()
      } else if (e.key === 'Enter') {
        e.preventDefault()
        confirmListening()
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [isListening, sessionTranscript, interimTranscript])

  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop() } catch (e) {}
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  // Confirm voice dictation: commit transcribed text and restore normal composer
  const confirmListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.onend = null
        recognitionRef.current.stop()
      } catch (e) {}
      recognitionRef.current = null
    }

    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }

    // Append session transcription to base draft
    const fullSessionText = (sessionTranscript + (interimTranscript ? ' ' + interimTranscript : '')).trim()
    if (fullSessionText) {
      setDraft((prev) => {
        const base = baseDraftRef.current || ''
        const spacing = base && !base.endsWith(' ') && !base.endsWith('\n') ? ' ' : ''
        return base + spacing + fullSessionText
      })
    }

    setInterimTranscript('')
    setSessionTranscript('')
    setIsListening(false)

    setTimeout(() => {
      textareaRef.current?.focus()
    }, 50)
  }

  // Cancel voice dictation: discard recorded speech and restore previous composer text
  const cancelListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.onend = null
        recognitionRef.current.stop()
      } catch (e) {}
      recognitionRef.current = null
    }

    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }

    // Discard any transcribed speech from this session and restore snapshot
    setDraft(baseDraftRef.current || '')
    setInterimTranscript('')
    setSessionTranscript('')
    setIsListening(false)

    setTimeout(() => {
      textareaRef.current?.focus()
    }, 50)
  }

  const stopListening = confirmListening

  // Toggle voice dictation using MediaStream + Web Audio Analyser + Web Speech API
  const toggleListening = async () => {
    if (isListening) {
      stopListening()
      return
    }

    // 1. Snapshot base draft and reset session buffers
    baseDraftRef.current = draft
    setInterimTranscript('')
    setSessionTranscript('')
    setRecordingDuration(0)

    // 2. Request microphone stream (feeds Web Audio AnalyserNode for live audiogram)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showToast('Microphone device access (getUserMedia) is not supported in this browser', 'error')
      return
    }

    let stream = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioStreamRef.current = stream
    } catch (err) {
      console.error('Microphone access denied or unavailable:', err)
      showToast('Microphone access denied: please enable microphone permission', 'error')
      return
    }

    // 3. Initialize SpeechRecognition if available
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.lang = 'en-US'

        recognition.onstart = () => {
          // Recognition started
        }

        recognition.onresult = (event) => {
          let currentFinal = ''
          let currentInterim = ''

          for (let i = 0; i < event.results.length; i++) {
            const chunk = event.results[i][0]?.transcript || ''
            if (event.results[i].isFinal) {
              currentFinal += chunk + ' '
            } else {
              currentInterim += chunk
            }
          }

          setInterimTranscript(currentInterim)
          if (currentFinal) {
            setSessionTranscript(currentFinal.trim())
          }
        }

        recognition.onerror = (event) => {
          console.warn('Speech recognition event:', event.error)
          if (event.error === 'no-speech') {
            // Silence detected; do not abort, let user speak when ready
            return
          }
          if (event.error === 'network') {
            // Chromium Web Speech API requires Google cloud endpoint.
            // In air-gapped / local networks, notify user that live audiogram continues
            showToast('Air-gapped mode: cloud STT endpoint unreachable, live audiogram active', 'info')
          } else if (event.error !== 'aborted') {
            showToast(`Voice recognition: ${event.error}`, 'warning')
          }
        }

        recognition.onend = () => {
          // If still recording, keep state
        }

        recognitionRef.current = recognition
        recognition.start()
      } catch (err) {
        console.warn('SpeechRecognition start failed:', err)
      }
    } else {
      showToast('Web Speech API not supported; live audiogram active', 'info')
    }

    setIsListening(true)
  }

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
    window.useChatStore = useChatStore
    return () => {
      delete window.__workbenchSetThinkingMidResponse
      delete window.__workbenchSetThinkingExpanded
      delete window.__workbenchSetCompletedPhrases
      delete window.__workbenchTriggerApproval
      delete window.__workbenchResolveApproval
      delete window.useChatStore
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
    if ((!draft.trim() && temporaryAttachments.length === 0) || isPending || awaitingHumanApproval) return
    let text = draft.trim()

    if (temporaryAttachments.length > 0) {
      const attDescriptions = temporaryAttachments
        .map((att) => {
          let desc = `[Temporary Attachment: ${att.name}]`
          if (att.textContent) {
            desc += `\n\`\`\`\n${att.textContent.slice(0, 3000)}\n\`\`\``
          }
          return desc
        })
        .join('\n\n')
      text = text ? `${text}\n\n${attDescriptions}` : attDescriptions
      setTemporaryAttachments([])
    }

    setDraft('')
    addMessage('user', text)
    setIsPending(true)

    // Add the assistant message immediately with streaming=true so MessageBubble
    // starts typewriter draining as real SSE chunks arrive, and TurnTrace shows
    // in-flight agent activity live as it happens.
    const startTime = Date.now()
    const msgId = addMessage('assistant', '', {
      streaming: true,
      citations: [],
      toolCallEvents: [],
      userRequest: text,
      plan: [],
      verification: null,
      route: null,
      elapsedSeconds: 0,
    })

    try {
      await sendMessageStream(text, sessionId, {
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
            reasoning: call.reasoning,
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
        onThought: (thoughtEv) => {
          if (thoughtEv?.text) {
            addThoughtEvent(msgId, thoughtEv.text)
          }
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
        className="flex items-center justify-between px-8 pt-4 pb-3.5 flex-shrink-0 select-none gap-6"
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
            className="flex items-center p-1 rounded-lg text-xs font-medium ml-3 gap-1 border relative"
            style={{ background: 'var(--color-overlay)', borderColor: 'var(--color-border)' }}
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
                  className="relative flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs transition-fast cursor-pointer"
                  style={{
                    color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                    fontWeight: isActive ? 600 : 500,
                  }}
                >
                  {isActive && (
                    <motion.div
                      layoutId="chatpane-active-tab-pill"
                      className="absolute inset-0 rounded-md border"
                      style={{
                        background: 'var(--color-surface)',
                        borderColor: 'var(--color-border-strong)',
                        boxShadow: 'var(--shadow-xs)',
                      }}
                      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                    />
                  )}
                  <span className="relative z-10 flex items-center gap-2">
                    <tab.icon size={13} strokeWidth={2} />
                    <span>{tab.label}</span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Right Header Actions: Plan DAG Compact Progress Strip + Live Sockets + Overflow Menu */}
        <div className="flex items-center gap-2">
          {(() => {
            const doneSteps = plan.filter((s) => s.status === 'done').length
            const runningStep = plan.find((s) => s.status === 'running')
            const currentStepNum = doneSteps + (runningStep ? 1 : 0)
            const totalSteps = plan.length || 5

            return (
              <Link
                to={`/plan/${sessionId}`}
                className="group flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-medium transition-fast hover:bg-[var(--color-surface-hover)] shadow-xs cursor-pointer select-none row-hover-lift"
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

          {/* Dedicated Live Sockets Telemetry Button (Relocated from bottom strip) */}
          <Link
            to="/monitor"
            id="live-sockets-header-btn"
            className="group flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-medium transition-fast hover:bg-[var(--color-surface-hover)] shadow-xs cursor-pointer select-none row-hover-lift"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
            }}
            title="Inspect real-time air-gap security and socket telemetry (/monitor)"
          >
            <div
              className="flex items-center gap-1.5"
              style={{ color: networkStatus.isAirGapped ? '#10b981' : '#ef4444' }}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${networkStatus.isAirGapped ? 'bg-emerald-500' : 'bg-red-500'} animate-pulse`}
              />
              <ShieldCheck size={13} strokeWidth={2.2} />
              <span className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>
                Live Sockets ({networkStatus.available ? networkStatus.socketCount : 0})
              </span>
            </div>
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
          className="flex-1 overflow-y-auto px-8 py-6 flex flex-col gap-7"
        >
          {messages.length === 0 && !isPending && (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-16 animate-fade-in">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mb-3.5"
                style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
              >
                <MessageSquare size={24} />
              </div>
              <h3 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Ask about your sources
              </h3>
              <p
                className="text-xs max-w-md mt-2 leading-relaxed"
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
        className="px-8 py-4 flex-shrink-0"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        {/* Safety Gate Locked Banner when approval is pending (§3.12 / FR-15) */}
        {awaitingHumanApproval && (
          <div
            id="composer-approval-locked-banner"
            className="mb-3 px-4 py-2.5 rounded-lg flex items-center justify-between gap-3 text-xs animate-fade-in border"
            style={{
              background: 'var(--color-error-tint)',
              borderColor: 'var(--color-accent-border)',
            }}
          >
            <div className="flex items-center gap-2.5 min-w-0">
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
              className="px-3 py-1.5 rounded-md text-[11px] font-bold text-white transition-fast cursor-pointer hover:brightness-110 flex-shrink-0 shadow-xs"
              style={{ background: 'var(--color-accent)' }}
            >
              Review Gate
            </button>
          </div>
        )}

        <AnimatePresence mode="wait">
          {isListening ? (
            <motion.div
              key="voice-recording-pill"
              initial={{ opacity: 0, scale: 0.98, y: 2 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 2 }}
              transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
              className="w-full"
            >
              <LiveAudioVisualizer
                stream={audioStreamRef.current}
                onConfirm={confirmListening}
                onCancel={cancelListening}
              />
            </motion.div>
          ) : (
            <motion.div
              key="normal-composer"
              initial={{ opacity: 0, scale: 0.98, y: 2 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 2 }}
              transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
              className={`flex items-end gap-3 px-4 py-3 rounded-xl transition-fast shadow-[var(--shadow-md)] ${
                isCodeOrMarkdown ? 'ring-1 ring-[var(--color-accent-border)]' : ''
              }`}
              style={{
                background: isCodeOrMarkdown ? 'var(--color-surface-hover)' : 'var(--color-input-bg)',
                border: awaitingHumanApproval
                  ? '1px dashed var(--color-accent)'
                  : '1px solid var(--color-input-border)',
                boxShadow: 'var(--shadow-md)',
                opacity: awaitingHumanApproval ? 0.75 : 1,
              }}
            >
          {/* Hidden file inputs for document and photo attachments */}
          <input
            ref={docFileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx,.xls,.txt,.csv,.json,.md,.yaml,.yml,.py,.sql"
            className="hidden"
            onChange={(e) => handleBrowserFilesUpload(e, 'document')}
          />
          <input
            ref={photoFileInputRef}
            type="file"
            multiple
            accept="image/*,.png,.jpg,.jpeg,.tiff,.bmp,.svg"
            className="hidden"
            onChange={(e) => handleBrowserFilesUpload(e, 'photo')}
          />

          {/* Left buttons: Paperclip (with animated popover) + Globe + Mic */}
          <div className="flex items-center gap-1.5 pb-0.5">
            {/* Attachment Button + Animated Popover */}
            <div className="relative" ref={attachMenuRef}>
              <button
                type="button"
                id="chat-attachment-btn"
                disabled={awaitingHumanApproval}
                onClick={() => !awaitingHumanApproval && setIsAttachMenuOpen((prev) => !prev)}
                className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
                  awaitingHumanApproval
                    ? 'cursor-not-allowed opacity-40'
                    : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
                }`}
                style={{
                  color: isAttachMenuOpen ? 'var(--color-accent)' : 'var(--color-text-muted)',
                  background: isAttachMenuOpen ? 'var(--color-accent-tint)' : 'transparent',
                }}
                title="Attach document, photo, or source directory"
                aria-label="Attach source"
              >
                <Paperclip size={15} strokeWidth={2} />
              </button>

              {/* Animated Attachment Dropdown via Framer Motion */}
              <AnimatePresence>
                {isAttachMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: 6 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 6 }}
                    transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                    className="absolute left-0 bottom-full mb-2 w-56 rounded-xl py-1.5 z-50 shadow-xl border overflow-hidden"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      boxShadow: 'var(--shadow-lg)',
                    }}
                  >
                    <div
                      className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: 'var(--color-text-faint)' }}
                    >
                      Temporary Attachments (This Chat)
                    </div>

                    {/* 1. Add Document */}
                    <button
                      type="button"
                      id="attach-add-document-btn"
                      onClick={handleAddDocument}
                      className="w-full px-3 py-2 text-xs flex items-center gap-2.5 transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer text-left"
                      style={{ color: 'var(--color-text)' }}
                    >
                      <div
                        className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
                        style={{ background: 'rgba(59, 130, 246, 0.12)', color: '#3b82f6' }}
                      >
                        <FilePlus size={13} strokeWidth={2.2} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-medium text-xs">Attach Document</span>
                        <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                          Temporary PDF, DOCX, XLSX, TXT
                        </span>
                      </div>
                    </button>

                    {/* 2. Add Photo */}
                    <button
                      type="button"
                      id="attach-add-photo-btn"
                      onClick={handleAddPhoto}
                      className="w-full px-3 py-2 text-xs flex items-center gap-2.5 transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer text-left"
                      style={{ color: 'var(--color-text)' }}
                    >
                      <div
                        className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
                        style={{ background: 'rgba(168, 85, 247, 0.12)', color: '#a855f7' }}
                      >
                        <ImageIcon size={13} strokeWidth={2.2} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-medium text-xs">Attach Photo / Scan</span>
                        <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                          Photos, P&amp;ID scans, defect images
                        </span>
                      </div>
                    </button>

                    <div className="my-1 border-t" style={{ borderColor: 'var(--color-border)' }} />

                    <div
                      className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
                      style={{ color: 'var(--color-text-faint)' }}
                    >
                      Permanent Knowledge Base
                    </div>

                    {/* 3. Add Source Directory */}
                    <button
                      type="button"
                      id="attach-add-directory-btn"
                      onClick={handleAddSourceDirectory}
                      className="w-full px-3 py-2 text-xs flex items-center gap-2.5 transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer text-left"
                      style={{ color: 'var(--color-text)' }}
                    >
                      <div
                        className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
                        style={{ background: 'rgba(16, 185, 129, 0.12)', color: '#10b981' }}
                      >
                        <FolderPlus size={13} strokeWidth={2.2} />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="font-medium text-xs">Add Permanent Sources…</span>
                        <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                          Index into long-term corpus
                        </span>
                      </div>
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button
              type="button"
              disabled={awaitingHumanApproval}
              onClick={() => showToast('Grounded in local sources — Zero outbound network egress', 'success')}
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
            <button
              type="button"
              id="voice-dictation-btn"
              disabled={awaitingHumanApproval}
              onClick={toggleListening}
              className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
                awaitingHumanApproval
                  ? 'cursor-not-allowed opacity-40'
                  : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
              } ${isListening ? 'animate-pulse' : ''}`}
              style={{
                color: isListening ? 'var(--color-accent)' : 'var(--color-text-muted)',
                background: isListening ? 'var(--color-accent-tint)' : 'transparent',
              }}
              title={isListening ? 'Stop voice recording' : 'Start voice dictation'}
            >
              {isListening ? (
                <MicOff size={15} strokeWidth={2.2} />
              ) : (
                <Mic size={15} strokeWidth={2} />
              )}
            </button>
          </div>

          {/* Input field (Multi-line auto-resizing textarea with code/markdown detection) */}
          <div className="flex-1 flex flex-col min-w-0 py-0.5">
            {/* Temporary Attachment Chips */}
            {temporaryAttachments.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mb-2 px-1">
                {temporaryAttachments.map((att) => (
                  <div
                    key={att.id}
                    className="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] border"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                  >
                    <FileText size={11} className="text-[var(--color-accent)]" />
                    <span className="font-medium truncate max-w-[120px]">{att.name}</span>
                    <span className="text-[9px] text-[var(--color-text-muted)]">
                      ({Math.round(att.size / 1024)}KB)
                    </span>
                    <button
                      type="button"
                      onClick={() => setTemporaryAttachments((prev) => prev.filter((x) => x.id !== att.id))}
                      className="w-3.5 h-3.5 rounded flex items-center justify-center hover:bg-[var(--color-overlay)] text-[var(--color-text-muted)] hover:text-red-500 cursor-pointer"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {isCodeOrMarkdown && (
              <div
                className="flex items-center gap-1.5 px-2 py-0.5 mb-1.5 rounded text-[10px] font-mono select-none w-fit border animate-fade-in"
                style={{
                  background: 'var(--color-accent-tint)',
                  borderColor: 'var(--color-accent-border)',
                  color: 'var(--color-accent)',
                }}
              >
                <Code size={11} strokeWidth={2.5} />
                <span>Code / Markdown detected</span>
              </div>
            )}
            <textarea
              ref={textareaRef}
              id="chat-composer-input"
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                awaitingHumanApproval
                  ? 'Composer locked: Human authorization required at approval gate...'
                  : 'Ask a follow-up or command an agentic task (Shift+Enter for newline)...'
              }
              className={`w-full bg-transparent text-xs outline-none placeholder:text-[var(--color-text-faint)] resize-none overflow-y-auto leading-relaxed ${
                isCodeOrMarkdown ? 'font-mono text-[11.5px]' : ''
              } ${awaitingHumanApproval ? 'cursor-not-allowed text-[var(--color-text-muted)]' : ''}`}
              style={{
                color: 'var(--color-text)',
                maxHeight: '180px',
              }}
              disabled={isPending || awaitingHumanApproval}
            />
          </div>

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
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
