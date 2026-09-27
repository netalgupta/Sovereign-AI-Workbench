import { strict as assert } from 'node:assert'
import test from 'node:test'

import { cleanPrompt, collectPrompts, stepHistory } from './promptHistory.js'

const u = (content) => ({ role: 'user', content })
const a = (content) => ({ role: 'assistant', content })

test('this chat first, newest first, then earlier chats; duplicates once', () => {
  const current = [u('first'), a('x'), u('second'), a('y')]
  const other = [[u('older chat q'), u('second')]]
  assert.deepEqual(collectPrompts(current, other), ['second', 'first', 'older chat q'])
})

test('attachment notes are not part of the prompt', () => {
  assert.equal(cleanPrompt('List all houses\n\nAttached: Best House 2026.xlsx'), 'List all houses')
  assert.equal(cleanPrompt('This file [Temporary Attachment: Tut 1.pdf]'), 'This file')
})

test('Up walks back, Down walks forward and restores the unsent draft', () => {
  const history = ['newest', 'older']
  let state = { index: -1, saved: '' }
  const press = (key, draft) => {
    const next = stepHistory({ key, draft, caretStart: 0, caretEnd: draft.length, history, state })
    if (next) state = next
    return next
  }
  assert.equal(press('ArrowUp', 'half typed').draft, 'newest')
  assert.equal(press('ArrowUp', 'newest').draft, 'older')
  assert.equal(press('ArrowUp', 'older'), null) // no further back
  assert.equal(press('ArrowDown', 'older').draft, 'newest')
  assert.equal(press('ArrowDown', 'newest').draft, 'half typed')
  assert.equal(press('ArrowDown', 'half typed'), null)
})

test('inside a multi-line draft the arrows move the caret instead', () => {
  const draft = 'line one\nline two'
  const state = { index: -1, saved: '' }
  // caret on the second line: Up must not replace the draft
  assert.equal(stepHistory({ key: 'ArrowUp', draft, caretStart: 12, caretEnd: 12, history: ['p'], state }), null)
})
