/**
 * Sovereign Workbench — the desktop shell.
 *
 * One executable, two jobs:
 *
 *   SETUP (first run, or --setup): a guided installer that puts every
 *     component on this machine from the drive it was run from -- Python
 *     and its packages, Ollama and the registered models, the app and its
 *     model caches -- then builds the search index. No network needed.
 *
 *   APP (every run after): starts Ollama and the backend on 127.0.0.1,
 *     waits until they answer, and opens the workbench.
 *
 * OFFLINE IS ENFORCED HERE, not assumed: every request any window makes
 * is refused unless it goes to 127.0.0.1 / localhost (or is a local
 * file, data: or blob: URL). A dependency that tries to phone home fails
 * visibly in the log instead of succeeding quietly.
 *
 * --dev runs the app against the repo this file sits in (py -3 from the
 * repo root), for development without installing.
 */

const { app, BrowserWindow, dialog, ipcMain, session, shell } = require('electron')
const fs = require('fs')
const path = require('path')

const { startServices, stopServices, BACKEND_URL } = require('./backend-process')
const installer = require('./installer')

const ARGS = new Set(process.argv.slice(1))
const DEV = ARGS.has('--dev')
const REPO = path.resolve(__dirname, '..')
// Where the drive's payload is: next to the portable .exe, or in the repo for --dev/--setup testing.
const BUNDLE_DIR = process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(app.getPath('exe'))
const PAYLOAD_CANDIDATES = [path.join(BUNDLE_DIR, 'payload'), path.join(REPO, 'payload')]
const CONFIG_FILE = path.join(app.getPath('userData'), 'install.json')
// Smoke test: --capture=<file.png> saves the window once it shows, then quits.
const CAPTURE = process.argv.find((a) => a.startsWith('--capture='))?.slice('--capture='.length)
const SCREEN = process.argv.find((a) => a.startsWith('--screen='))?.slice('--screen='.length)

function maybeCapture(win, delay) {
  if (!CAPTURE) return
  setTimeout(async () => {
    try {
      if (SCREEN) await win.webContents.executeJavaScript(`document.querySelector('[data-go="${SCREEN}"]')?.click()`)
      await new Promise((r) => setTimeout(r, 600))
      const img = await win.webContents.capturePage()
      fs.writeFileSync(CAPTURE, img.toPNG())
    } finally {
      app.quit()
    }
  }, delay)
}

let children = null
let mainWindow = null
const logLines = []

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'))
  } catch {
    return null
  }
}

function writeConfig(cfg) {
  fs.mkdirSync(path.dirname(CONFIG_FILE), { recursive: true })
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2))
}

function payloadDir() {
  return PAYLOAD_CANDIDATES.find((p) => fs.existsSync(path.join(p, 'manifest.json'))) || null
}

// ── offline, enforced ──────────────────────────────────────────────────────
const LOCAL = /^(https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/|$)|file:|data:|blob:|devtools:)/i

function lockToLoopback(ses) {
  ses.webRequest.onBeforeRequest((details, callback) => {
    const allowed = LOCAL.test(details.url)
    if (!allowed) log(`[offline] refused a request to ${details.url}`)
    callback({ cancel: !allowed })
  })
  ses.setPermissionRequestHandler((_wc, permission, callback) => {
    // the chat's voice notes need the microphone; nothing else is granted
    callback(permission === 'media')
  })
}

function log(line) {
  const text = String(line).replace(/\s+$/, '')
  if (!text) return
  logLines.push(text)
  if (logLines.length > 2000) logLines.shift()
  for (const w of BrowserWindow.getAllWindows()) w.webContents.send('log', text)
}

// ── windows ────────────────────────────────────────────────────────────────
function baseWindow(opts) {
  return new BrowserWindow({
    backgroundColor: '#0F141B',
    show: false,
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true },
    ...opts,
  })
}

