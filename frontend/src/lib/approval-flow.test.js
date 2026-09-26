import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { errorText } from './errorText.js'

/**
 * Approving a finished Word document or spreadsheet from the chat never
 * wrote it: /api/approvals/execute requires request_id AND token, the store
 * sent only the token, and every approval got a 422 -- since the two-step
 * approval was first wired up. The 422's `detail` is a list of objects; it
 * went into approvalError, React rendered an object, and the app went blank.
 */

test('the execute call sends the request id with the token', () => {
  const store = readFileSync(new URL('../store/chatStore.js', import.meta.url), 'utf-8')
  const call = store.slice(store.indexOf("fetch('/api/approvals/execute'"))
  const body = call.slice(0, call.indexOf('})') + 2)
  assert.match(body, /request_id:/, 'execute must send request_id')
  assert.match(body, /token:/, 'execute must send the token')
})

test('a FastAPI validation error becomes a sentence, never an object', () => {
  const body = { detail: [{ type: 'missing', loc: ['body', 'request_id'], msg: 'Field required', input: {} }] }
  const text = errorText(body, 'fallback')
  assert.equal(typeof text, 'string')
  assert.equal(text, 'request_id: Field required')
})

test('plain messages pass through, and nothing falls back to the default', () => {
  assert.equal(errorText({ detail: 'Approval expired' }, 'x'), 'Approval expired')
  assert.equal(errorText({}, 'HTTP 500'), 'HTTP 500')
  assert.equal(typeof errorText({ detail: { code: 7 } }, 'x'), 'string')
})
