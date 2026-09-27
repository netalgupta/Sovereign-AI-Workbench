import { strict as assert } from 'node:assert'
import test from 'node:test'

import { extractCodeFiles } from './codeFiles.js'
import { crc32, makeZip } from './zip.js'

const FENCE = '```'

test('files named in every shape models use are found, in order', () => {
  const md = [
    'Here is the service.',
    '',
    'File: app/main.py',
    FENCE + 'python',
    'print("hi")',
    FENCE,
    '**config.yaml**',
    FENCE + 'yaml',
    'port: 8080',
    FENCE,
    FENCE + 'toml title="pyproject.toml"',
    '[project]',
    FENCE,
    FENCE + 'bash',
    'echo unnamed',
    FENCE,
  ].join('\n')
  const files = extractCodeFiles(md)
  assert.deepEqual(files.map((f) => f.name), ['app/main.py', 'config.yaml', 'pyproject.toml'])
  assert.equal(files[0].content, 'print("hi")\n')
})

test('an answer with no named blocks offers no files', () => {
  assert.deepEqual(extractCodeFiles('text\n' + FENCE + 'python\nx = 1\n' + FENCE), [])
  assert.deepEqual(extractCodeFiles('no code at all'), [])
})

test('the zip is well formed: signatures, CRC, entry count', () => {
  assert.equal(crc32(new TextEncoder().encode('hello')), 0x3610a686)
  const zip = makeZip([{ name: 'a.txt', content: 'hello' }, { name: 'dir/b.yaml', content: 'k: v\n' }], new Date(2026, 8, 27, 12, 0, 0))
  const view = new DataView(zip.buffer)
  assert.equal(view.getUint32(0, true), 0x04034b50) // first local header
  const eocd = zip.length - 22
  assert.equal(view.getUint32(eocd, true), 0x06054b50)
  assert.equal(view.getUint16(eocd + 10, true), 2) // entries
  assert.equal(view.getUint32(14, true), 0x3610a686) // CRC of a.txt in its header
})

test('files without an extension are files too: Dockerfile, .env', () => {
  const md = ['File: app.py', FENCE + 'python', 'x = 1', FENCE, 'File: Dockerfile', FENCE + 'dockerfile', 'FROM python:3.12', FENCE,
    '**.env**', FENCE, 'PORT=8080', FENCE].join('\n')
  assert.deepEqual(extractCodeFiles(md).map((f) => f.name), ['app.py', 'Dockerfile', '.env'])
})
