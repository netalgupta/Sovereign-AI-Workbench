import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

/**
 * sendMessageStream called `handlers.onDeckJob(...)` for the deck_job event,
 * and nothing named `handlers` existed. The ReferenceError was caught by the
 * try/catch around JSON.parse and logged as a "JSON parse error", so no
 * deck, report or spreadsheet started from the chat ever showed its progress
 * card or its Review button -- found by driving the real chat box.
 *
 * Every callback the stream reader calls must be one it destructured.
 */
const source = readFileSync(new URL('./api.js', import.meta.url), 'utf-8')
const start = source.indexOf('export async function sendMessageStream')
const end = source.indexOf('\nexport ', start + 10)
const body = source.slice(start, end === -1 ? undefined : end)

test('every stream callback that is called is one the function receives', () => {
  const destructured = new Set(body.slice(0, body.indexOf('} = callbacks')).match(/\bon[A-Z]\w+/g))
  const called = new Set([...body.matchAll(/\b(on[A-Z]\w+)\?\.\(/g)].map((m) => m[1]))
  for (const name of called) assert.ok(destructured.has(name), `${name} is called but never received`)
  assert.ok(!/\bhandlers\./.test(body), 'no reference to an undefined `handlers` object')
})

test('a deck_job event reaches its handler', () => {
  assert.match(body, /case 'deck_job':\s*onDeckJob\?\.\(event\)/)
})
