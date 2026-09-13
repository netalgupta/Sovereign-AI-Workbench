/**
 * api.js — The ONLY file that knows this is mocked.
 *
 * Every component calls sendMessage / checkBackendHealth exactly as if
 * they were real network calls. When Aditya's real FastAPI endpoint is
 * ready, only this file changes — no component or store modifications needed.
 *
 * Contract (FRONTEND.md §3.1, §3.2):
 *   POST /api/chat
 *   Body:     { message: string, session_id: string }
 *   Response: {
 *     reply:      string,          — full markdown body
 *     citations:  Citation[],      — see /src/integrations/citations/contract.js
 *     session_id: string,
 *   }
 */

const MOCK_LATENCY_MS = 400

// ---------------------------------------------------------------------------
// Mock citation data — matches the Citation contract shape exactly.
// When Aditya's backend returns real retrieval passages, this constant is
// replaced by the live API response body. No other file changes.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Mock citation data — grounded directly in the actual MRPL_RAG_Test_Corpus.
// Matches the Citation contract shape exactly.
// ---------------------------------------------------------------------------
const MOCK_CITATIONS = [
  {
    id: 1,
    doc: 'SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx',
    section: 'Section 4.2 — Feed Rate Operating Limits & WABT End-of-Run',
    passage:
      'The design-basis feed rate for Hydrocracking Unit 2 (HCU-2) shall not exceed 110 % of nameplate capacity (Q_d = 1,450 m³/h) under any continuous operating mode. Sustained feed elevation accelerates bed fouling; WABT trigger limit is 410 °C. Exceedance for more than 15 minutes triggers an automatic interlock via the DCS feed-forward controller (FFC-201).',
  },
  {
    id: 2,
    doc: 'Aromatic_Complex_Benzene_Safety_Circular.docx',
    section: 'Section 2.1 — High-Temperature Catalyst Runaway Prevention',
    passage:
      'Operating at elevated feed rates increases LHSV (Liquid Hourly Space Velocity) which reduces residence time. At LHSV > 1.8 h⁻¹, exothermic quench reactions become thermally unstable across Beds 1-3; H₂/HC ratio must be maintained above 1,000 Nm³/m³ to suppress runaway. Continuous VOC monitoring active.',
  },
  {
    id: 3,
    doc: 'Novolen_Batch_QA_Report_Aug2026.pdf',
    section: 'Section 3.1 — Downstream Excursion & Fractionation Flooding Criteria',
    passage:
      'Column flooding is defined as the condition where liquid entrainment rate exceeds 10 % of vapour flow. At feed rates above 110 % of design capacity, flooding probability increases to 34 % based on the correlation: F_factor = u_v × √ρ_v. Immediate operator intervention is required per MOC procedure.',
  },
  {
    id: 4,
    doc: 'PSA_Hydrogen_Purity_Trend_Log.xlsx',
    section: 'Sheet 1 (Weeks 1–12) — Thermocouple Array TC-201 Telemetry & H2 Quality',
    passage:
      'TC-201A: 381.4 °C · TC-201B: 382.1 °C · TC-201C: 383.0 °C · TC-201D: 380.9 °C · TC-201E: 382.6 °C · TC-201F: 381.7 °C. Rolling average across 6 sensors: 381.95 °C. Upper operating limit: 400 °C. Rate-of-change: +0.4 °C/hr. PSA-3 purity drift to 99.65% cross-referenced.',
  },
]

