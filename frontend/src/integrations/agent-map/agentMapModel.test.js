import { strict as assert } from 'node:assert'
import test from 'node:test'

import { buildTurnMap } from './agentMapModel.js'

const user = { role: 'user', content: 'What is the MFI of H030SG?' }

test('the latest turn is the root, with its model and tool calls in order', () => {
  const turn = {
    role: 'assistant',
    route: { model: 'qwen2.5:7b', task: 'question_answering', path: 'direct' },
    startedAt: 1000,
    endedAt: 6000,
    usage: { prompt_tokens: 1866, output_tokens: 202, llm_calls: 1 },
    toolCallEvents: [{ id: 't1', name: 'search_documents', status: 'done', seconds: 1.1, startedAt: 1100 }],
    llmCalls: [{ iteration: 1, model: 'qwen2.5:7b', prompt_tokens: 1866, output_tokens: 202, seconds: 4.1, receivedAt: 5900 }],
  }
  const map = buildTurnMap([user, turn], 7000)
  assert.equal(map.root.title, 'What is the MFI of H030SG?')
  assert.equal(map.root.seconds, 5)
  assert.equal(map.root.tokens, 2068)
  assert.equal(map.root.status, 'done')
  assert.deepEqual(map.steps.map((s) => s.kind), ['tool', 'model'])
})

test('tokens Ollama did not report are absent, not zero', () => {
  const turn = {
    role: 'assistant', route: { model: 'qwen2.5:7b', path: 'agentic' }, startedAt: 0,
    llmCalls: [{ iteration: 1, model: 'qwen2.5:7b', prompt_tokens: null, output_tokens: null, seconds: 2, receivedAt: 1 }],
  }
  const map = buildTurnMap([user, turn], 3000)
  assert.equal(map.steps[0].tokens, null)
  assert.equal(map.root.tokens, null)
  assert.equal(map.working, true)
})

test('an instant reply names no model', () => {
  const turn = { role: 'assistant', route: { path: 'unclear', model: null }, startedAt: 0, endedAt: 400 }
  const map = buildTurnMap([user, turn], 500)
  assert.match(map.root.subtitle, /no model/)
  assert.equal(map.steps.length, 0)
})

test('no turn yet is no map', () => {
  assert.equal(buildTurnMap([user]), null)
})
