/**
 * notebookModel.js — the chat's calculations and programs as notebook cells.
 * Pure, so it is tested in Node (notebookModel.test.js).
 */

// The registry's "computation" category: every tool here is ungated, so a
// cell can be re-run through /api/tools/call without an approval.
export const COMPUTATION_TOOLS = new Set([
  'evaluate_expression', 'evaluate_unit_expression', 'analyse_trend', 'project_to_threshold',
  'describe_series', 'catalyst_run_length', 'hydrogen_balance', 'lookup_thermophysical_property',
  'psa_purity_compliance', 'graph_analytics', 'plot_series',
])

const TITLES = {
  evaluate_expression: 'Calculation',
  evaluate_unit_expression: 'Unit conversion',
  analyse_trend: 'Trend analysis',
  project_to_threshold: 'Projection to a limit',
  describe_series: 'Series statistics',
  catalyst_run_length: 'Catalyst run length',
  hydrogen_balance: 'Hydrogen balance',
  lookup_thermophysical_property: 'Thermophysical property',
  psa_purity_compliance: 'PSA purity compliance',
  graph_analytics: 'Graph analytics',
  plot_series: 'Plot',
  run_generated_code: 'Program',
}

export function buildCells(messages) {
  const cells = []
  for (const m of messages || []) {
    for (const t of m.toolCallEvents || []) {
      const tool = t.name || t.tool_name
      const isCode = tool === 'run_generated_code'
      if (!isCode && !COMPUTATION_TOOLS.has(tool)) continue
      if (t.status === 'running') continue
      const out = t.output
      cells.push({
        key: `${m.id}-${t.id}`,
        kind: isCode ? 'code' : 'calc',
        tool,
        title: TITLES[tool] || tool,
        arguments: t.arguments || t.input_params || {},
        output: out,
        result:
          out && typeof out === 'object'
            ? out.result_magnitude != null
              ? `${out.result_magnitude} ${out.result_unit || ''}`.trim()
              : out.result ?? out.value ?? null
            : out ?? null,
        status: t.status || 'done',
        seconds: t.seconds ?? null,
      })
    }
  }
  return cells
}
