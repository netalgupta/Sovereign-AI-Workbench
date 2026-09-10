import { useEffect, useRef } from 'react'
import { useChatStore } from '../../store/chatStore'
import { MessageBubble } from './MessageBubble'

/**
 * MessageList — scrollable conversation history.
 *
 * Auto-scrolls to the latest message on every new addition.
 * Empty state shows when no messages have been sent yet.
 */
export function MessageList() {
  const messages = useChatStore((s) => s.messages)
  const setDraft = useChatStore((s) => s.setDraft)
  const bottomRef = useRef(null)

  // Smooth-scroll to bottom on every new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSelectPrompt = (promptText) => {
    setDraft(promptText)
    const textarea = document.getElementById('chat-composer-input')
    if (textarea) {
      textarea.focus()
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
    }
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center overflow-y-auto px-6">
        <div className="flex flex-col items-center gap-7 text-center w-full max-w-lg py-12">
          {/* P&ID refinery schematic motif — authentic process sensor / instrument node */}
          <div className="flex flex-col items-center gap-3">
            <svg
              width="36"
              height="36"
              viewBox="0 0 36 36"
              fill="none"
              aria-hidden="true"
              className="select-none"
            >
              {/* Process line */}
              <line x1="2" y1="18" x2="34" y2="18" stroke="var(--color-border-strong)" strokeWidth="1.25" strokeDasharray="3 2" />
              <line x1="8" y1="18" x2="28" y2="18" stroke="var(--color-text-muted)" strokeWidth="1.5" />
              {/* Flange markers */}
              <line x1="8" y1="13" x2="8" y2="23" stroke="var(--color-text-muted)" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="28" y1="13" x2="28" y2="23" stroke="var(--color-text-muted)" strokeWidth="1.5" strokeLinecap="round" />
              {/* Instrument junction / control node */}
              <circle cx="18" cy="18" r="6" fill="var(--color-bg)" stroke="var(--color-accent)" strokeWidth="1.5" />
              <circle cx="18" cy="18" r="2" fill="var(--color-accent)" />
              {/* Sensor impulse line */}
              <line x1="18" y1="12" x2="18" y2="5" stroke="var(--color-accent)" strokeWidth="1.25" />
              <circle cx="18" cy="4" r="1.5" fill="var(--color-accent)" />
            </svg>

            {/* Visual hierarchy anchor: Bold hero title */}
            <div className="flex flex-col gap-1.5 items-center">
              <h1
                className="text-2xl font-semibold tracking-tight"
                style={{ color: 'var(--color-text)' }}
              >
                Sovereign Workbench
              </h1>
              <p
                className="text-xs leading-relaxed max-w-md"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Isolated operational intelligence for refinery process units, equipment inspection, and safety-verified approval drafting.
              </p>
            </div>
          </div>

          {/* Suggested prompts — plain text list with subtle left-accent bar on hover (no pill bubbles) */}
          <div className="w-full flex flex-col gap-1.5 text-left">
            <span
              className="text-[11px] font-medium px-3 mb-0.5"
              style={{ color: 'var(--color-text-faint)' }}
            >
              Suggested engineering queries
            </span>
            {[
              'Draft an approval note for Hydrocracker Unit (HCU) charge pump mechanical seal replacement',
              'Extract corrosion wall-thickness measurements from CDU-II ultrasonic inspection report',
              'Evaluate hydrogen purity and pressure drop across PSA beds during feed fluctuation',
            ].map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handleSelectPrompt(prompt)}
                className="group w-full text-left px-3 py-2.5 rounded text-xs leading-relaxed transition-base flex items-start gap-2.5"
                style={{
                  background: 'transparent',
                  borderLeft: '2px solid transparent',
                  color: 'var(--color-text-muted)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderLeftColor = 'var(--color-accent)'
                  e.currentTarget.style.background = 'var(--color-surface)'
                  e.currentTarget.style.color = 'var(--color-text)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderLeftColor = 'transparent'
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--color-text-muted)'
                }}
                title="Click to populate composer"
              >
                <span
                  className="font-mono text-[11px] opacity-40 group-hover:opacity-100 transition-fast select-none mt-0.5"
                  style={{ color: 'var(--color-accent)' }}
                >
                  ›
                </span>
                <span className="flex-1">{prompt}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className="flex-1 overflow-y-auto py-6"
      style={{ scrollBehavior: 'smooth' }}
    >
      <div className="flex flex-col gap-5">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
