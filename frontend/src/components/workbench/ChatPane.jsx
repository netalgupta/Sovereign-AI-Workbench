import { useState, useEffect, useRef } from 'react'
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
  Clock,
  Loader2,
  CheckCircle2,
  Database,
  X,
  UploadCloud,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useChatStore } from '../../store/chatStore'
import { sendMessage, uploadAttachment, getAttachmentStatus } from '../../lib/api'
import { showToast } from '../../store/toastStore'
import { MessageBubble } from '../chat/MessageBubble'
import { NetworkMonitorBar } from '../../integrations/network-monitor'
import { CalcTraceCard } from '../../integrations/calc-trace'

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
  const attachments = useChatStore((s) => s.attachments) || []
  const addAttachment = useChatStore((s) => s.addAttachment)
  const updateAttachmentStatus = useChatStore((s) => s.updateAttachmentStatus)
  const removeAttachment = useChatStore((s) => s.removeAttachment)

  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState('')
  const [isPending, setIsPending] = useState(false)
  const [category, setCategory] = useState('temporary') // 'temporary' | 'permanent'
  const [isDragging, setIsDragging] = useState(false)

  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)
  const dragCounter = useRef(0)

  // Top tabs: Chat / Notebooks / Artifacts
  const [activeTab, setActiveTab] = useState('chat')
  const [copiedCode, setCopiedCode] = useState(false)

  // Model selector state
  const [selectedModel, setSelectedModel] = useState('Model registry')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)
  const [models, setModels] = useState([])
  const [modelsError, setModelsError] = useState(null)

  const [isMidResponseExpanded, setIsMidResponseExpanded] = useState(false)
  const [liveElapsed, setLiveElapsed] = useState(0)
  const [expandedCompletedSteps, setExpandedCompletedSteps] = useState({})

  // Fetch model registry list
  useEffect(() => {
    fetch('/api/models')
      .then((res) => res.json())
      .then((data) => {
        if (data.models && Array.isArray(data.models)) {
          setModels(data.models)
          const avail = data.models.find((m) => m.status === 'available')
          if (avail) setSelectedModel(avail.id)
        }
      })
      .catch((err) => {
        setModelsError(err?.message || 'Could not fetch models')
      })
  }, [])

  // ── Polling Effect for Pending Attachments ────────────────────────────────
  useEffect(() => {
    const pending = attachments.filter(
      (a) => a.status === 'queued' || a.status === 'processing'
    )
    if (pending.length === 0) return

    const interval = setInterval(async () => {
      for (const att of pending) {
        const res = await getAttachmentStatus(att.attachment_id)
        if (res && res.status && res.status !== att.status) {
          updateAttachmentStatus(att.attachment_id, res.status, res)
        }
      }
    }, 1200)

    return () => clearInterval(interval)
  }, [attachments, updateAttachmentStatus])

  // ── Shared Unified File Upload Handler ──────────────────────────────────────
  // Used by BOTH paperclip file picker and drag-and-drop.
  const processFileSelection = async (fileList) => {
    const files = Array.from(fileList || [])
    if (files.length === 0) return

    for (const file of files) {
      showToast(`Uploading ${file.name} (${category})...`, 'info')

      // 1. Send file to POST /api/attachments/upload
      const res = await uploadAttachment(file, category, sessionId)
      const attId = res?.attachment_id || `att_${Date.now()}`

      // 2. Add to chatStore immediately with queued status
      addAttachment({
        attachment_id: attId,
        filename: file.name,
        type: file.type || 'application/octet-stream',
        category: category,
        status: res?.status || 'queued',
        created_at: new Date().toISOString(),
      })
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleFileInputChange = (e) => {
    processFileSelection(e.target.files)
  }

  // ── Robust Drag and Drop Event Handlers ─────────────────────────────────────
  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current += 1
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'copy'
    if (!isDragging) setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current -= 1
    if (dragCounter.current <= 0) {
      dragCounter.current = 0
      setIsDragging(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setIsDragging(false)

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFileSelection(e.dataTransfer.files)
    }
  }

  const handleSend = async () => {
    if (!draft.trim() || isPending || awaitingHumanApproval) return
    const text = draft.trim()
    setDraft('')
    setIsPending(true)

    // Build message string, appending ready attachments if present
    let messageText = text
    const readyAtts = attachments.filter((a) => a.status === 'ready')
    if (readyAtts.length > 0) {
      const names = readyAtts.map((a) => a.filename).join(', ')
      messageText = `${text}\n\n[Attached Files: ${names}]`
    }

    const msgId = addMessage('user', messageText)

    try {
      const res = await sendMessage(messageText, sessionId)
      if (res.reply) {
        addMessage('assistant', res.reply, {
          citations: res.citations || [],
          plan: res.plan || [],
        })
      }
    } catch (err) {
      showToast(err?.message || 'Error sending message', 'error')
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

  return (
    <div
      className="flex-1 flex flex-col min-w-0 bg-[var(--color-bg)] h-full overflow-hidden relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileInputChange}
        className="hidden"
        id="hidden-chat-file-input"
      />

      {/* Drag & Drop Target Visual Overlay */}
      {isDragging && (
        <div
          className="absolute inset-0 z-50 border-2 border-dashed border-amber-500 rounded-xl flex flex-col items-center justify-center gap-3 p-8 m-3 pointer-events-none text-amber-600 dark:text-amber-400 font-sans shadow-lg transition-all animate-fade-in"
          style={{ background: 'rgba(245, 158, 11, 0.12)' }}
        >
          <UploadCloud size={44} className="animate-bounce" />
          <div className="text-center">
            <p className="font-bold text-base tracking-tight">Drop files to attach to chat ({category})</p>
            <p className="text-xs mt-1 opacity-90">Supports PDFs, P&amp;ID scans, inspection reports, standards &amp; documents</p>
          </div>
        </div>
      )}

      {/* ── 1. Top Header Tabs ───────────────────────────────────────────── */}
      <div
        className="h-12 px-6 flex items-center justify-between flex-shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-4 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className={`font-semibold pb-3 mt-3 transition-fast ${
              activeTab === 'chat'
                ? 'border-b-2 border-[var(--color-accent)] text-[var(--color-text)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
            }`}
          >
            Chat &amp; Investigation
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('notebooks')}
            className={`font-semibold pb-3 mt-3 transition-fast ${
              activeTab === 'notebooks'
                ? 'border-b-2 border-[var(--color-accent)] text-[var(--color-text)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
            }`}
          >
            Analysis Notebooks
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-mono font-bold px-2 py-0.5 rounded uppercase tracking-wider"
            style={{ background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }}
          >
            Air-Gapped Sovereign Node
          </span>
        </div>
      </div>

      {/* ── 2. Scrollable Messages Area ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Bot size={36} className="mb-3 opacity-40" style={{ color: 'var(--color-accent)' }} />
            <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
              Ask about your sources
            </h3>
            <p
              className="text-xs max-w-md mt-1.5 leading-relaxed"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Answers are grounded in the documents listed under Sources, with a
              citation for each claim. Drop inspection reports or click the paperclip to attach files.
            </p>
          </div>
        )}

        {/* Dynamic Messages */}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      {/* ── 3. Chat Composer Docked Above Status Strip ──────────────────── */}
      <div
        className="px-6 py-3 flex-shrink-0"
        style={{ borderTop: '1px solid var(--color-border)' }}
      >
        {/* Safety Gate Locked Banner when approval is pending */}
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

        {/* Active Attachment Chips Strip */}
        {attachments.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-2">
            {attachments.map((att) => {
              const isReady = att.status === 'ready'
              const isProcessing = att.status === 'processing'
              const isQueued = att.status === 'queued'
              const isFailed = att.status === 'failed'

              return (
                <div
                  key={att.attachment_id}
                  title={isFailed ? (att.error || 'Upload / Processing failed') : `${att.filename} (${att.status})`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono border transition-all"
                  style={{
                    background: isReady
                      ? 'rgba(34, 197, 94, 0.08)'
                      : isProcessing
                      ? 'rgba(59, 130, 246, 0.08)'
                      : isFailed
                      ? 'rgba(239, 68, 68, 0.08)'
                      : 'rgba(234, 179, 8, 0.08)',
                    borderColor: isReady
                      ? 'rgba(34, 197, 94, 0.3)'
                      : isProcessing
                      ? 'rgba(59, 130, 246, 0.3)'
                      : isFailed
                      ? 'rgba(239, 68, 68, 0.3)'
                      : 'rgba(234, 179, 8, 0.3)',
                    color: isReady
                      ? '#15803d'
                      : isProcessing
                      ? '#1d4ed8'
                      : isFailed
                      ? '#b91c1c'
                      : '#a16207',
                  }}
                >
                  {att.category === 'permanent' ? (
                    <Database size={12} className="opacity-70" title="Permanent KB Document" />
                  ) : (
                    <Clock size={12} className="opacity-70" title="Temporary Session File" />
                  )}

                  <span className="truncate max-w-[160px] font-medium">{att.filename}</span>

                  <span className="text-[10px] uppercase font-bold px-1 py-0.2 rounded bg-black/5 dark:bg-white/10">
                    {att.category}
                  </span>

                  <div className="flex items-center gap-1 ml-1 font-semibold text-[11px]">
                    {isQueued && (
                      <>
                        <Clock size={12} className="animate-pulse" />
                        <span>queued</span>
                      </>
                    )}
                    {isProcessing && (
                      <>
                        <Loader2 size={12} className="animate-spin" />
                        <span>processing</span>
                      </>
                    )}
                    {isReady && (
                      <>
                        <CheckCircle2 size={12} />
                        <span>ready</span>
                      </>
                    )}
                    {isFailed && (
                      <>
                        <ShieldAlert size={12} />
                        <span>failed</span>
                      </>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => removeAttachment(att.attachment_id)}
                    className="ml-1 hover:opacity-75 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 cursor-pointer"
                    title="Remove attachment"
                  >
                    <X size={12} />
                  </button>
                </div>
              )
            })}
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
          {/* Left buttons: Paperclip + Category Toggle + Globe */}
          <button
            type="button"
            id="chat-paperclip-btn"
            disabled={awaitingHumanApproval}
            onClick={() => fileInputRef.current?.click()}
            className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
              awaitingHumanApproval
                ? 'cursor-not-allowed opacity-40'
                : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
            }`}
            style={{ color: 'var(--color-text-muted)' }}
            title="Attach file (PDF, image, doc, csv)"
          >
            <Paperclip size={15} strokeWidth={2} />
          </button>

          {/* Category Toggle button */}
          <button
            type="button"
            id="chat-category-toggle-btn"
            onClick={() => setCategory((c) => (c === 'temporary' ? 'permanent' : 'temporary'))}
            title={`Current upload category: ${category}. Click to toggle.`}
            className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-tight uppercase border transition-colors cursor-pointer"
            style={{
              background: category === 'permanent' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(107, 114, 128, 0.1)',
              borderColor: category === 'permanent' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(107, 114, 128, 0.3)',
              color: category === 'permanent' ? '#2563eb' : '#4b5563',
            }}
          >
            {category === 'permanent' ? 'perm' : 'temp'}
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

          {/* Model Selector Dropdown */}
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
              title="Model registry profile"
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