// ---------------------------------------------------------------------------
// Rich markdown reply used when the user sends a new message.
// Exercises every §3.1-3.3 feature: headings, bold, code block (Python),
// inline citations [1][2], and a markdown table.
// ---------------------------------------------------------------------------
function buildMockReply(userMessage) {
  return `**Analysis complete.** Here is a summary for your query: _"${userMessage}"_

---

### Operational Risk Assessment (Grounded in MRPL Corpus)

Increasing the HCU feed rate beyond 110 % design capacity introduces three compounding risks: thermal runaway across Reactor R-201 Beds 1-3, H₂ compressor capacity saturation (K-201), and downstream fractionation column flooding. [1][2]

The primary safety constraint is the feed-forward interlock (FFC-201) and the WABT end-of-run trigger (> 410 °C per SOP-114-Rev3). Operating above this threshold reduces catalyst residency time and risks rapid exothermic excursion. [1][2]

### Current Reactor Inlet Temperatures (Thermocouple Telemetry)

Based on the latest thermocouple array readings (4-shift rolling average from process logs): [4]

| Sensor | Reading (°C) | Limit (°C) | Status |
|--------|-------------|-----------|--------|
| TC-201A | 381.4 | 400 | ✓ Normal |
| TC-201B | 382.1 | 400 | ✓ Normal |
| TC-201C | 383.0 | 400 | ✓ Normal |
| TC-201D | 380.9 | 400 | ✓ Normal |
| TC-201E | 382.6 | 400 | ✓ Normal |
| TC-201F | 381.7 | 400 | ✓ Normal |

**Rolling average:** 381.95 °C — safety margin: **18.05 °C** (within envelope)

### Recommended Guard Logic

\`\`\`python
# Feed-rate guard — per SOP-114-Rev3 §4.2 & FFC-201 interlock
if feed_rate > 1.10 * design_capacity:
    alert("High risk: exceeds 110% design threshold (1,450 m³/h)")
    suggest_mitigation(cool_quench=True, bed_quench_valve="QFC-18")

# Catalyst bed temperature check against WABT headroom
if inlet_temp > 395:  # 5°C early-warning headroom before 400°C threshold
    trigger_alarm(level="WARNING", channel="TC-201", target_unit="HCU-2")
\`\`\`

> ⚠️ **Operator note:** If feed rate must exceed 110 % for operational reasons, engage quench flow controller (QFC-18) first and maintain H₂/HC ratio above 1,000 Nm³/m³ before any ramp. [3]`
}

// ---------------------------------------------------------------------------
// Mock plan steps — matches AGENTS_SPEC.md PlanStep schema exactly:
// { id, step_id, description, assigned_agent, status, depends_on, tool_call_event_id }
// Includes a fork: step-2 and step-3 both depend on step-1 in parallel.
// tool_call_event_id strings match the DOM IDs in ChatPane.jsx string-for-string.
// ---------------------------------------------------------------------------
export const MOCK_PLAN_STEPS = [
  {
    id: 'step-1',
    step_id: 'step-1',
    description: 'Deconstruct refinery parameters and construct multi-phase verification plan',
    assigned_agent: 'reasoning',
    status: 'done',
    depends_on: [],
    tool_call_event_id: 'step-4-planning',
  },
  {
    id: 'step-2',
    step_id: 'step-2',
    description: 'Query historical thermocouple sensor trends across 4 shifts (TC-201 array)',
    assigned_agent: 'code',
    status: 'done',
    depends_on: ['step-1'],
    tool_call_event_id: 'step-2-1-telemetry',
  },
  {
    id: 'step-3',
    step_id: 'step-3',
    description: 'Retrieve plant safety limits and evaluate thermal runaway operating envelope',
    assigned_agent: 'vision',
    status: 'done',
    depends_on: ['step-1'],
    tool_call_event_id: 'step-2-2-limits',
  },
  {
    id: 'step-4',
    step_id: 'step-4',
    description: 'Compile volumetric flow differential pressure equation in SymPy AST',
    assigned_agent: 'math',
    status: 'running',
    depends_on: ['step-2', 'step-3'],
    tool_call_event_id: 'step-2-computation',
  },
  {
    id: 'step-5',
    step_id: 'step-5',
    description: 'Verify API-521 boundary threshold and confirm +18.2% operational headroom',
    assigned_agent: 'reasoning',
    status: 'pending',
    depends_on: ['step-4'],
    tool_call_event_id: 'step-1-verification',
  },
]

export const MOCK_FEED_RATE_APPROVAL_ACTION = {
  id: 'act-feed-rate-115',
  title: 'Confirm Critical Parameter Modification',
  action_type: 'DCS_SETPOINT_WRITE',
  target: 'HCU-2 / FFC-201',
  description: 'This will change HCU feed rate from 100% to 115%.',
  detail:
    'This action will adjust the HCU-2 reactor feed rate setpoint from 100% (1,450 m³/h) to 115% (1,667 m³/h) via DCS feed-forward controller FFC-201.',
  current_value: '100% (1,450 m³/h)',
  proposed_value: '115% (1,667 m³/h)',
  unit: 'm³/h',
  parameter: 'FFC-201.SP (Feed Rate Setpoint)',
  risk_level: 'CRITICAL',
  warning:
    'Operating above 110% reduces catalyst residence time (LHSV > 1.8 h⁻¹) and increases exothermic runaway risk. Fractionation column flooding probability increases to 34%.',
  mitigation_required:
    'Mandatory pre-condition: Quench flow controller (QFC-18) armed and H₂/HC ratio maintained > 1,000 Nm³/m³ before setpoint ramp.',
}

