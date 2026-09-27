import { strict as assert } from 'node:assert'
import test from 'node:test'

import { agentForTool, finishStep, reconcilePlan, startStep } from './planProgress.js'

const plan = [
  { step_id: 's1', assigned_agent: 'retrieval', status: 'pending' },
  { step_id: 's2', assigned_agent: 'math', status: 'pending' },
  { step_id: 's3', assigned_agent: 'reasoning', status: 'pending' },
]

test('tools map to the agents the planner names', () => {
  assert.equal(agentForTool('search_documents'), 'retrieval')
  assert.equal(agentForTool('evaluate_expression'), 'math')
  assert.equal(agentForTool('run_generated_code'), 'code')
  assert.equal(agentForTool('draft_docx'), 'reasoning')
})

test('a finished turn reads as finished: 3/3, not 0/3', () => {
  let p = plan
  let r = startStep(p, 'search_documents'); p = r.plan
  assert.equal(p[0].status, 'running')
  p = finishStep(p, r.stepId, true)
  r = startStep(p, 'evaluate_expression'); p = finishStep(r.plan, r.stepId, true)
  p = reconcilePlan(p, { answered: true })
  assert.deepEqual(p.map((s) => s.status), ['done', 'done', 'done'])
})

test('a step nothing ran for is skipped, never done', () => {
  let r = startStep(plan, 'search_documents')
  let p = finishStep(r.plan, r.stepId, true)
  p = reconcilePlan(p, { answered: true })
  assert.deepEqual(p.map((s) => s.status), ['done', 'skipped', 'done'])
})

test('a failed call fails its step; no answer leaves reasoning skipped', () => {
  const r = startStep(plan, 'evaluate_expression')
  let p = finishStep(r.plan, r.stepId, false)
  p = reconcilePlan(p, { answered: false })
  assert.deepEqual(p.map((s) => s.status), ['skipped', 'failed', 'skipped'])
})
