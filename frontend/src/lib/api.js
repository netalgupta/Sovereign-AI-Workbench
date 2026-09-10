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
const MOCK_CITATIONS = [
  {
    id: 1,
    doc: 'HCU_Operations_Manual.pdf',
    section: 'Section 4.2 — Feed Rate Operating Limits',
    passage:
      'The design-basis feed rate for the Hydrocracking Unit (HCU-2) shall not exceed 110 % of the nameplate capacity (Q_d = 1,450 m³/h) under any continuous operating mode. Exceedance for more than 15 minutes triggers an automatic interlock via the DCS feed-forward controller (FFC-201).',
  },
  {
    id: 2,
    doc: 'Safety_Guidelines_2024.docx',
    section: 'Page 14 — High-Temperature Catalyst Runaway Prevention',
    passage:
      'Operating at elevated feed rates increases LHSV (Liquid Hourly Space Velocity) which reduces residence time. At LHSV > 1.8 h⁻¹, exothermic quench reactions become thermally unstable; H₂/HC ratio must be maintained above 1,000 Nm³/m³ to suppress runaway. See Table 3-A for alarm setpoints.',
  },
  {
    id: 3,
    doc: 'Emissions_Regulations_2024.pdf',
    section: 'Section 9 — Downstream Fractionation Column Flooding Criteria',
    passage:
      'Column flooding is defined as the condition where liquid entrainment rate exceeds 10 % of vapour flow. At feed rates above 110 % of design capacity, flooding probability increases to 34 % based on the correlation: F_factor = u_v × √ρ_v. Immediate operator intervention is required per MOC procedure.',
  },
  {
    id: 4,
    doc: 'Historical_Trend_Data.csv',
    section: 'Row 1042–1090 — Thermocouple Array TC-201 (4 Shifts)',
    passage:
      'TC-201A: 381.4 °C · TC-201B: 382.1 °C · TC-201C: 383.0 °C · TC-201D: 380.9 °C · TC-201E: 382.6 °C · TC-201F: 381.7 °C. Rolling average across 6 sensors: 381.95 °C. Upper operating limit: 400 °C. Rate-of-change: +0.4 °C/hr (well within ±2.0 °C/hr threshold).',
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

### Operational Risk Assessment

Increasing the HCU feed rate beyond 110 % design capacity introduces three compounding risks: thermal runaway in the catalyst bed, H₂ compressor capacity saturation, and fractionation column flooding. [1][2]

The key safety constraint is the feed-forward interlock (FFC-201) which activates at sustained exceedance. Operating above this threshold reduces catalyst residency time and risks exothermic runaway. [2]

### Current Reactor Inlet Temperatures

Based on the latest thermocouple array readings (4-shift average): [4]

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
# Feed-rate guard — per SOP-HCU-412 §4.3
if feed_rate > 1.10 * design_capacity:
    alert("High risk: exceeds 110% design threshold")
    suggest_mitigation(cool_quench=True)

# Catalyst bed temperature check
if inlet_temp > 395:  # 5°C early-warning headroom
    trigger_alarm(level="WARNING", channel="TC-201")
\`\`\`

> ⚠️ **Operator note:** If feed rate must exceed 110 % for operational reasons, engage the quench flow controller (QFC-18) first and increase the H₂/HC ratio above 1,000 Nm³/m³ before any ramp. [3]`
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

export async function checkBackendHealth() {
  // Always "online" — this IS the backend for now, by design, not a fallback.
  return { ok: true }
}

export async function sendMessage(message, sessionId) {
  await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS))
  return {
    reply: buildMockReply(message),
    citations: MOCK_CITATIONS,
    plan: MOCK_PLAN_STEPS,
    session_id: sessionId,
  }
}

