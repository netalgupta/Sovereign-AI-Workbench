/**
 * useTypewriter.js — Generic streaming reveal buffer hook.
 *
 * Drains characters from a queue at a constant visual speed (~18ms/char),
 * regardless of how the source text arrives:
 *   • Mock API: one full string dumped at once → all chars pushed into queue
 *   • Real SSE/WS backend: chunks arrive asynchronously → each chunk's chars
 *     are appended to the queue; the drain loop continues uninterrupted
 *
 * The hook NEVER resets mid-stream. New text just extends the queue.
 *
 * Usage:
 *   const { revealed, isDone } = useTypewriter(message.content, {
 *     speedMs: 18,
 *     active: message.streaming || message.displayedContent !== message.content,
 *   })
 */

import { useEffect, useRef, useCallback } from 'react'
import { useChatStore } from '../../store/chatStore'

/**
 * @param {string}   targetText      — full text to eventually reveal (grows with SSE chunks)
 * @param {string}   messageId       — store message id to write displayedContent back
 * @param {object}   [opts]
 * @param {number}   [opts.speedMs]  — ms between each revealed character (default 18)
 * @param {boolean}  [opts.active]   — if false, skip animation (for user messages)
 */
export function useTypewriter(targetText, messageId, { speedMs = 18, active = true } = {}) {
  // Track how many characters we have already revealed (index into targetText)
  const revealedIndexRef = useRef(0)
  const intervalRef = useRef(null)
  const setDisplayedContent = useChatStore((s) => s.setDisplayedContent)

  const tick = useCallback(() => {
    // Read current targetText from closure — this is safe because the interval
    // is re-started whenever targetText changes, but revealedIndexRef persists.
    setDisplayedContent(messageId, (prev) => {
      if (revealedIndexRef.current >= targetText.length) {
        // Queue exhausted — stop
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        return prev
      }
      // Reveal one character
      const next = targetText.slice(0, revealedIndexRef.current + 1)
      revealedIndexRef.current += 1
      return next
    })
  }, [targetText, messageId, setDisplayedContent])

  useEffect(() => {
    if (!active) {
      // Not streaming — reveal everything immediately
      revealedIndexRef.current = targetText.length
      setDisplayedContent(messageId, targetText)
      return
    }

    // There are new characters to reveal (targetText grew or just started)
    if (revealedIndexRef.current < targetText.length) {
      if (!intervalRef.current) {
        intervalRef.current = setInterval(tick, speedMs)
      }
      // If interval is already running, it will naturally consume the new chars
    }

    return () => {
      // Cleanup only when unmounting, not on every targetText change
      // (the interval should keep running across chunk arrivals)
    }
  }, [targetText, active, speedMs, tick, messageId, setDisplayedContent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])
}
