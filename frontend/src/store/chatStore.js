/**
 * chatStore.js — Zustand store for conversation state.
 *
 * Shape is compatible with AGENTS_SPEC.md AgentState:
 *   sessionId → AgentState.session_id
 *   messages  → derived from AgentState.tool_call_log + draft_output
 *
 * Day 3-4 additions:
 *   - messages now carry `streaming`, `displayedContent`, and `citations`
 *   - appendStreamChunk(id, chunk) — generic reveal buffer, works for mock
 *     (single chunk) and real SSE (multiple variable-size chunks)
 *   - finishStreaming(id) — called when the last chunk has been queued
 */

import { create } from 'zustand'
import { now } from '../lib/formatTime'

function generateSessionId() {
  // Simple UUID v4 — no dependency needed
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export const useChatStore = create((set) => ({
  // ── State ──────────────────────────────────────────────────────────────────
  messages: [],
  sessionId: generateSessionId(),
  draft: '',

  // ── Actions ────────────────────────────────────────────────────────────────
  setDraft: (draft) => set({ draft }),

  /**
   * Add a message to the conversation.
   * For assistant messages, content starts empty; displayedContent is revealed
   * progressively by the typewriter hook via appendStreamChunk.
   *
   * @param {'user' | 'assistant'} role
   * @param {string} content       — full content (immediately visible for user msgs)
   * @param {object} [opts]
   * @param {boolean} [opts.streaming] — if true, start with empty displayedContent
   * @param {Array}   [opts.citations] — citation objects from the API response
   */
  addMessage: (role, content, opts = {}) => {
    const { streaming = false, citations = [] } = opts
    const message = {
      id: generateSessionId(),
      role,
      content,
      displayedContent: streaming ? '' : content,
      streaming,
      citations,
      timestamp: now(),
    }
    set((state) => ({ messages: [...state.messages, message] }))
    return message.id
  },

  /**
   * Append a chunk of text to a streaming message's full content buffer.
   * The typewriter hook reads `content` and drains into `displayedContent`.
   * Calling this repeatedly (for real SSE chunks) is safe — it just extends
   * the queue without resetting.
   *
   * @param {string} id      — message id
   * @param {string} chunk   — new text to append
   */
  appendStreamChunk: (id, chunk) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + chunk } : m
      ),
    }))
  },

  /**
   * Mark streaming as done for a message.
   * The typewriter continues draining until displayedContent === content.
   *
   * @param {string} id
   */
  finishStreaming: (id) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, streaming: false } : m
      ),
    }))
  },

  /**
   * Called by the typewriter hook every tick to advance displayedContent.
   * This is the only place displayedContent is mutated.
   *
   * @param {string} id
   * @param {string} newDisplayed — the updated displayed string
   */
  setDisplayedContent: (id, newDisplayed) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, displayedContent: newDisplayed } : m
      ),
    }))
  },

  /**
   * Clear all messages and start a new session.
   */
  clearMessages: () => {
    set({ messages: [], sessionId: generateSessionId() })
  },
}))
