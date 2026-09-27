/**
 * agentMapModel.js — the agent map's data, as a pure function (testable in Node).
 *
 * The latest assistant turn becomes a root node (model, path, elapsed,
 * tokens) and its model calls and tool calls, in the order they happened.
 * Tokens are Ollama's own counts; a count it did not report stays null.
 */

/** The latest turn, as nodes: the root agent and its steps in order. */
export function buildTurnMap(messages, now = Date.now()) {
  const idx = [...messages].map((m, i) => [m, i]).reverse().find(([m]) => m.role === 'assistant' && m.route)
  if (!idx) return null
  const [turn, i] = idx
  const request = [...messages.slice(0, i)].reverse().find((m) => m.role === 'user')?.content || ''
  const working = !turn.endedAt
  const llmCalls = Array.isArray(turn.llmCalls) ? turn.llmCalls : []
  const tools = Array.isArray(turn.toolCallEvents) ? turn.toolCallEvents : []
  const steps = [
    ...llmCalls.map((c, k) => ({
      key: `llm-${k}`,
      kind: 'model',
      title: `Model call ${c.iteration ?? k + 1}`,
      subtitle: c.model || '',
      status: 'done',
      seconds: c.seconds ?? null,
      tokens: c.prompt_tokens == null && c.output_tokens == null ? null : (c.prompt_tokens || 0) + (c.output_tokens || 0),
      at: c.receivedAt || 0,
      detail: c,
    })),
    ...tools.map((t, k) => ({
      key: `tool-${t.id || k}`,
      kind: 'tool',
      title: t.name || t.tool_name || 'tool',
      subtitle: t.status === 'running' ? 'running' : '',
      status: t.status || 'running',
      seconds: t.seconds ?? (t.startedAt ? ((t.endedAt || now) - t.startedAt) / 1000 : null),
      tokens: null,
      at: t.startedAt || 0,
      detail: t,
    })),
  ].sort((a, b) => a.at - b.at)
  const reported = llmCalls.filter((c) => c.prompt_tokens != null || c.output_tokens != null)
  const tokens = turn.usage
    ? (turn.usage.prompt_tokens || 0) + (turn.usage.output_tokens || 0)
    : reported.length
      ? reported.reduce((n, c) => n + (c.prompt_tokens || 0) + (c.output_tokens || 0), 0)
      : null
  return {
    root: {
      key: 'root',
      kind: 'root',
      title: request || 'This turn',
      subtitle: turn.route?.model
        ? `${turn.route.model} · ${String(turn.route.task || '').replace(/_/g, ' ')}`
        : `answered on the ${turn.route?.path || ''} path, no model`,
      status: working ? 'working' : 'done',
      seconds: turn.startedAt ? ((turn.endedAt || now) - turn.startedAt) / 1000 : turn.elapsedSeconds ?? null,
      tokens,
      detail: { request, route: turn.route, usage: turn.usage || null, plan: turn.plan || [] },
    },
    steps,
    working,
  }
}

