/**
 * backend-process.js — start the local services the app needs and wait
 * until they answer. Nothing here reaches beyond 127.0.0.1.
 *
 *   Ollama     the model server. Started if it is not already running.
 *   Backend    FastAPI (uvicorn) on 127.0.0.1:8000, which also serves the
 *              built frontend -- the window loads http://127.0.0.1:8000/.
 */

const { spawn } = require('child_process')
const fs = require('fs')
const http = require('http')
const path = require('path')

const BACKEND_URL = 'http://127.0.0.1:8000'
const OLLAMA_URL = 'http://127.0.0.1:11434'

// The Ollama settings measured on the 8 GB card (CLAUDE.md, "VRAM Discipline").
const OLLAMA_ENV = {
  OLLAMA_NUM_PARALLEL: '2',
  OLLAMA_FLASH_ATTENTION: '1',
  OLLAMA_KV_CACHE_TYPE: 'q8_0',
  OLLAMA_KEEP_ALIVE: '30m',
  OLLAMA_HOST: '127.0.0.1:11434',
}

function get(url, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume()
      resolve(res.statusCode >= 200 && res.statusCode < 500)
    })
    req.on('timeout', () => { req.destroy(); resolve(false) })
    req.on('error', () => resolve(false))
  })
}

async function waitFor(url, { timeoutMs, onTick }) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    if (await get(url)) return true
    onTick?.(Math.round((Date.now() - started) / 1000))
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

function ollamaExe() {
  const candidates = [
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Ollama', 'ollama.exe'),
    path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Ollama', 'ollama.exe'),
  ]
  return candidates.find((p) => p && fs.existsSync(p)) || 'ollama'
}

/**
 * @param {{appDir: string, python: string[], log: (line: string) => void, status: (text: string) => void}} o
 * @returns {Promise<{backend: import('child_process').ChildProcess|null, ollama: import('child_process').ChildProcess|null}>}
 */
async function startServices({ appDir, python, log, status }) {
  const children = { backend: null, ollama: null }

  status('Starting the local model server')
  if (!(await get(`${OLLAMA_URL}/api/tags`))) {
    children.ollama = spawn(ollamaExe(), ['serve'], {
      env: { ...process.env, ...OLLAMA_ENV },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    children.ollama.stdout.on('data', (d) => log(`[ollama] ${d}`))
    children.ollama.stderr.on('data', (d) => log(`[ollama] ${d}`))
    children.ollama.on('error', (e) => log(`[ollama] could not start: ${e.message}`))
    await waitFor(`${OLLAMA_URL}/api/tags`, { timeoutMs: 30000 })
  }

  status('Starting the workbench')
  if (!(await get(`${BACKEND_URL}/api/health`))) {
    const [exe, ...pre] = python
    children.backend = spawn(exe, [...pre, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'], {
      cwd: appDir,
      env: { ...process.env, ...OLLAMA_ENV, PYTHONIOENCODING: 'utf-8', HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1' },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    children.backend.stdout.on('data', (d) => log(`[backend] ${d}`))
    children.backend.stderr.on('data', (d) => log(`[backend] ${d}`))
    children.backend.on('error', (e) => log(`[backend] could not start: ${e.message}`))
  }
  const up = await waitFor(`${BACKEND_URL}/api/health`, {
    timeoutMs: 240000,
    onTick: (s) => status(s < 20 ? 'Starting the workbench' : `Loading local models (${s}s)`),
  })
  if (!up) throw new Error('The workbench did not start within 4 minutes. The log below says why.')
  return children
}

function stopServices(children) {
  for (const child of [children?.backend, children?.ollama]) {
    if (child && !child.killed) {
      try {
        // the whole process tree: uvicorn and anything it started
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
      } catch {
        child.kill()
      }
    }
  }
}

module.exports = { startServices, stopServices, BACKEND_URL, OLLAMA_ENV, get }