/**
 * Detects if a message expresses an explicit intent to ACT (commanding a critical
 * parameter change or setpoint adjustment) versus an intent to ASK/inquire.
 *
 * Strict requirements:
 * - Questions (ending in '?' or starting with interrogatives like 'What', 'Can you', 'Should we')
 *   MUST NOT trigger approval.
 * - Only imperative verbs indicating a requested change ('increase', 'set', 'change', 'raise',
 *   'adjust', 'modify', 'ramp up') directed at feed rate trigger the gate.
 *
 * @param {string} msg
 * @returns {boolean}
 */
export function isActionApprovalRequest(msg) {
  if (!msg || typeof msg !== 'string') return false
  const text = msg.trim()

  // 1. Exclude questions or informational inquiries
  if (text.endsWith('?')) return false
  if (
    /^(what|why|how|can you|could you|should we|would you|is it|are there|explain|tell me about)\b/i.test(
      text
    )
  ) {
    return false
  }

  // 2. Require action verbs commanding a change to feed rate
  const actionVerbBefore =
    /\b(increase|raise|set|change|modify|adjust|boost|ramp\s*up|scale\s*up)\s+(the\s+)?feed[- ]?rate\b/i
  const actionVerbAfter =
    /\bfeed[- ]?rate\s*(to|=|:=|\bset to\b|\bchanged to\b|\braised to\b|\bincreased to\b)\s*\d+/i

  return actionVerbBefore.test(text) || actionVerbAfter.test(text)
}

export async function checkBackendHealth() {
  try {
    const res = await fetch('/api/health')
    if (res.ok) {
      const data = await res.json()
      return { ok: true, live: true, ...data }
    }
  } catch {}
  return { ok: true, live: false }
}

/**
 * Send operator decision (Confirm or Cancel) to the safety approval gate.
 */
export async function resolveApproval(requestId, confirmed = true, operator = 'operator') {
  try {
    const res = await fetch('/api/approvals/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, confirmed, operator }),
    })
    if (res.ok) {
      const data = await res.json()
      return { ok: true, status: data.status || (confirmed ? 'approved' : 'refused'), ...data }
    }
    const errData = await res.json().catch(() => ({}))
    const errorMsg = errData.detail || errData.message || `Backend returned HTTP ${res.status}`
    return { ok: false, status: 'error', error: errorMsg }
  } catch (err) {
    console.warn('[API] /api/approvals/resolve error:', err)
    return { ok: false, status: 'error', error: err?.message || 'Network error reaching /api/approvals/resolve' }
  }
}

/**
 * Fetch live hardware zero-egress telemetry from backend.
 */
export async function getNetworkStatus() {
  try {
    const res = await fetch('/api/network/status')
    if (res.ok) return await res.json()
  } catch {}
  return null
}

// A full agent turn on this hardware is retrieval + a 14B reasoning
// generation + a verification pass, all CPU-bound. Measured end to end
// on the dev box: 69 seconds for a short question, and longer once
// generation is genuinely grounded rather than templated.
//
// This was 60000. The backend took 69s. So the abort ALWAYS fired
// before the reply arrived, every live answer was discarded unread, and
// every message silently became the offline simulation below - which
// renders identically to a real answer. The product appeared to work
// perfectly while never once showing backend output.
//
// A timeout shorter than the operation it guards does not protect
// anything; it just guarantees the fallback path.
const LIVE_TURN_TIMEOUT_MS = 300000 // 5 min

/**
 * Is the backend process actually there?
 *
 * This distinction decides whether falling back to a simulation is
 * honest. Backend absent (dev machine, frontend-only work) -> a clearly
 * labelled simulation is useful. Backend PRESENT but slow or erroring ->
 * a simulation is a lie about a system that is right there and
 * answering, so the failure is reported instead.
 */
