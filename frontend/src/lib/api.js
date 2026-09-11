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
  // Always "online" — this IS the backend for now, by design, not a fallback.
  return { ok: true }
}

export async function sendMessage(message, sessionId) {
  await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS))

  const isApprovalNeeded = isActionApprovalRequest(message)

  if (isApprovalNeeded) {
    return {
      reply: `**Action Request Intercepted:** You commanded a critical operating parameter change: _"${message}"_

> 🛑 **Safety Interlock Gate [FR-15 / §3.12]:** Changing reactor feed rate from **100% (1,450 m³/h)** to **115% (1,667 m³/h)** exceeds the continuous design basis and requires manual human operator authorization before DCS controller FFC-201 can accept the parameter update.
>
> A human approval gate modal has been displayed. Composer input is locked until this action is confirmed or cancelled.`,
      citations: MOCK_CITATIONS.slice(0, 2),
      plan: MOCK_PLAN_STEPS,
      session_id: sessionId,
      awaiting_human_approval: true,
      approval_action: MOCK_FEED_RATE_APPROVAL_ACTION,
    }
  }

  return {
    reply: buildMockReply(message),
    citations: MOCK_CITATIONS,
    plan: MOCK_PLAN_STEPS,
    session_id: sessionId,
    awaiting_human_approval: false,
    approval_action: null,
  }
}

