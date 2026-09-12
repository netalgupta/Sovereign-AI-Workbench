import { useRef, useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Send, Paperclip, CheckCircle2, Clock, Loader2, Database, ShieldAlert, X } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { sendMessage, uploadAttachment, getAttachmentStatus } from '../../lib/api'
import { Spinner } from '../ui/Spinner'
import { ErrorBanner } from '../ui/ErrorBanner'

/**
 * ChatComposer — message input bar with attachment payload & state sync.
 *
 * Features:
 *   - Category selection: "temporary" (session inspection) vs "permanent" (KB standard)
 *   - Near-real-time polling (1.2s interval) while attachment status is queued or processing
 *   - Live visual indicator moving queued -> processing -> ready without page refresh
 */
export function ChatComposer() {
  const draft = useChatStore((s) => s.draft)
  const setDraft = useChatStore((s) => s.setDraft)
  const attachments = useChatStore((s) => s.attachments)
  const addAttachment = useChatStore((s) => s.addAttachment)
  const updateAttachmentStatus = useChatStore((s) => s.updateAttachmentStatus)
  const removeAttachment = useChatStore((s) => s.removeAttachment)
  const sessionId = useChatStore((s) => s.sessionId)

  const [category, setCategory] = useState('temporary') // 'temporary' | 'permanent'
  const [sendError, setSendError] = useState(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  const addMessage = useChatStore((s) => s.addMessage)

  const mutation = useMutation({
    mutationFn: ({ message, session_id }) => sendMessage(message, session_id),
    onSuccess: (data) => {
      addMessage('assistant', data.reply, {
        citations: data.citations,
        plan: data.plan,
      })
      setSendError(null)
    },
    onError: (err) => {
      setSendError(err?.message || 'Failed to send message. Please try again.')
    },
  })

  // ── Polling effect for pending attachments ────────────────────────────────
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

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    for (const file of files) {
      // 1. Send upload request to backend API
      const res = await uploadAttachment(file, category, sessionId)
      const attId = res?.attachment_id || `att_${Date.now()}`

      // 2. Add attachment to store with initial status 'queued'
      addAttachment({
        attachment_id: attId,
        filename: file.name,
        type: file.type || 'application/octet-stream',
        category: category,
        status: res?.status || 'queued',
        created_at: new Date().toISOString(),
      })
    }
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const canSend = draft.trim().length > 0 && !mutation.isPending

  const handleSend = () => {
    if (!canSend) return
    const trimmed = draft.trim()
    setSendError(null)

    let finalMessage = trimmed
    const readyAttachments = attachments.filter((a) => a.status === 'ready')
    if (readyAttachments.length > 0) {
      const attNames = readyAttachments.map((a) => a.filename).join(', ')
      finalMessage = `${trimmed}\n\n[Attached Files: ${attNames}]`
    }

    addMessage('user', finalMessage)
    setDraft('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    mutation.mutate({ message: finalMessage, session_id: sessionId })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e) => {
    setDraft(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  return (
    <div
      className="flex-shrink-0 px-6 pb-6 pt-3"
      style={{ borderTop: '1px solid rgba(42, 39, 36, 0.04)' }}
    >
      {/* Error banner */}
      {sendError && (
        <div className="mb-3">
          <ErrorBanner message={sendError} onDismiss={() => setSendError(null)} />
        </div>
      )}

      {/* Attachment status list strip */}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((att) => {
            const isReady = att.status === 'ready'
            const isProcessing = att.status === 'processing'
            const isQueued = att.status === 'queued'
            const isFailed = att.status === 'failed'

            return (
              <div
                key={att.attachment_id}
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

                {/* Status indicator */}
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
                  className="ml-1 hover:opacity-75 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
                  title="Remove attachment"
                >
                  <X size={12} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Composer box */}
      <div
        className="flex items-end gap-2 p-3 rounded-xl transition-base"
        style={{
          background: 'white',
          border: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-sm)',
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = 'var(--color-accent-border)'
          e.currentTarget.style.boxShadow = `var(--shadow-sm), 0 0 0 3px var(--color-accent-tint)`
        }}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) {
            e.currentTarget.style.borderColor = 'var(--color-border)'
            e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
          }
        }}
      >
        {/* Attachment Category Selector & Upload Trigger */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
            disabled={mutation.isPending}
          />

          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => fileInputRef.current?.click()}
            title="Attach file (PDF, image, doc, csv)"
            className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors disabled:opacity-40"
          >
            <Paperclip size={16} />
          </button>

          {/* Category Toggle */}
          <button
            type="button"
            onClick={() => setCategory((c) => (c === 'temporary' ? 'permanent' : 'temporary'))}
            title={`Current upload category: ${category}. Click to toggle.`}
            className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-tight uppercase border transition-colors"
            style={{
              background: category === 'permanent' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(107, 114, 128, 0.1)',
              borderColor: category === 'permanent' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(107, 114, 128, 0.3)',
              color: category === 'permanent' ? '#2563eb' : '#4b5563',
            }}
          >
            {category === 'permanent' ? 'perm' : 'temp'}
          </button>
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          id="chat-composer-input"
          value={draft}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={mutation.isPending}
          placeholder="Message Sovereign Workbench…"
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm leading-relaxed outline-none"
          style={{
            color: 'var(--color-text)',
            minHeight: 24,
            maxHeight: 200,
            fontFamily: 'var(--font-ui)',
          }}
          aria-label="Message input"
        />

        {/* Send button */}
        <button
          id="chat-send-button"
          onClick={handleSend}
          disabled={!canSend}
          className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg transition-fast"
          style={{
            background: canSend ? 'var(--color-accent)' : 'var(--color-border)',
            color: canSend ? 'white' : 'var(--color-text-faint)',
            cursor: canSend ? 'pointer' : 'not-allowed',
          }}
          aria-label="Send message"
          title="Send (Enter)"
        >
          {mutation.isPending ? (
            <Spinner size="sm" />
          ) : (
            <Send size={15} strokeWidth={2} />
          )}
        </button>
      </div>

      {/* Hint text */}
      <p
        className="mt-2 text-center text-xs"
        style={{ color: 'var(--color-text-faint)' }}
      >
        Enter to send — Shift+Enter for newline
      </p>
    </div>
  )
}
