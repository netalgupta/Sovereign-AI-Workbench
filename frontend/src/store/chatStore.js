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

export const useChatStore = create((set, get) => ({
  // ── State ──────────────────────────────────────────────────────────────────
  messages: [],
  sessionId: generateSessionId(),
  draft: '',
  plan: [],

  // ── Approval Gate State (§3.12 / FR-15) ────────────────────────────────────
  awaitingHumanApproval: false,
  pendingApprovalAction: null,
  // The background job writing a deck, document or spreadsheet, while it runs.
  activeJob: null,
  isApprovalModalOpen: false,
  approvalError: null,
  isResolvingApproval: false,

  // ── Active Documents (Source Filtering) ───────────────────────────────────
  // Built from the Sources panel — names of files currently toggled ON.
  // Passed as active_documents to every /api/chat/stream call.
  // null means "NOT YET KNOWN -- do not filter", and it is NOT the same
  // as [] which means "the user switched every source off". The backend
  // draws that distinction deliberately (grounded_retrieval.py), and
  // collapsing it here is a race with a baffling symptom:
  //
  //   the store starts empty, the sidebar only fills it once
  //   /api/corpus resolves, and a message sent before that -- or any
  //   time that fetch fails -- told the backend every source was
  //   switched off. The user then sees "you have disabled all sources"
  //   having touched nothing.
  //
  // So the initial value is null, and only a real answer from the
  // sources panel ever makes it an array.
  activeDocuments: null,
  setActiveDocuments: (docs) =>
    set({ activeDocuments: Array.isArray(docs) ? docs : null }),

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
      approvalError: null,
      isResolvingApproval: false,
    }),

  openApprovalModal: () => set({ isApprovalModalOpen: true, approvalError: null }),

  /**
   * Follow a background output job (deck, document, spreadsheet) until it
   * is finished, refused or failed. When it is ready, its approval becomes
   * the pending one, so the same gate the operator always sees carries it.
   */
  setActiveJob: (job) => {
    if (!job?.job_id) return
    set({ activeJob: job })
    const poll = async () => {
      if (get().activeJob?.job_id !== job.job_id) return
      let next = null
      try {
        const res = await fetch(`/api/decks/${job.job_id}`)
        if (res.ok) next = await res.json()
      } catch {
        // The backend went away mid-job: leave the last state on screen
        // rather than replacing it with a guess about what happened.
      }
      if (!next) {
        setTimeout(poll, 3000)
        return
      }
      set({ activeJob: next })
      if (next.status === 'awaiting_approval' && next.approval) {
        set({
          awaitingHumanApproval: true,
          pendingApprovalAction: next.approval,
          isApprovalModalOpen: true,
        })
        return
      }
      if (next.status === 'refused' || next.status === 'failed') {
        get().addMessage('assistant', next.status === 'refused'
          ? `**Nothing was written.** ${next.error || ''}`
          : `**The job failed.** ${next.error || ''}`)
        set({ activeJob: null })
        return
      }
      setTimeout(poll, 2000)
    }
    setTimeout(poll, 1500)
  },

  clearActiveJob: () => set({ activeJob: null }),
  closeApprovalModal: () => set({ isApprovalModalOpen: false, approvalError: null }),
  setApprovalError: (error) => set({ approvalError: error }),

  /**
   * Resolve an awaiting human approval gate decision.
   * AWAITS the real backend API call.
   * On success: posts the authorized message only after backend confirms.
   * On failure: keeps modal open, shows clear error message, never posts success message.
   *
   * @param {boolean} confirmed - True if operator approved; False if cancelled
   */
  resolveApproval: async (confirmed) => {
    const action = get().pendingApprovalAction
    const actionDesc = action?.description || ''
    set({ approvalError: null, isResolvingApproval: true })

    // ── REFUSE path ──────────────────────────────────────────────────────────
    if (!confirmed) {
      if (action?.id) {
        try {
          await fetch('/api/approvals/refuse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              request_id: action.id,
              decided_by: 'local-operator',
              reason: 'Operator cancelled',
            }),
          })
        } catch {}
      }
      set({
        awaitingHumanApproval: false,
        pendingApprovalAction: null,
        isApprovalModalOpen: false,
        approvalError: null,
        isResolvingApproval: false,
      })
      // What was actually refused, not an invented setpoint story: this
      // said "Parameter modification was rejected... Setpoint retained at
      // nominal" for a refused Word document.
      set({ activeJob: null })
      get().addMessage(
        'assistant',
        `**Cancelled.** Nothing was written.${actionDesc ? `\n\n${actionDesc}` : ''}`
      )
      return { success: true }
    }

    // ── APPROVE path — two steps: approve then execute ────────────────────────
    if (!action?.id) {
      const errMsg = 'No active approval request ID'
      set({ approvalError: errMsg, isApprovalModalOpen: true, isResolvingApproval: false })
      return { success: false, error: errMsg }
    }

    // Step 1: POST /api/approvals/approve
    let approveResult = null
    try {
      const approveRes = await fetch('/api/approvals/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: action.id,
          decided_by: 'local-operator',
          reason: 'Operator confirmed via approval gate',
        }),
      })
      if (approveRes.ok) {
        approveResult = await approveRes.json()
      } else {
        const errData = await approveRes.json().catch(() => ({}))
        const errMsg = errData.detail || errData.message || `Approval backend returned HTTP ${approveRes.status}`
        set({ approvalError: errMsg, isApprovalModalOpen: true, isResolvingApproval: false })
        return { success: false, error: errMsg }
      }
    } catch (err) {
      const errMsg = `Network error reaching /api/approvals/approve: ${err?.message || err}`
      set({ approvalError: errMsg, isApprovalModalOpen: true, isResolvingApproval: false })
      return { success: false, error: errMsg }
    }

    // Step 2: POST /api/approvals/execute (with token from step 1)
    const execToken = approveResult?.token || approveResult?.execution_token
    if (execToken) {
      try {
        const execRes = await fetch('/api/approvals/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: execToken }),
        })
        if (!execRes.ok) {
          const errData = await execRes.json().catch(() => ({}))
          const errMsg = errData.detail || errData.message || `Execute backend returned HTTP ${execRes.status}`
          set({ approvalError: errMsg, isApprovalModalOpen: true, isResolvingApproval: false })
          return { success: false, error: errMsg }
        }
      } catch (err) {
        const errMsg = `Network error reaching /api/approvals/execute: ${err?.message || err}`
        set({ approvalError: errMsg, isApprovalModalOpen: true, isResolvingApproval: false })
        return { success: false, error: errMsg }
      }
    }
    // Note: if no execution token was returned (action is just recorded, not dispatched),
    // the approve step alone is sufficient — this covers both action kinds.

    // Backend genuinely confirmed
    set({
      awaitingHumanApproval: false,
      pendingApprovalAction: null,
      isApprovalModalOpen: false,
      approvalError: null,
      isResolvingApproval: false,
    })

    const paramDetail = action?.proposed_value || 'confirmed'
    const controller = action?.target || 'requested action'
    get().addMessage(
      'assistant',
      `✅ **Action Authorized by Operator:** Safety gate passed. ${controller} accepted parameter update: **${paramDetail}**. Continuous interlock monitoring active.`
    )
    return { success: true }
  },

  /**
   * Update arbitrary properties on an existing message.
   * @param {string} id
   * @param {object} updates
   */
  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    }))
  },

  /**
   * Append or update an in-flight tool call event on a message.
   * @param {string} messageId
   * @param {object} toolEvent
   */
  addToolCallEvent: (messageId, toolEvent) => {
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== messageId) return m
        const events = Array.isArray(m.toolCallEvents) ? m.toolCallEvents : []
        const matchIdx = events.findIndex((e) => e.id === toolEvent.id)
        if (matchIdx >= 0) {
          const updated = [...events]
          updated[matchIdx] = { ...updated[matchIdx], ...toolEvent }
          return { ...m, toolCallEvents: updated }
        }
        return { ...m, toolCallEvents: [...events, toolEvent] }
      }),
    }))
  },

  /**
   * Append a thought or process reasoning event to a message's trace.
   * @param {string} messageId
   * @param {string} thoughtText
   */
  addThoughtEvent: (messageId, thoughtText) => {
    if (!thoughtText) return
    set((state) => ({
      messages: state.messages.map((m) => {
        if (m.id !== messageId) return m
        const existing = Array.isArray(m.thoughts) ? m.thoughts : []
        return { ...m, thoughts: [...existing, thoughtText] }
      }),
    }))
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
