import { create } from 'zustand'
import { now } from '../lib/formatTime'

/**
 * chatStore.js — Zustand store for conversation state.
 *
 * Shape is compatible with AGENTS_SPEC.md AgentState:
 *   sessionId → AgentState.session_id
 *   messages  → derived from AgentState.tool_call_log + draft_output
 *
 * When Aditya's real backend is wired in, the message list will be
 * augmented with ToolCallEvent rendering (Day 3-4), but this store
 * shape stays stable.
 */

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
   * @param {'user' | 'assistant'} role
   * @param {string} content
   */
  addMessage: (role, content) => {
    const message = {
      id: generateSessionId(), // reuse uuid generator for msg IDs
      role,
      content,
      timestamp: now(),
    }
    set((state) => ({ messages: [...state.messages, message] }))
  },

  /**
   * Clear all messages and start a new session.
   */
  clearMessages: () => {
    set({ messages: [], sessionId: generateSessionId() })
  },
}))
