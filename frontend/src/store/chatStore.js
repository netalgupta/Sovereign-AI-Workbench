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
  attachments: [],

  // ── Attachment Actions ─────────────────────────────────────────────────────
  addAttachment: (att) =>
    set((state) => ({
      attachments: [
        ...state.attachments.filter((a) => a.attachment_id !== att.attachment_id),
        att,
      ],
    })),

  updateAttachmentStatus: (attachmentId, status, details = {}) =>
    set((state) => ({
      attachments: state.attachments.map((a) =>
        a.attachment_id === attachmentId || a.id === attachmentId
          ? { ...a, status, ...details }
          : a
      ),
    })),

  removeAttachment: (attachmentId) =>
    set((state) => ({
      attachments: state.attachments.filter(
        (a) => a.attachment_id !== attachmentId && a.id !== attachmentId
      ),
    })),

  clearAttachments: () => set({ attachments: [] }),

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
  resolveApproval: async (confirmed) => {
    const action = get().pendingApprovalAction
    const actionDesc = action?.description || action?.title || 'Action'

    set({
      awaitingHumanApproval: false,
      pendingApprovalAction: null,
      isApprovalModalOpen: false,
    })

    if (action?.id) {
      const res = await apiResolveApproval(action.id, confirmed, 'operator')
      if (confirmed) {
        if (res?.result?.file_path) {
          get().addMessage(
            'assistant',
            `✅ **Action Authorized & Executed by Operator:** Generated Word document **"${res.result.title || action.title}"** at \`${res.result.file_path}\` (${res.result.section_count} section(s), ${res.result.total_sources} source citation(s), ${res.result.byte_size} bytes).`
          )
        } else {
          get().addMessage(
            'assistant',
            `✅ **Action Authorized & Executed by Operator:** Safety gate passed. Action **"${action.title || actionDesc}"** executed successfully.`
          )
        }
      } else {
        get().addMessage(
          'assistant',
          `❌ **Action Cancelled by Operator:** Action **"${action.title || actionDesc}"** was rejected. No file or system state was modified.`
        )
      }
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
    // plan / toolCallEvents / verification carry the REAL execution
    // trace for this turn, so the UI can show what ran instead of the
    // hardcoded reasoning steps that used to be baked into ChatPane.
    const {
      streaming = false,
      citations = [],
      plan = [],
      toolCallEvents = [],
      verification = null,
      userRequest = '',
    } = opts
    const message = {
      id: generateSessionId(),
      role,
      content,
      displayedContent: streaming ? '' : content,
      streaming,
      citations,
      plan,
      toolCallEvents,
      verification,
      userRequest,
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
   * ACCEPTS EITHER A STRING OR AN UPDATER FUNCTION, and the function form
   * is not optional politeness -- it is the entire reason assistant
   * replies rendered as an empty bubble.
   *
   * useTypewriter's tick calls this React-style:
   *
   *     setDisplayedContent(messageId, (prev) => { ...; return next })
   *
   * while this reducer assigned the second argument straight through:
   *
   *     displayedContent: newDisplayed
   *
   * So displayedContent was set to the FUNCTION OBJECT. React renders
   * nothing for a function child, so the bubble stayed blank -- and
   * because the updater never ran, the revealedIndex inside it never
   * advanced, so the interval never reached its own stop condition and
   * the message sat on "streaming..." forever.
   *
   * The backend was returning 200 OK with a correct grounded answer the
   * whole time. Every reply this app has ever produced was discarded at
   * this line.
   *
   * @param {string} id
   * @param {string | ((prev: string) => string)} newDisplayed
   */
  setDisplayedContent: (id, newDisplayed) => {
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== id) return m
        const next =
          typeof newDisplayed === 'function'
            ? newDisplayed(m.displayedContent ?? '')
            : newDisplayed
        // Guard the invariant rather than trusting callers: whatever an
        // updater returns, this field must end up a string, because the
        // failure mode for anything else is a silently blank message
        // rather than an error anyone would notice.
        return { ...m, displayedContent: typeof next === 'string' ? next : String(next ?? '') }
      }),
    }))
  },

  /**
   * Clear all messages and start a new session.
   */
  clearMessages: () => {
    set({ messages: [], sessionId: generateSessionId() })
  },
}))