async function backendIsReachable() {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 2500)
    const res = await fetch('/api/health', { signal: ctl.signal })
    clearTimeout(t)
    return res.ok
  } catch {
    return false
  }
}

/**
 * Stream a chat turn from the backend via real SSE (POST /api/chat/stream).
 * Interleaves narration tokens, tool call events, step updates, and approval gates.
 *
 * Falls back to labelled offline simulation only if the backend is genuinely unreachable.
 */
export async function sendMessageStream(message, sessionId, callbacks = {}, options = {}) {
  const {
    onStart,
    onPlan,
    onRoute,
    onMemory,
    onToolCall,
    onToolResult,
    onTextDelta,
    onApprovalRequired,
    onDone,
    onError,
  } = callbacks

  // Defaulting to [] here would tell the backend "every source is
  // switched off" for any caller that does not pass the option at all.
  // null is the only safe default: no filter.
  const { activeDocuments = null } = options

  let liveError = null
  let receivedAnyEvent = false

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), LIVE_TURN_TIMEOUT_MS)

    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: sessionId || 'default',
        // Sent only when it is a real answer. null is omitted so the
        // backend applies no filter, rather than being told the user
        // deselected everything.
        active_documents: Array.isArray(activeDocuments) ? activeDocuments : null,
      }),
      signal: controller.signal,
    })

    if (res.ok && res.body) {
      clearTimeout(timeout)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() // keep unparsed remainder

        for (const block of blocks) {
          const lines = block.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const rawJson = line.slice(6).trim()
              if (!rawJson) continue
              try {
                const event = JSON.parse(rawJson)
                receivedAnyEvent = true

                switch (event.type) {
                  case 'start':
                    onStart?.(event)
                    break
                  case 'plan':
                    onPlan?.(event)
                    break
                  case 'route':
                    onRoute?.(event)
                    break
                  case 'memory':
                    onMemory?.(event)
                    break
                  case 'tool_call':
                    onToolCall?.(event)
                    break
                  case 'tool_result':
                    onToolResult?.(event)
                    break
                  case 'text_delta':
                    onTextDelta?.(event.text || '')
                    break
                  case 'approval_required':
                    onApprovalRequired?.(event)
                    break
                  case 'done':
                    onDone?.(event)
                    return { ok: true, ...event }
                  case 'error':
                    onError?.(event.message || 'Stream error occurred')
                    return { ok: false, error: event.message }
                  default:
                    break
                }
              } catch (parseErr) {
                console.warn('[SSE] JSON parse error:', parseErr, rawJson)
              }
            }
          }
        }
      }

      return { ok: true }
    } else {
      liveError = `The backend returned HTTP ${res.status}.`
    }
  } catch (err) {
    liveError =
      err?.name === 'AbortError'
        ? `The agent turn exceeded ${LIVE_TURN_TIMEOUT_MS / 1000}s and was cancelled.`
        : `Could not reach /api/chat/stream: ${err?.message || err}`
    console.warn('[API] Live /api/chat/stream failed:', err)
  }

  // If stream dropped mid-turn after starting
  if (receivedAnyEvent) {
    const streamErr = `Stream connection interrupted: ${liveError}`
    onError?.(streamErr)
    return { ok: false, error: streamErr }
  }

  // 2. The backend is reachable and it failed. Report failure honestly without faking data.
  if (await backendIsReachable()) {
    const failureMsg =
      `**The backend could not complete this turn.**\n\n` +
      `${liveError}\n\n` +
      `No simulated answer is being shown in its place: the backend is running, ` +
      `so anything displayed here would be mistaken for its output. ` +
      `Check the server log for the failing step.`
    onError?.(failureMsg)
    return { ok: false, error: failureMsg }
  }

  // 3. Backend genuinely absent — offline simulation, explicitly labelled as such.
  await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS))

  const isApprovalNeeded = isActionApprovalRequest(message)

  if (isApprovalNeeded) {
    const mockReply =
      `> ⚠️ **SIMULATED RESPONSE — the backend is not running.** Nothing below came from the corpus, a model, or a tool call. Start the backend to get real answers.\n\n` +
      `**Action Request Intercepted:** You commanded a critical operating parameter change: _"${message}"_\n\n` +
      `> 🛑 **Safety Interlock Gate [FR-15 / §3.12]:** Changing reactor feed rate from **100% (1,450 m³/h)** to **115% (1,667 m³/h)** exceeds the continuous design basis and requires manual human operator authorization before DCS controller FFC-201 can accept the parameter update.\n>\n` +
      `> A human approval gate modal has been displayed. Composer input is locked until this action is confirmed or cancelled.`

    onApprovalRequired?.({
      id: MOCK_FEED_RATE_APPROVAL_ACTION.id,
      name: 'DCS_SETPOINT_WRITE',
      arguments: { feed_rate: 115 },
      effect: MOCK_FEED_RATE_APPROVAL_ACTION.description,
      action: MOCK_FEED_RATE_APPROVAL_ACTION,
    })
    onTextDelta?.(mockReply)
    onDone?.({
      reply: mockReply,
      citations: MOCK_CITATIONS.slice(0, 2),
      plan: [],
      awaiting_approval: true,
      approval_action: MOCK_FEED_RATE_APPROVAL_ACTION,
      simulated: true,
    })
    return { ok: true, simulated: true }
  }

  const mockReply =
    `> ⚠️ **SIMULATED RESPONSE — the backend is not running.** Nothing below came from the corpus, a model, or a tool call. Start the backend to get real answers.\n\n` +
    buildMockReply(message)

  onRoute?.({
    type: 'route',
    path: 'simulated',
    reason: 'Backend offline. Showing local simulated demo response.',
    tools_expected: false,
  })
  onToolCall?.({
    type: 'tool_call',
    id: 'mock-search-1',
    name: 'search_documents',
    arguments: { query: message },
  })
  onToolResult?.({
    type: 'tool_result',
    id: 'mock-search-1',
    name: 'search_documents',
    output: { found: true, count: 4, note: 'Simulated passages from test corpus' },
    status: 'done',
    seconds: 0.15,
  })
  onTextDelta?.(mockReply)
  onDone?.({
    reply: mockReply,
    citations: MOCK_CITATIONS,
    plan: [],
    awaiting_approval: false,
    simulated: true,
  })
  return { ok: true, simulated: true }
}

