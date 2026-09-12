/**
 * MessageBubble.jsx — Single conversation message with streaming typewriter.
 *
 * FRONTEND.md §3.1:
 *   - User messages: right-aligned, accent-tinted background
 *   - Assistant messages: left-aligned, NO bubble — text on cream surface
 *   - Streaming text reveals token-by-token (even if backend returns full chunk)
 *   - Full markdown rendering: headings, bold, code blocks, tables, citations
 *
 * Streaming reveal architecture:
 *   - message.content   = full target text (grows with each SSE chunk)
 *   - message.displayedContent = what's actually rendered (chases content)
 *   - useTypewriter hook drains the delta at ~18ms/char, works for both
 *     single-chunk mock AND real multi-chunk SSE streams
 */

import { useEffect, useRef } from 'react'
import { formatTime } from '../../lib/formatTime'
import { MarkdownBody } from './MarkdownBody'
import { useChatStore } from '../../store/chatStore'

const TYPEWRITER_SPEED_MS = 18

/**
 * Typewriter inline hook — lives inside MessageBubble so it has access to
 * the exact message state without prop-drilling.
 *
 * Drains characters from message.content into message.displayedContent
 * at a constant visual speed. Safe for multi-chunk SSE (queue extends,
 * drainer continues uninterrupted).
 */
function useMessageTypewriter(message) {
  const setDisplayedContent = useChatStore((s) => s.setDisplayedContent)
  const revealedRef = useRef(message.displayedContent.length)
  const intervalRef = useRef(null)

  useEffect(() => {
    // Non-streaming or already fully revealed → skip animation
    if (!message.streaming && message.displayedContent === message.content) return
    if (message.role === 'user') return

    const target = message.content

    // Start the drain interval if not already running
    if (!intervalRef.current) {
      intervalRef.current = setInterval(() => {
        if (revealedRef.current >= target.length) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
          return
        }
        revealedRef.current += 1
        setDisplayedContent(message.id, target.slice(0, revealedRef.current))
      }, TYPEWRITER_SPEED_MS)
    }
    // If interval is already running and target grew (new SSE chunk), it will
    // naturally continue draining the newly appended characters.
  }, [message.content, message.streaming, message.displayedContent, message.id, message.role, setDisplayedContent])

  // FAILSAFE: the reveal animation must never be able to hide the answer.
  //
  // The typewriter above is a presentation nicety. It is also the only
  // thing standing between a received reply and the screen, and when it
  // stalls the result is a blank bubble stuck on "streaming..." with no
  // error anywhere -- which is exactly what shipped. The backend was
  // returning 200 OK with a correct grounded answer and the user saw
  // nothing, repeatedly, across several different attempted fixes.
  //
  // Rather than keep guessing at which interaction of batching, refs and
  // effect ordering stalls it, this makes the failure mode impossible:
  // if content exists and nothing has been revealed shortly after it
  // arrived, the whole thing is shown at once. A missing animation is a
  // cosmetic regression; a missing answer is the product not working.
  useEffect(() => {
    if (message.role === 'user') return
    if (!message.content) return
    if (message.displayedContent === message.content) return

    const failsafe = setTimeout(() => {
      // Re-read from the store rather than trusting this closure, which
      // may be describing a render from before the drain started.
      const live = useChatStore.getState().messages.find((m) => m.id === message.id)
      if (!live || !live.content) return
      if (live.displayedContent === live.content) return
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      revealedRef.current = live.content.length
      setDisplayedContent(message.id, live.content)
    }, 1200)

    return () => clearTimeout(failsafe)
  }, [message.content, message.displayedContent, message.id, message.role, setDisplayedContent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])
}

/**
 * Blinking cursor shown while streaming is active.
 */
function StreamCursor() {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: '2px',
        height: '13px',
        background: 'var(--color-accent)',
        borderRadius: '1px',
        verticalAlign: 'text-bottom',
        marginLeft: '1px',
        animation: 'breathing-dot 1s ease-in-out infinite',
        opacity: 0.8,
      }}
    />
  )
}

/**
 * @param {{ message: import('../../store/chatStore').Message }} props
 */
export function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isStreaming =
    message.streaming || message.displayedContent !== message.content

  // Start typewriter draining for this message
  useMessageTypewriter(message)

  // ── User message ────────────────────────────────────────────────────────
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
            {/* User messages are plain text — no markdown, no citations */}
            {message.content}
          </div>
          <span className="text-xs px-1" style={{ color: 'var(--color-text-faint)' }}>
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    )
  }

  // ── Assistant message ────────────────────────────────────────────────────
  // No bubble — just text on the cream surface (FRONTEND.md §3.1)
  return (
    <div className="flex flex-col gap-1 px-6 animate-fade-in" style={{ maxWidth: '84%' }}>
      {/* Agent name label */}
      <span className="text-xs font-medium" style={{ color: 'var(--color-accent)' }}>
        Sovereign Workbench
      </span>

      {/* Markdown body with streaming typewriter reveal */}
      <div className="relative">
        {/* `|| message.content` is a second, cheaper guard on the same
            failure: if displayedContent is ever empty or non-string
            while content exists, show the content. Nothing about the
            reveal animation is worth a blank answer. */}
        <MarkdownBody
          content={
            typeof message.displayedContent === 'string' && message.displayedContent
              ? message.displayedContent
              : message.content || ''
          }
        />
        {/* Blinking cursor while draining */}
        {isStreaming && <StreamCursor />}
      </div>

      <span className="text-xs" style={{ color: 'var(--color-text-faint)' }}>
        {formatTime(message.timestamp)}
        {isStreaming && (
          <span className="ml-1.5 text-[10px]" style={{ color: 'var(--color-accent)' }}>
            · streaming…
          </span>
        )}
      </span>
    </div>
  )
}
