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
  FileText,
  X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { usePreviewStore } from '../../store/previewStore'
import { OutputJobCard } from './OutputJobCard'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from '../../store/chatStore'
import { useIngestionStore } from '../../store/ingestionStore'
import { sendMessageStream, uploadFilesToCorpus, analyseAttachment, callTool } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { CalcTraceCard } from '../../integrations/calc-trace'
import LiveAudioVisualizer from './LiveAudioVisualizer'
import RealOutputCards, { OUTPUTS_CHANGED } from '../../integrations/output-cards/RealOutputCards'

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
  const sourcesEnabled = useChatStore((s) => s.sourcesEnabled)
  const toggleSourcesEnabled = useChatStore((s) => s.toggleSourcesEnabled)
  const awaitingHumanApproval = useChatStore((s) => s.awaitingHumanApproval)
  const setAwaitingApproval = useChatStore((s) => s.setAwaitingApproval)
  const setActiveJob = useChatStore((s) => s.setActiveJob)
  const openApprovalModal = useChatStore((s) => s.openApprovalModal)
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState('')
  const [isPending, setIsPending] = useState(false)

  // Files queued in the composer tray (§3.13). Each item's status/progress
  // is driven ONLY by the real upload/OCR steps below.
  const openPreview = usePreviewStore((s) => s.openPreview)
  const [attachments, setAttachments] = useState([])

  // Top tabs: Chat / Notebooks / Artifacts (synchronized with TopBar)
  const activeTab = useChatStore((s) => s.activeTab)
  const setActiveTab = useChatStore((s) => s.setActiveTab)

  // Code block copy state
  const [copiedCode, setCopiedCode] = useState(false)

  // Model selector state (Cosmetic selector pointing to real models.yaml entries)
  // Kept for the trigger label only; routing is per-task, so there is no
  // "selected" model to send anywhere.
  const [selectedModel, setSelectedModel] = useState('Model registry')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)

  // ── Voice Dictation & Multi-line Composer State ───────────────────────────
  const [isListening, setIsListening] = useState(false)
  // Dictation records locally and transcribes on OUR backend. It used the
  // Web Speech API, which in Chromium streams microphone audio to Google's
  // servers -- hard constraint #1 -- and worked on any networked machine.
  const recorderRef = useRef(null)
  const audioChunksRef = useRef([])
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
  // Drag-over state for the drop target over the composer (§3.13).
  const [isDragOver, setIsDragOver] = useState(false)

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

  const addFiles = async (fileList, label) => {
    const files = Array.from(fileList || [])
    if (files.length === 0) return

    const newAttachments = []
    const mediaAttachments = []
    for (const file of files) {
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
      // Images and audio go through the REAL pipeline on send: uploaded into
      // the corpus, then OCR / transcription through the registered tools.
      // Only small text files are pasted inline, as before.
      if (file.type.startsWith('image/') || file.type.startsWith('audio/')) {
        mediaAttachments.push({
          id: `media_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
          file,
          name: file.name,
          size: file.size,
          previewUrl,
          status: 'queued',
          progress: 0,
        })
        continue
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
    if (mediaAttachments.length) setAttachments((prev) => [...prev, ...mediaAttachments])
    setTemporaryAttachments((prev) => [...prev, ...newAttachments])
    showToast(`Attached ${newAttachments.length + mediaAttachments.length} file(s) to this message`, 'info')
  }

  // Paperclip inputs reach the tray through the same code as drag-and-drop,
  // so one path decides what is media (OCR/transcription pipeline) and what
  // is a small inline text file.
  const handleBrowserFilesUpload = (e, label) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    e.target.value = ''
    addFiles(files, label)
  }

  // ── Drag-and-drop over the composer (§3.13) ──────────────────────────────
  const handleDragEnter = (e) => {
    if (isPending || awaitingHumanApproval) return
    e.preventDefault()
    e.stopPropagation()
    if (e.dataTransfer?.types?.includes('Files')) setIsDragOver(true)
  }

  const handleDragOver = (e) => {
    if (isPending || awaitingHumanApproval) return
    e.preventDefault()
    e.stopPropagation()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)
    if (isPending || awaitingHumanApproval) return
    const files = Array.from(e.dataTransfer?.files || [])
    if (files.length) addFiles(files, 'drop')
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

  // Stop any recording on unmount
  useEffect(() => {
    return () => {
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try {
          recorderRef.current.stop()
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
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try { recorderRef.current.stop() } catch (e) {}
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  // Stop the recorder and resolve with the recorded audio (or null).
  const stopRecorder = () =>
    new Promise((resolve) => {
      const rec = recorderRef.current
      recorderRef.current = null
      if (!rec || rec.state === 'inactive') {
        resolve(null)
        return
      }
      rec.onstop = () => {
        const chunks = audioChunksRef.current
        audioChunksRef.current = []
        resolve(chunks.length ? new Blob(chunks, { type: rec.mimeType || 'audio/webm' }) : null)
      }
      try {
        rec.stop()
      } catch (e) {
        resolve(null)
      }
    })

  const releaseMicrophone = () => {
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }
  }

  // Confirm voice dictation: transcribe LOCALLY, then append to the draft.
  const confirmListening = async () => {
    const blob = await stopRecorder()
    releaseMicrophone()
    setIsListening(false)
    setInterimTranscript('')
    setSessionTranscript('')

    if (blob && blob.size > 0) {
      showToast('Transcribing on this machine…', 'info')
      try {
        const audioBase64 = await readFileAsBase64(blob)
        const res = await fetch('/api/transcribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audioBase64, mimeType: blob.type || 'audio/webm' }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
        const spoken = (data.text || '').trim()
        if (spoken) {
          setDraft(() => {
            const base = baseDraftRef.current || ''
            const spacing = base && !base.endsWith(' ') && !base.endsWith('\n') ? ' ' : ''
            return base + spacing + spoken
          })
        } else {
          showToast('No speech was recognised in the recording', 'warning')
        }
      } catch (err) {
        showToast(`Local transcription failed: ${String(err?.message || err).slice(0, 120)}`, 'error')
      }
    }

    setTimeout(() => {
      textareaRef.current?.focus()
    }, 50)
  }

  // Cancel voice dictation: discard the recording and restore previous composer text
  const cancelListening = async () => {
    await stopRecorder()
    audioChunksRef.current = []
    releaseMicrophone()
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

    // 3. Record locally. Transcription happens on confirm, on our backend.
    if (typeof MediaRecorder === 'undefined') {
      showToast('Recording is not supported in this browser', 'error')
      releaseMicrophone()
      return
    }
    try {
      audioChunksRef.current = []
      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunksRef.current.push(event.data)
      }
      recorder.start(250)
      recorderRef.current = recorder
    } catch (err) {
      console.warn('MediaRecorder start failed:', err)
      showToast('Could not start recording', 'error')
      releaseMicrophone()
      return
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
    const hasAttachments = attachments.length > 0
    if ((!draft.trim() && temporaryAttachments.length === 0 && !hasAttachments) || isPending || awaitingHumanApproval) return
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

    // ── Attachment pipeline before sending (real upload + OCR/vision) ──
    // Uploads write the file into the corpus (so grounded answers can cite
    // it), then images/audio run through the registered vision tools. Every
    // tool event below carries genuine backend output; a failure becomes a
    // visible 'failed' event instead of a silent pretend success.
    let pipelineEvents = []
    // FR-14: vision-model readings of uploaded images, appended to the
    // outbound message so the reply can actually describe what the image
    // depicts. Each is an ESTIMATE (badged in the trace via /api/tools
    // metadata), never a measurement.
    let visionContext = []
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
        if (['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'webp'].includes(ext)) return 'detect_defects'
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
              // Keep every overlay-relevant field. The DefectOverlay mounts
              // only when the event carries `detections` AND an
              // `image_url`/`imageUrl`; a pipeline event that stripped
              // down to full_text alone would render no boxes.
              output: {
                ...(result.full_text !== undefined
                  ? { full_text: String(result.full_text).slice(0, 6000) }
                  : {}),
                ...(result.detections !== undefined ? { detections: result.detections } : {}),
                ...(result.image_url !== undefined ? { image_url: result.image_url } : {}),
                ...(result.imageUrl !== undefined ? { imageUrl: result.imageUrl } : {}),
                ...(result.findings !== undefined ? { findings: result.findings } : {}),
              },
            })
          }
          // FR-14: OCR alone never INTERPRETS an image. For pictures and
          // diagrams (P&IDs, photos, scans) also run the vision model and
          // surface its reading as an ESTIMATE-badged event, exactly like
          // chart reading. The `is_estimate` badge comes from /api/tools
          // metadata, so no custom rendering is needed here.
          if (tool === 'detect_defects') {
            try {
              const vision = await callTool('describe_image', { image_path: path })
              if (vision && vision.description) {
                const desc = String(vision.description)
                pipelineEvents.push({
                  tool_name: 'describe_image',
                  status: 'done',
                  output: {
                    full_text: desc.slice(0, 6000),
                  },
                })
                visionContext.push(
                  `\n\n_Vision-model description of attached image (${a.name}) — ESTIMATE, not a measurement:_\n${desc}`
                )
              }
            } catch (err) {
              pipelineEvents.push({
                tool_name: 'describe_image',
                status: 'failed',
                error: String(err?.message || err).slice(0, 240),
              })
            }
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
    const userText =
      (hasAttachments && !text ? `Analyse the attached file${names.length > 1 ? 's' : ''}: ${names.join(', ')}` : text) +
      visionContext.join('')
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
        onDeckJob: (jobEv) => {
          // A deck, report or spreadsheet is being written in the background;
          // the card follows it and its approval arrives when it is ready.
          if (jobEv.job) setActiveJob(jobEv.job)
        },
        onApprovalRequired: (appEv) => {
          // Only what the backend sent. This fallback used to title every
          // approval "Confirm Critical Parameter Modification" as a
          // DCS_SETPOINT_WRITE, so a request to write a document was shown
          // as a setpoint change on the screen where the operator signs off.
          const actionPayload = appEv.action || {
            id: appEv.id,
            title: 'Confirm action',
            action_type: appEv.name || 'operator action',
            description: appEv.effect || '',
            arguments: appEv.arguments,
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
      }, { activeDocuments, sourcesEnabled })
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
      {/* ── 2. Active Tab Content (Chat / Notebooks / Artifacts) ─────────── */}

      {/* ── 2. Active Tab Content ──────────────────────────────────────── */}
      {activeTab === 'artifacts' ? (
        /* Every file the operator has approved, newest first (outputs/). */
        <RealOutputCards />
      ) : activeTab !== 'chat' ? (
        /* Notebooks: not built yet */
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

      {/* ── 3. Chat Composer Seamlessly Integrated with Chat Stream ──── */}
      <div className="px-8 pb-5 pt-1 flex-shrink-0">
        {/* A deck, report or spreadsheet being written in the background. */}
        <OutputJobCard />

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
              className={`relative flex items-end gap-3 px-4 py-3 rounded-xl transition-fast shadow-[var(--shadow-md)] ${
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
              onDragEnter={handleDragEnter}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {isDragOver && (
                <div
                  className="pointer-events-none absolute inset-0 z-20 rounded-xl flex items-center justify-center border-2 border-dashed"
                  style={{
                    borderColor: 'var(--color-accent)',
                    background: 'var(--color-accent-tint)',
                  }}
                >
                  <div
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium"
                    style={{ color: 'var(--color-accent)', background: 'var(--color-surface)' }}
                  >
                    <ImageIcon size={14} strokeWidth={2} />
                    Drop files to attach — images and audio enter the OCR/transcription pipeline
                  </div>
                </div>
              )}
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
            {(temporaryAttachments.length > 0 || attachments.length > 0) && (
              <div className="flex flex-wrap items-center gap-1.5 mb-2 px-1">
                {attachments.map((att) => (
                  <div
                    key={att.id}
                    onClick={() => att.status !== 'error' && openPreview({
                      id: att.id,
                      name: att.name,
                      filename: att.name,
                      attachmentId: att.attachmentId || att.attachment_id || att.id,
                    })}
                    className="flex items-center gap-1.5 px-1.5 py-0.5 rounded-md text-[11px] border cursor-pointer hover:border-[var(--color-accent)]"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: att.status === 'error' ? 'var(--color-danger, #C8413B)' : 'var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                    title={att.status === 'error' ? 'Upload or analysis failed' : 'Click to open a preview'}
                  >
                    {att.previewUrl ? (
                      <img
                        src={att.previewUrl}
                        alt={att.name}
                        className="w-6 h-6 rounded object-cover border flex-shrink-0"
                        style={{ borderColor: 'var(--color-border)' }}
                      />
                    ) : (
                      <FileText size={11} className="text-[var(--color-accent)] flex-shrink-0" />
                    )}
                    <span className="font-medium truncate max-w-[120px]">{att.name}</span>
                    <span className="text-[9px] text-[var(--color-text-muted)]">{att.status}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
                        setAttachments((prev) => prev.filter((x) => x.id !== att.id))
                      }}
                      className="w-3.5 h-3.5 rounded flex items-center justify-center hover:bg-[var(--color-overlay)] text-[var(--color-text-muted)] hover:text-red-500 cursor-pointer"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
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
            disabled={
              (!draft.trim() && attachments.length === 0 && temporaryAttachments.length === 0) || isPending || awaitingHumanApproval
            }
            className={`w-8 h-8 rounded-md flex items-center justify-center text-white transition-fast shadow-xs flex-shrink-0 ${
              awaitingHumanApproval || (!draft.trim() && attachments.length === 0 && temporaryAttachments.length === 0)
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
            </motion.div>
          )}
        </AnimatePresence>
      </div>

    </div>
  )
}
