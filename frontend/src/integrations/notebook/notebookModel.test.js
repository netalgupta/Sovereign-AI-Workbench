import { strict as assert } from 'node:assert'
import test from 'node:test'

import { buildCells } from './notebookModel.js'

test('calculations and programs become cells; searches and running calls do not', () => {
  const messages = [
    {
      id: 'm1',
      role: 'assistant',
      toolCallEvents: [
        { id: 'a', name: 'search_documents', status: 'done', output: {} },
        {
          id: 'b', name: 'evaluate_unit_expression', status: 'done', seconds: 0.01,
          arguments: { expression: '1450 m**3/hr', target_unit: 'bbl/day' },
          output: { result_magnitude: 218885.41, result_unit: 'oil_barrel / day', steps: ['1450 m3/h'] },
        },
        { id: 'c', name: 'evaluate_expression', status: 'running' },
      ],
    },
    {
      id: 'm2',
      role: 'assistant',
      toolCallEvents: [{ id: 'code-1', name: 'run_generated_code', status: 'done', arguments: { task: 'fib' },
        output: { code: 'print(1)', stdout: '1', model: 'qwen2.5-coder:7b' } }],
    },
  ]
  const cells = buildCells(messages)
  assert.deepEqual(cells.map((c) => [c.kind, c.tool]), [['calc', 'evaluate_unit_expression'], ['code', 'run_generated_code']])
  assert.equal(cells[0].result, '218885.41 oil_barrel / day')
  assert.equal(cells[0].title, 'Unit conversion')
})

test('an empty chat has no cells', () => {
  assert.deepEqual(buildCells([]), [])
})
