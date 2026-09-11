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
import { MOCK_PLAN_STEPS, resolveApproval as apiResolveApproval } from '../lib/api'

function generateSessionId() {
  // Simple UUID v4 — no dependency needed
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export const useChatStore = create((set, get) => ({
  // ── State ──────────────────────────────────────────────────────────────────
  messages: [],
  sessionId: generateSessionId(),
  draft: '',
  plan: MOCK_PLAN_STEPS,

  // ── Approval Gate State (§3.12 / FR-15) ────────────────────────────────────
  awaitingHumanApproval: false,
  pendingApprovalAction: null,
  isApprovalModalOpen: false,

  // ── Actions ────────────────────────────────────────────────────────────────
  setDraft: (draft) => set({ draft }),
  setPlan: (plan) => set({ plan }),
  updatePlanStepStatus: (stepId, status) =>
    set((state) => ({
      plan: state.plan.map((s) =>
        s.id === stepId || s.step_id === stepId ? { ...s, status } : s
      ),
    })),

  /**
   * Set approval gate lock state. When active, blocks composer input.
   * @param {boolean} status
   * @param {object|null} [action]
   */
  setAwaitingApproval: (status, action = null) =>
    set({
      awaitingHumanApproval: status,
      pendingApprovalAction: action,
      isApprovalModalOpen: status,
    }),

  openApprovalModal: () => set({ isApprovalModalOpen: true }),
  closeApprovalModal: () => set({ isApprovalModalOpen: false }),

  /**
   * Resolve an awaiting human approval gate decision.
   * Logs an audit trail message to the conversation and unlocks composer.
   *
   * @param {boolean} confirmed - True if operator approved; False if cancelled
   */
  resolveApproval: (confirmed) => {
    const action = get().pendingApprovalAction
    const actionDesc = action?.description || 'HCU feed rate modification'

    if (action?.id) {
      apiResolveApproval(action.id, confirmed, 'operator').catch(() => {})
    }

    set({
      awaitingHumanApproval: false,
      pendingApprovalAction: null,
      isApprovalModalOpen: false,
    })

    if (confirmed) {
      get().addMessage(
        'assistant',
        `✅ **Action Authorized by Operator:** Safety gate passed. DCS feed-forward controller FFC-201 accepted parameter update: **115% (1,667 m³/h)**. Continuous interlock monitoring active.`
      )
    } else {
      get().addMessage(
        'assistant',
        `❌ **Action Cancelled by Operator:** Parameter modification was rejected. ${actionDesc} aborted. Setpoint retained at nominal **100% (1,450 m³/h)**.`
      )
    }
  },

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
