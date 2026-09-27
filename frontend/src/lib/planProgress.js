/**
 * planProgress.js — which plan step a tool call belongs to.
 *
 * The planner labels steps by AGENT (retrieval, math, code, reasoning);
 * tool events carry TOOL names. The step for a call was guessed from the
 * call id's prefix ("search-1" -> "search"), which never matched a step id
 * ("s1"), so every step stayed Pending and the Plan DAG read "0/2" after
 * the turn had finished. Pure: tested in planProgress.test.js.
 *
 * Honest by construction: a step is Done only when a call it owns
 * finished (or, for the reasoning step, when an answer was written); a
 * step nothing ran for ends as Skipped, never as Done.
 */

const TOOL_AGENT = [
  [/^(search_documents|search_images|get_document|graph_|query_graph|list_documents)/, 'retrieval'],
  [/^(evaluate_|analyse_trend|project_to_threshold|describe_series|catalyst_run_length|hydrogen_balance|lookup_thermophysical|psa_purity|plot_series|unit_)/, 'math'],
  [/^(run_generated_code|run_in_sandbox|execute_code)/, 'code'],
  [/^(ocr_|read_image|analyse_image|detect_|vision_|transcribe_)/, 'vision'],
]

export function agentForTool(name) {
  const n = String(name || '')
  for (const [re, agent] of TOOL_AGENT) if (re.test(n)) return agent
  return 'reasoning'
}

const idOf = (s) => s.step_id || s.id

/** A call started: the first waiting step of its agent runs. */
export function startStep(plan, toolName) {
  const agent = agentForTool(toolName)
  const step = (plan || []).find((s) => (s.status || 'pending') === 'pending' && (s.assigned_agent || 'reasoning') === agent)
  if (!step) return { plan, stepId: null }
  const stepId = idOf(step)
  return { plan: plan.map((s) => (idOf(s) === stepId ? { ...s, status: 'running' } : s)), stepId }
}

/** The call finished: its step is done, or failed. */
export function finishStep(plan, stepId, ok) {
  if (!stepId) return plan
  return (plan || []).map((s) => (idOf(s) === stepId ? { ...s, status: ok ? 'done' : 'failed' } : s))
}

/**
 * The turn ended. A still-running step finished with it; the reasoning
 * step that writes the answer is done when an answer exists; anything
 * nothing ran for is skipped.
 */
export function reconcilePlan(plan, { answered }) {
  return (plan || []).map((s) => {
    const status = s.status || 'pending'
    if (status === 'running') return { ...s, status: 'done' }
    if (status !== 'pending') return s
    if (answered && (s.assigned_agent || 'reasoning') === 'reasoning') return { ...s, status: 'done' }
    return { ...s, status: 'skipped' }
  })
}