/**
 * Backwards-compatible single-shot wrapper around sendMessageStream.
 */
export async function sendMessage(message, sessionId) {
  let reply = ''
  let citations = []
  let plan = []
  let tool_call_events = []
  let awaiting_human_approval = false
  let approval_action = null
  let isLive = true

  const res = await sendMessageStream(message, sessionId, {
    onRoute: () => {},
    onToolCall: (call) => {
      tool_call_events.push({
        id: call.id,
        tool_name: call.name,
        input_params: call.arguments,
        status: 'running',
      })
    },
    onToolResult: (resEv) => {
      const idx = tool_call_events.findIndex((e) => e.id === resEv.id)
      if (idx >= 0) {
        tool_call_events[idx] = {
          ...tool_call_events[idx],
          output: resEv.output,
          status: resEv.status,
          seconds: resEv.seconds,
        }
      }
    },
    onTextDelta: (delta) => {
      reply += delta
    },
    onApprovalRequired: (appEv) => {
      awaiting_human_approval = true
      approval_action = appEv.action || {
        id: appEv.id,
        title: 'Confirm Critical Parameter Modification',
        action_type: appEv.name || 'DCS_SETPOINT_WRITE',
        description: appEv.effect || 'Critical parameter change intercepted',
        arguments: appEv.arguments,
      }
    },
    onDone: (doneEv) => {
      if (doneEv.citations) citations = doneEv.citations
      if (doneEv.plan) plan = doneEv.plan
      if (doneEv.awaiting_approval !== undefined) awaiting_human_approval = doneEv.awaiting_approval
      if (doneEv.approval_action) approval_action = doneEv.approval_action
      if (doneEv.simulated) isLive = false
    },
    onError: (err) => {
      reply = err
    },
  })

  if (res?.simulated) isLive = false

  return {
    reply,
    citations,
    plan,
    tool_call_events,
    session_id: sessionId,
    awaiting_human_approval,
    approval_action,
    live: isLive,
    error: !res?.ok,
  }
}

