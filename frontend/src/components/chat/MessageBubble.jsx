import { formatTime } from '../../lib/formatTime'

/**
 * MessageBubble — renders a single conversation message.
 *
 * User messages:    right-aligned, accent-tinted background (FRONTEND.md §3.1)
 * Assistant messages: left-aligned, NO bubble — raw text on cream.
 *   This is deliberate: "bubbles read as 'generic chatbot,' we're avoiding that."
 *   — FRONTEND.md §3.1
 *
 * @param {{ id, role, content, timestamp }} message
 */
export function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end px-6 animate-fade-in">
        <div className="flex flex-col items-end gap-1" style={{ maxWidth: '72%' }}>
          <div
            className="px-4 py-3 text-sm leading-relaxed"
            style={{
              background: 'var(--color-accent-tint)',
              border: '1px solid var(--color-accent-border)',
              borderRadius: 'var(--radius-lg)',
              borderBottomRightRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            {message.content}
          </div>
          <span className="text-xs px-1" style={{ color: 'var(--color-text-faint)' }}>
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    )
  }

  // Assistant — no bubble, just text on the cream surface
  return (
    <div className="flex flex-col gap-1 px-6 animate-fade-in" style={{ maxWidth: '80%' }}>
      {/* Agent name label */}
      <span
        className="text-xs font-medium"
        style={{ color: 'var(--color-accent)' }}
      >
        Sovereign Workbench
      </span>
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--color-text)' }}
      >
        {message.content}
      </p>
      <span className="text-xs" style={{ color: 'var(--color-text-faint)' }}>
        {formatTime(message.timestamp)}
      </span>
    </div>
  )
}
