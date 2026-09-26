import { strict as assert } from 'node:assert'
import test from 'node:test'

import { latexToPlain, plainMath } from './plainMath.js'

test('the unit conversion measured in the chat UI reads as plain maths', () => {
  const raw = 'Working: \\[ 1450 \\, \\text{m}^3/\\text{hour} = 218885.4148110373 \\, \\text{barrel/day} \\]'
  const out = plainMath(raw)
  assert.ok(!out.includes('\\'), out)
  assert.ok(out.includes('1450 m³/hour = 218885.4148110373 barrel/day'), out)
})

test('fractions, times and nested text unwind', () => {
  assert.equal(latexToPlain('\\frac{1450}{86400} \\times 7.48'), '1450 / 86400 × 7.48')
  assert.equal(latexToPlain('\\frac{\\text{m}^3}{\\text{h}}'), 'm³ / h')
  assert.equal(latexToPlain('\\frac{a + b}{2}'), '(a + b) / 2')
})

test('code is never rewritten', () => {
  const md = 'Run this:\n```python\nprint("\\\\times \\\\frac{1}{2}")\n```\nand `\\text{x}` stays.'
  assert.equal(plainMath(md), md)
})

test('text without LaTeX is returned unchanged', () => {
  const md = 'The average MFI is 3.4 g/10min [1].'
  assert.equal(plainMath(md), md)
})
