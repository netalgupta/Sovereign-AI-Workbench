/**
 * installer.js — puts every component on this machine from the drive's
 * payload, one step at a time, reporting real progress (bytes copied,
 * packages installed, lines of output), never an invented percentage.
 *
 * Steps, in order (each skips itself when already done, so a second run
 * repairs rather than repeats):
 *
 *   verify   the payload's manifest is there and every component it lists
 *   python   Python from its installer, then every package from the
 *            wheelhouse with pip --no-index (nothing downloaded)
 *   ollama   Ollama from its installer, then the registered models
 *   app      the workbench: backend, built frontend, model caches, corpora
 *   shell    this desktop app, so the installed copy runs without the drive
 *   settings Ollama's measured settings, the install marker, a shortcut
 *   index    the search index built once, so the first question is fast
 */

const { spawn, execFile } = require('child_process')
const fs = require('fs')
const os = require('os')
const path = require('path')

const OLLAMA_SETTINGS = {
  OLLAMA_NUM_PARALLEL: '2',
  OLLAMA_FLASH_ATTENTION: '1',
  OLLAMA_KV_CACHE_TYPE: 'q8_0',
  OLLAMA_KEEP_ALIVE: '30m',
}

// ── machine check ──────────────────────────────────────────────────────────
function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { windowsHide: true, timeout: 8000, ...opts }, (err, stdout) => resolve(err ? null : String(stdout)))
  })
}

async function freeBytes(dir) {
  try {
    let probe = dir
    while (probe && !fs.existsSync(probe)) probe = path.dirname(probe)
    const s = await fs.promises.statfs(probe || os.homedir())
    return Number(s.bavail) * Number(s.bsize)
  } catch {
    return null
  }
}

async function checkMachine() {
  const gpuOut = await run('nvidia-smi', ['--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'])
  const gpus = (gpuOut || '').trim().split(/\r?\n/).filter(Boolean).map((line) => {
    const [name, mem, driver] = line.split(',').map((s) => s.trim())
    return { name, vramGB: Math.round((Number(mem) / 1024) * 10) / 10, driver }
  })
  const ollama = [
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Ollama', 'ollama.exe'),
    path.join(process.env.ProgramFiles || '', 'Ollama', 'ollama.exe'),
  ].find((p) => fs.existsSync(p))
  const docker = await run('docker', ['info', '--format', '{{.ServerVersion}}'])
  return {
    os: `${os.type()} ${os.release()}`,
    cpu: os.cpus()[0]?.model?.trim() || 'unknown',
    cores: os.cpus().length,
    ramGB: Math.round(os.totalmem() / 1e9),
    gpus,
    ollamaInstalled: Boolean(ollama),
    dockerRunning: Boolean(docker && docker.trim()),
  }
}

// ── helpers ────────────────────────────────────────────────────────────────
function walk(dir) {
  const out = []
  const stack = [dir]
  while (stack.length) {
    const d = stack.pop()
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, entry.name)
      if (entry.isDirectory()) stack.push(p)
      else if (entry.isFile()) out.push(p)
    }
  }
  return out
}

/** Copy a tree, reporting bytes. A file already there with the same size is skipped. */
async function copyTree(src, dst, onBytes) {
  const files = walk(src)
  const total = files.reduce((n, f) => n + fs.statSync(f).size, 0)
  let done = 0
  for (const file of files) {
    const target = path.join(dst, path.relative(src, file))
    const size = fs.statSync(file).size
    if (fs.existsSync(target) && fs.statSync(target).size === size) {
      done += size
      onBytes(done, total)
      continue
    }
    fs.mkdirSync(path.dirname(target), { recursive: true })
    await new Promise((resolve, reject) => {
      const rd = fs.createReadStream(file, { highWaterMark: 4 << 20 })
      const wr = fs.createWriteStream(target + '.part')
      let last = Date.now()
      rd.on('data', (chunk) => {
        done += chunk.length
        if (Date.now() - last > 120) {
          onBytes(done, total)
          last = Date.now()
        }
      })
      rd.on('error', reject)
      wr.on('error', reject)
      wr.on('finish', resolve)
      rd.pipe(wr)
    })
    fs.renameSync(target + '.part', target)
    onBytes(done, total)
  }
  return { files: files.length, bytes: total }
}

