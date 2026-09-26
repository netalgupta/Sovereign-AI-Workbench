import { strict as assert } from 'node:assert'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

/**
 * The same invented refinery payload has been removed from this frontend
 * six times: a feed-rate change on FFC-201 (1,450 -> 1,667 m3/h) as the
 * approval modal's fallback, again in the chat pane, again in api.js, a
 * "Setpoint retained at nominal" message after refusing a WORD DOCUMENT,
 * a DCS_SETPOINT_WRITE default label, and three built-in "deliverables"
 * on the Outputs page shown with download buttons when the backend was
 * empty or unreachable.
 *
 * Every instance looked reasonable where it sat -- a default, a fallback,
 * a sample. Together they mean the screen where a human signs off can
 * describe an action nobody requested, over numbers nobody measured.
 *
 * This test reads the source with comments stripped, so the history above
 * can be written down next to the code without tripping it.
 */

const SRC = join(import.meta.dirname, '..')

const BANNED = [
  ['1,450', 'invented feed rate'],
  ['1,667', 'invented feed rate'],
  ['FFC-201', 'invented controller tag'],
  ['HCU-2 /', 'invented target'],
  ['Setpoint retained at nominal', 'invented outcome after a refusal'],
  ['DCS_SETPOINT_WRITE', 'setpoint label applied to any action'],
  ['Confirm Critical Parameter Modification', 'invented approval title'],
  ['CANONICAL_OUTPUTS', 'built-in sample deliverables'],
  ['interlock monitoring active', 'invented control-room outcome after a file write'],
  ['accepted parameter update', 'setpoint language applied to any approval'],
]

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(jsx?|tsx?)$/.test(name) && !name.endsWith('.test.js') ? [full] : []
  })
}

function withoutComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*'))
    .join('\n')
}

test('no fabricated refinery payload survives in the frontend', () => {
  const offenders = []
  for (const file of sourceFiles(SRC)) {
    const code = withoutComments(readFileSync(file, 'utf8'))
    for (const [needle, why] of BANNED) {
      if (code.includes(needle)) offenders.push(`${file}: ${needle} (${why})`)
    }
  }
  assert.deepEqual(offenders, [], `fabricated payload is back:\n${offenders.join('\n')}`)
})