function openSetup() {
  const win = baseWindow({ width: 1080, height: 720, minWidth: 900, minHeight: 620, title: 'Sovereign Workbench Setup' })
  win.loadFile(path.join(__dirname, 'setup', 'index.html'))
  win.once('ready-to-show', () => {
    win.show()
    maybeCapture(win, 2500)
  })
  mainWindow = win
}

async function launchApp(cfg) {
  const splash = baseWindow({ width: 520, height: 340, frame: false, resizable: false, title: 'Sovereign Workbench' })
  splash.loadFile(path.join(__dirname, 'splash.html'))
  splash.once('ready-to-show', () => splash.show())
  const status = (text) => !splash.isDestroyed() && splash.webContents.send('status', text)

  const appDir = DEV ? REPO : path.join(cfg.installDir, 'app')
  const python = DEV ? ['py', '-3'] : [path.join(cfg.installDir, 'python', 'python.exe')]
  try {
    children = await startServices({ appDir, python, log, status })
  } catch (err) {
    status(err.message)
    splash.webContents.send('failed', { message: err.message, log: logLines.slice(-40) })
    return
  }

  const win = baseWindow({ width: 1480, height: 920, minWidth: 1100, minHeight: 700, title: 'Sovereign Workbench' })
  win.maximize()
  win.loadURL(`${BACKEND_URL}/`)
  win.once('ready-to-show', () => {
    win.show()
    if (!splash.isDestroyed()) splash.close()
    maybeCapture(win, 5000)
  })
  // links to other sites are not opened (there is no network to open them on)
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (LOCAL.test(url)) return { action: 'allow' }
    log(`[offline] did not open ${url}`)
    return { action: 'deny' }
  })
  mainWindow = win
}

// ── setup IPC ──────────────────────────────────────────────────────────────
ipcMain.handle('setup:info', async () => {
  const payload = payloadDir()
  const cfg = readConfig()
  return {
    payload,
    manifest: payload ? JSON.parse(fs.readFileSync(path.join(payload, 'manifest.json'), 'utf8')) : null,
    defaultDir: cfg?.installDir || path.join(process.env.LOCALAPPDATA || app.getPath('home'), 'SovereignWorkbench'),
    machine: await installer.checkMachine(),
    version: app.getVersion(),
  }
})

ipcMain.handle('setup:chooseDir', async (_e, current) => {
  const res = await dialog.showOpenDialog(mainWindow, {
    title: 'Where should Sovereign Workbench be installed?',
    defaultPath: current,
    properties: ['openDirectory', 'createDirectory'],
  })
  if (res.canceled || !res.filePaths[0]) return null
  return { dir: res.filePaths[0], free: await installer.freeBytes(res.filePaths[0]) }
})

ipcMain.handle('setup:freeBytes', async (_e, dir) => installer.freeBytes(dir))

ipcMain.handle('setup:run', async (event, installDir) => {
  const payload = payloadDir()
  if (!payload) throw new Error('No payload folder was found next to this program.')
  const send = (msg) => event.sender.send('setup:progress', msg)
  const result = await installer.install({ payload, installDir, send, log, shellDir: path.dirname(process.execPath) })
  writeConfig({ installDir, installedAt: new Date().toISOString(), version: app.getVersion() })
  return result
})

ipcMain.handle('setup:launch', async () => {
  const cfg = readConfig()
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close()
  await launchApp(cfg)
})

ipcMain.handle('app:log', () => logLines.slice(-200))
ipcMain.handle('app:openLogFolder', () => shell.openPath(app.getPath('userData')))

// ── lifecycle ──────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  lockToLoopback(session.defaultSession)
  const cfg = readConfig()
  const installed = cfg?.installDir && fs.existsSync(path.join(cfg.installDir, 'installed.json'))
  if (DEV) return launchApp(cfg)
  if (!installed || ARGS.has('--setup')) return openSetup()
  return launchApp(cfg)
})

app.on('window-all-closed', () => {
  stopServices(children)
  app.quit()
})
app.on('before-quit', () => stopServices(children))