/** Run a process, streaming its output lines to `onLine`. Resolves with the exit code. */
function stream(cmd, args, { cwd, env, onLine }) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { cwd, env: { ...process.env, ...env }, windowsHide: true })
    const split = (buf) => String(buf).split(/\r?\n/).forEach((l) => l.trim() && onLine(l))
    child.stdout.on('data', split)
    child.stderr.on('data', split)
    child.on('error', reject)
    child.on('close', resolve)
  })
}

function findFile(dir, pattern) {
  if (!fs.existsSync(dir)) return null
  const hit = fs.readdirSync(dir).find((n) => pattern.test(n))
  return hit ? path.join(dir, hit) : null
}

// ── the steps ──────────────────────────────────────────────────────────────
const STEPS = [
  { id: 'verify', title: 'Checking the package' },
  { id: 'python', title: 'Python and its packages' },
  { id: 'ollama', title: 'Ollama and the models' },
  { id: 'app', title: 'The workbench' },
  { id: 'shell', title: 'The desktop app' },
  { id: 'settings', title: 'Settings and shortcut' },
  { id: 'index', title: 'Building the search index' },
]

async function install({ payload, installDir, send, log, shellDir }) {
  const manifest = JSON.parse(fs.readFileSync(path.join(payload, 'manifest.json'), 'utf8'))
  const component = (id) => manifest.components.find((c) => c.id === id)
  const report = (id, fields) => send({ step: id, ...fields })
  const started = Date.now()
  fs.mkdirSync(installDir, { recursive: true })
  const python = path.join(installDir, 'python', 'python.exe')

  const steps = {
    async verify() {
      const missing = ['python', 'ollama', 'app'].filter((id) => !component(id) || !fs.existsSync(path.join(payload, id)))
      if (missing.length) throw new Error(`The package is incomplete: ${missing.join(', ')} missing from payload/.`)
      const need = manifest.components.reduce((n, c) => n + (c.bytes || 0), 0)
      const free = await freeBytes(installDir)
      if (free != null && free < need * 1.1) {
        throw new Error(`Not enough space: ${(need / 1e9).toFixed(1)} GB needed, ${(free / 1e9).toFixed(1)} GB free.`)
      }
      return `${manifest.components.length} components, ${(need / 1e9).toFixed(1)} GB`
    },

    async python() {
      const dir = path.join(payload, 'python')
      if (!fs.existsSync(python)) {
        const exe = findFile(dir, /^python-.*\.exe$/i)
        if (!exe) throw new Error('No Python installer in payload/python/.')
        report('python', { detail: `Installing ${path.basename(exe)}` })
        const code = await stream(exe, ['/quiet', 'InstallAllUsers=0', `TargetDir=${path.join(installDir, 'python')}`,
          'Include_launcher=0', 'Include_test=0', 'PrependPath=0', 'Shortcuts=0', 'AssociateFiles=0'],
        { onLine: log })
        if (code !== 0 || !fs.existsSync(python)) throw new Error(`The Python installer stopped with code ${code}.`)
      }
      const wheels = walk(path.join(dir, 'wheels')).length
      let seen = 0
      const code = await stream(python, ['-m', 'pip', 'install', '--no-index', '--disable-pip-version-check',
        '--find-links', path.join(dir, 'wheels'), '-r', path.join(dir, 'requirements-lock.txt')], {
        onLine: (line) => {
          log(`[pip] ${line}`)
          if (/^(Processing|Requirement already satisfied)/.test(line)) {
            seen += 1
            report('python', { done: Math.min(seen, wheels), total: wheels, unit: 'packages', detail: line.slice(0, 90) })
          }
        },
      })
      if (code !== 0) throw new Error(`pip stopped with code ${code}. The log shows the package it could not install.`)
      return `${wheels} packages installed offline`
    },

    async ollama() {
      const dir = path.join(payload, 'ollama')
      const machine = await checkMachine()
      if (!machine.ollamaInstalled) {
        const exe = findFile(dir, /ollama.*setup.*\.exe$/i)
        if (!exe) throw new Error('No OllamaSetup.exe in payload/ollama/.')
        report('ollama', { detail: 'Installing Ollama' })
        const code = await stream(exe, ['/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES'], { onLine: log })
        if (code !== 0) throw new Error(`The Ollama installer stopped with code ${code}.`)
      }
      const target = path.join(os.homedir(), '.ollama', 'models')
      const res = await copyTree(path.join(dir, 'models'), target, (done, total) =>
        report('ollama', { done, total, unit: 'bytes', detail: 'Copying the registered models' }))
      const models = component('ollama')?.models || []
      return `${models.length} models (${(res.bytes / 1e9).toFixed(1)} GB)`
    },

    async app() {
      const res = await copyTree(path.join(payload, 'app'), path.join(installDir, 'app'), (done, total) =>
        report('app', { done, total, unit: 'bytes', detail: 'Backend, interface, model caches and corpora' }))
      return `${res.files} files`
    },

    async shell() {
      // the running desktop app itself, so the installed copy does not need the drive
      const res = await copyTree(shellDir, path.join(installDir, 'shell'), (done, total) =>
        report('shell', { done, total, unit: 'bytes', detail: 'Sovereign Workbench desktop app' }))
      return `${res.files} files`
    },

    async settings() {
      for (const [key, value] of Object.entries(OLLAMA_SETTINGS)) {
        await run('setx', [key, value])
        log(`[settings] ${key}=${value}`)
      }
      fs.writeFileSync(path.join(installDir, 'installed.json'),
        JSON.stringify({ installedAt: new Date().toISOString(), payload: manifest.built }, null, 2))
      const { shell } = require('electron')
      const exe = walk(path.join(installDir, 'shell')).find((f) => /Sovereign Workbench.*\.exe$/i.test(f))
      if (exe) {
        const desktop = path.join(os.homedir(), 'Desktop', 'Sovereign Workbench.lnk')
        shell.writeShortcutLink(desktop, { target: exe, description: 'Sovereign Workbench', icon: exe, iconIndex: 0 })
        return 'Ollama settings saved · desktop shortcut created'
      }
      return 'Ollama settings saved'
    },

    async index() {
      let lines = 0
      const code = await stream(python, ['-c',
        'from backend.api.state import get_state; s, c = get_state().ensure_corpus(); print(f"INDEXED {len(c)} passages")'],
      {
        cwd: path.join(installDir, 'app'),
        env: { PYTHONIOENCODING: 'utf-8', HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', ...OLLAMA_SETTINGS },
        onLine: (line) => {
          lines += 1
          log(`[index] ${line}`)
          report('index', { detail: line.slice(0, 90), done: lines, unit: 'lines' })
        },
      })
      if (code !== 0) throw new Error(`Indexing stopped with code ${code}.`)
      return 'Ready'
    },
  }

  for (const step of STEPS) {
    const t0 = Date.now()
    report(step.id, { status: 'running' })
    try {
      const summary = await steps[step.id]()
      report(step.id, { status: 'done', summary, seconds: Math.round((Date.now() - t0) / 1000) })
    } catch (err) {
      report(step.id, { status: 'failed', error: err.message, seconds: Math.round((Date.now() - t0) / 1000) })
      throw err
    }
  }
  return { seconds: Math.round((Date.now() - started) / 1000) }
}

module.exports = { checkMachine, freeBytes, install, STEPS }
