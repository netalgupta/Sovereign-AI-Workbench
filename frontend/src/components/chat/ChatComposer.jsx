import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { sendMessage } from '../../lib/api'
import { MultimodalUpload } from '../../integrations/multimodal-upload'
import { Spinner } from '../ui/Spinner'
import { ErrorBanner } from '../ui/ErrorBanner'

/**
 * ChatComposer — message input bar at the bottom of the chat pane.
 *
 * Wiring:
 *   - useMutation wraps sendMessage (the ONLY call site for api.js)
 *   - On success: assistant reply appended to chatStore
 *   - On error: ErrorBanner shown inline — never raw error objects
 *   - Loading: Send button shows Spinner, textarea + button disabled
 *
 * Paperclip icon is stubbed (non-functional) — file upload arrives Day 3-4.
 */
export function ChatComposer() {
  const draft = useChatStore((s) => s.draft)
  const setDraft = useChatStore((s) => s.setDraft)
  const [sendError, setSendError] = useState(null)
  const textareaRef = useRef(null)

  const addMessage = useChatStore((s) => s.addMessage)
  const sessionId  = useChatStore((s) => s.sessionId)

  const mutation = useMutation({
    mutationFn: ({ message, session_id }) => sendMessage(message, session_id),
    onSuccess: (data) => {
      addMessage('assistant', data.reply)
      setSendError(null)
    },
    onError: (err) => {
      setSendError(
        err?.message || 'Failed to send message. Please try again.'
      )
    },
  })

  const canSend = draft.trim().length > 0 && !mutation.isPending

  const handleSend = () => {
    if (!canSend) return
    const trimmed = draft.trim()
    setSendError(null)
    addMessage('user', trimmed)
    setDraft('')
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    mutation.mutate({ message: trimmed, session_id: sessionId })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e) => {
    setDraft(e.target.value)
    // Auto-grow textarea
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
          <ErrorBanner
            message={sendError}
            onDismiss={() => setSendError(null)}
          />
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
        {/* Multimodal upload integration boundary — owned by Sahil (FRONTEND.md §3.13) */}
        <MultimodalUpload
          isCompact={true}
          disabled={mutation.isPending}
          onUpload={(files) => {
            if (files && files.length > 0) {
              const fileNames = files.map((f) => f.name).join(', ')
              setDraft((prev) => (prev ? `${prev} [Attached: ${fileNames}]` : `[Attached: ${fileNames}] `))
            }
          }}
        />

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
