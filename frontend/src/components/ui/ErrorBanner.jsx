import { X, AlertTriangle } from 'lucide-react'
import { useState } from 'react'

/**
 * ErrorBanner — inline, dismissable error message.
 * FRONTEND.md §6 rule 2: "Every error shows a human-readable message,
 * never a raw stack trace or raw JSON error in the UI."
 *
 * @param {string}   message    - Human-readable error text
 * @param {boolean}  [dismissible=true]
 * @param {Function} [onDismiss]
 */
export function ErrorBanner({ message, dismissible = true, onDismiss }) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  const handleDismiss = () => {
    setDismissed(true)
    onDismiss?.()
  }

  // Strip raw JSON / stack traces — show only human-readable part
  const safeMessage =
    typeof message === 'string'
      ? message.replace(/\{.*?\}/gs, '[details hidden]').slice(0, 200)
      : 'An unexpected error occurred. Please try again.'

  return (
    <div
      className="flex items-start gap-3 px-4 py-3 rounded-lg text-sm animate-fade-in"
      style={{
        background: 'var(--color-error-tint)',
        border: '1px solid',
        borderColor: 'var(--color-error)',
        borderOpacity: 0.25,
        color: 'var(--color-text)',
      }}
      role="alert"
    >
      <AlertTriangle
        size={16}
        strokeWidth={2}
        style={{ color: 'var(--color-error)', flexShrink: 0, marginTop: 1 }}
      />
      <span className="flex-1 leading-snug">{safeMessage}</span>
      {dismissible && (
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 rounded transition-fast hover:opacity-60"
          style={{ color: 'var(--color-text-muted)' }}
          aria-label="Dismiss error"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
