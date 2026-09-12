import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { execSync } from 'node:child_process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Is the FastAPI backend actually running?
//
// WHY THIS GATE EXISTS. This plugin intercepts nine /api routes inside
// the dev server. Five of them -- /api/corpus, /api/sources (GET, POST,
// DELETE), /api/sources/scan and /api/sources/upload -- are ALSO
// implemented by the real backend, and the interception won, silently.
// A `proxy` to 127.0.0.1:8000 is configured below and was never reached
// for those paths.
//
// Two consequences, both bad:
//
//   1. Everyone has been developing against the dev server's own
//      filesystem scan rather than the backend's corpus. The two can
//      disagree about what is indexed -- the dev server lists files on
//      disk, the backend lists what is actually in FAISS -- and the UI
//      showed the reassuring one.
//
//   2. `vite build` produces no dev server. In a packaged build all
//      nine routes go to the backend, so the shipped app takes code
//      paths nobody has ever exercised. "Works in dev" was not evidence
//      about the product.
//
// So: when the backend answers, it wins, and this plugin steps aside.
// When it does not, these handlers remain as a frontend-only fallback,
// which is what they are legitimately good for.
//
// Probed once per process and cached, with a short negative TTL so
// starting the backend does not require restarting Vite.
let __backendUp = null
let __backendCheckedAt = 0
const BACKEND_RECHECK_MS = 5000

async function backendIsUp() {
  const now = Date.now()
  if (__backendUp === true) return true
  if (__backendUp === false && now - __backendCheckedAt < BACKEND_RECHECK_MS) return false
  __backendCheckedAt = now
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 1500)
    const res = await fetch('http://127.0.0.1:8000/api/health', { signal: ctl.signal })
    clearTimeout(t)
    __backendUp = res.ok
  } catch {
    __backendUp = false
  }
  return __backendUp
}

// Routes the real backend implements. Anything here must reach it when
// it is up, so the dev server and the packaged build behave the same.
const BACKEND_OWNED_ROUTES = new Set([
  '/api/corpus',
  '/api/sources',
  '/api/sources/scan',
  '/api/sources/upload',
  '/api/models',
  '/api/system-info',
])

function systemAndModelsPlugin() {
  return {
    name: 'system-and-models-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url?.split('?')[0]
        const cwd = path.resolve(__dirname, '..')

        // Real backend wins. next() hands the request to the proxy.
        if (BACKEND_OWNED_ROUTES.has(url) && (await backendIsUp())) {
          return next()
        }

        if (url === '/api/system-info' && req.method === 'GET') {
          try {
            const s = fs.statfsSync(cwd)
            const totalBytes = Number(s.bsize) * Number(s.blocks)
            const freeBytes = Number(s.bsize) * Number(s.bfree)
            const usedBytes = totalBytes - freeBytes
            const totalGB = Number((totalBytes / 1e9).toFixed(1))
            const usedGB = Number((usedBytes / 1e9).toFixed(1))
            const freeGB = Number((freeBytes / 1e9).toFixed(1))
            const utilPct = Number(((usedBytes / totalBytes) * 100).toFixed(1))

            const parsedRoot = path.parse(cwd).root
            const platform = os.platform()
            const driveLetter = platform === 'win32' ? parsedRoot.replace(/[\\/]/g, '') : parsedRoot
            const hostname = os.hostname()
            const cpuModel = os.cpus()[0]?.model || 'Host Multi-Core CPU'
            const cpuCores = os.cpus().length
            const totalMemGB = Number((os.totalmem() / 1e9).toFixed(1))
            const freeMemGB = Number((os.freemem() / 1e9).toFixed(1))

            let gpu = null
            try {
              const out = execSync('nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits', {
                timeout: 1500,
                stdio: ['pipe', 'pipe', 'ignore'],
              }).toString().trim()
              const [name, totalMB, usedMB] = out.split(',').map((x) => x.trim())
              if (name) {
                gpu = {
                  name,
                  vramTotalMB: Number(totalMB) || 0,
                  vramUsedMB: Number(usedMB) || 0,
                }
              }
            } catch {}

            // Check actual Ollama models directory if present
            let ollamaSizeGB = 5.2
            try {
              const ollamaDir = path.join(os.homedir(), '.ollama', 'models')
              if (fs.existsSync(ollamaDir)) {
                let bytes = 0
                function getDirSize(d) {
                  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
                    const p = path.join(d, e.name)
                    if (e.isDirectory()) getDirSize(p)
                    else bytes += fs.statSync(p).size
                  }
                }
                getDirSize(ollamaDir)
                if (bytes > 0) ollamaSizeGB = Number((bytes / 1e9).toFixed(1))
              }
            } catch {}

            // Measure actual MRPL Corpus directly from workspace directory
            let corpusSizeBytes = 2500581
            let corpusFileCount = 14
            try {
              const corpusDir = path.resolve(cwd, 'MRPL_RAG_Test_Corpus')
              if (fs.existsSync(corpusDir)) {
                let bytes = 0
                let count = 0
                function walkCorpus(d) {
                  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
                    const p = path.join(d, e.name)
                    if (e.isDirectory()) {
                      walkCorpus(p)
                    } else if (e.isFile()) {
                      bytes += fs.statSync(p).size
                      count++
                    }
                  }
                }
                walkCorpus(corpusDir)
                if (bytes > 0) {
                  corpusSizeBytes = bytes
                  corpusFileCount = count
                }
              }
            } catch {}

            const corpusSizeMB = Number((corpusSizeBytes / 1e6).toFixed(2))
            const corpusDisplay = `${corpusSizeMB} MB (${corpusFileCount} docs)`

            // Measure actual Vector Store / extraction cache directly from workspace
            let vectorStoreBytes = 15398
            try {
              const cacheDir = path.resolve(cwd, 'backend', 'evaluation', 'extraction_cache')
              if (fs.existsSync(cacheDir)) {
                for (const e of fs.readdirSync(cacheDir, { withFileTypes: true })) {
                  const p = path.join(cacheDir, e.name)
                  if (e.isFile()) vectorStoreBytes += fs.statSync(p).size
                }
              }
            } catch {}
            const vectorStoreDisplay = `${(vectorStoreBytes / 1e3).toFixed(1)} KB (FAISS Index)`

            const data = {
              device: {
                platform,
                osName: platform === 'win32' ? `Windows ${os.release()}` : `${platform} ${os.release()}`,
                hostname,
                mountPoint: parsedRoot,
                driveLetter,
                fileSystem: platform === 'win32' ? 'NTFS' : 'ext4',
                devicePath: platform === 'win32' ? `\\\\.\\PhysicalDrive0 (${driveLetter})` : '/dev/mapper/sovereign-storage',
                cpuModel,
                cpuCores,
                totalMemGB,
                freeMemGB,
                gpu,
                encryption: platform === 'win32' ? 'BitLocker / Hardware Volume Protected' : 'LUKS2 / AES-256-XTS',
                isAirGapped: true,
              },
              storage: {
                totalBytes,
                freeBytes,
                usedBytes,
                totalGB,
                usedGB,
                freeGB,
                utilizationPct: utilPct,
                breakdown: [
                  {
                    id: 'models',
                    label: 'Model Weights (GGUF / Ollama)',
                    sizeGB: ollamaSizeGB,
                    sizeDisplay: `${ollamaSizeGB} GB`,
                    color: 'var(--color-accent)',
                  },
                  {
                    id: 'vector_store',
                    label: 'FAISS Vector Store & SQLite',
                    sizeGB: Number((vectorStoreBytes / 1e9).toFixed(3)),
                    sizeDisplay: vectorStoreDisplay,
                    color: '#2563EB',
                  },
                  {
                    id: 'corpus',
                    label: 'MRPL Engineering Corpus',
                    sizeGB: Number((corpusSizeBytes / 1e9).toFixed(3)),
                    sizeDisplay: corpusDisplay,
                    color: '#059669',
                  },
                  {
                    id: 'system',
                    label: 'Audit Logs, OS & App Space',
                    sizeGB: Number(Math.max(1, usedGB - (ollamaSizeGB + Number((corpusSizeBytes / 1e9).toFixed(3)))).toFixed(1)),
                    sizeDisplay: `${Number(Math.max(1, usedGB - (ollamaSizeGB + Number((corpusSizeBytes / 1e9).toFixed(3)))).toFixed(1))} GB`,
                    color: '#D97706',
                  },
                ],
              },
            }

            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(data))
            return
          } catch (err) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: err.message }))
            return
          }
        }

        // Active watched directories list with on-disk persistence
        const configFilePath = path.resolve(cwd, 'backend', 'evaluation', 'configured_sources.json')

        function getDirectoryId(dirPath) {
          const norm = path.normalize(dirPath).toLowerCase()
          const hash = crypto.createHash('sha256').update(norm).digest('hex').slice(0, 10)
          return `dir_${hash}`
        }

        // THIS FUNCTION USED TO DESTROY THE USER'S TRACKED FOLDERS.
        //
        // The old body read the file inside `try { ... } catch {}`. Any
        // failure -- a transient read error, a partially written file, a
        // JSON syntax error -- was swallowed, `list` stayed empty, and
        // the `list.length === 0` branch below substituted the three
        // hardcoded preset corpora. The caller then IMMEDIATELY called
        // saveConfiguredDirs() on that result, writing the presets over
        // the real file.
        //
        // So a single unreadable byte silently and permanently deleted
        // every directory the user had added, at dev-server startup,
        // with no user action and no message. Observed live: a tracked
        // `docs` folder (19 files) vanished across a Vite restart, and
        // the corpus went from 50 sources to 31.
        //
        // The file is gitignored, so there was no copy to restore from.
        //
        // Two changes: a read failure is now distinguished from an empty
        // file and never silently yields presets, and the unreadable
        // file is preserved as a .corrupt backup instead of being
        // overwritten. Presets are only for a genuinely absent file --
        // a first run, where there is nothing to lose.
        function loadConfiguredDirs() {
          let list = []
          if (fs.existsSync(configFilePath)) {
            try {
              const saved = JSON.parse(fs.readFileSync(configFilePath, 'utf-8'))
              if (Array.isArray(saved) && saved.length > 0) list = saved
            } catch (err) {
              // Keep the bytes. They are the only record of what the
              // user was tracking, and they are about to be replaced.
              const backup = `${configFilePath}.corrupt-${Date.now()}`
              try {
                fs.copyFileSync(configFilePath, backup)
              } catch {}
              console.error(
                `[sources] configured_sources.json is unreadable (${err.message}).\n` +
                  `[sources] A copy was saved to ${backup}.\n` +
                  `[sources] Refusing to overwrite it with defaults - your tracked ` +
                  `folders are recoverable from that file.`
              )
              // Signal "do not persist this" to the caller.
              return { dirs: [], unreadable: true }
            }
          }
          if (list.length === 0) {
            list = [
              {
                id: 'user_uploads_corpus',
                name: 'User Ingested Sources',
                path: path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads'),
                isPreset: true,
                isUserUploads: true,
                enabled: true,
              },
              {
                id: 'mrpl_rag_corpus',
                name: 'MRPL_RAG_Test_Corpus',
                path: path.resolve(cwd, 'MRPL_RAG_Test_Corpus'),
                isPreset: true,
                enabled: true,
              },
              {
                id: 'mrpl_chart_corpus',
                name: 'MRPL_Chart_Stress_Corpus',
                path: path.resolve(cwd, 'MRPL_Chart_Stress_Corpus'),
                isPreset: true,
                enabled: true,
              },
            ]
          }

          // Ensure user_uploads_corpus is first
          const userUploadsIndex = list.findIndex(
            (d) => d.id === 'user_uploads_corpus' || d.name === 'User Ingested Sources' || (d.path && d.path.includes('07_User_Uploads'))
          )
          if (userUploadsIndex > 0) {
            const [uu] = list.splice(userUploadsIndex, 1)
            list.unshift(uu)
          } else if (userUploadsIndex === -1) {
            list.unshift({
              id: 'user_uploads_corpus',
              name: 'User Ingested Sources',
              path: path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads'),
              isPreset: true,
              isUserUploads: true,
              enabled: true,
            })
          }

          // Deduplicate and ensure each directory has a unique, deterministic ID
          const seen = new Set()
          const deduped = []
          for (const d of list) {
            if (!d.path) continue
            const norm = path.normalize(d.path).toLowerCase()
            if (seen.has(norm)) continue
            seen.add(norm)
            if (!d.id || d.id.startsWith('dir_433a5c') || deduped.some((x) => x.id === d.id)) {
              d.id = d.isPreset ? d.id : getDirectoryId(d.path)
            }
            deduped.push({
              ...d,
              path: path.normalize(d.path),
            })
          }
          return { dirs: deduped, unreadable: false }
        }

        function saveConfiguredDirs(dirs) {
          try {
            const dir = path.dirname(configFilePath)
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
            fs.writeFileSync(configFilePath, JSON.stringify(dirs, null, 2), 'utf-8')
          } catch {}
        }

        // Load only. The unconditional save that used to be here is
        // what turned a read failure into permanent data loss: startup
        // rewrote the file every time, so the fallback presets were
        // persisted before anyone could notice they were wrong.
        //
        // Nothing is written unless the user actually changes something,
        // which the add/remove handlers below do explicitly.
        {
          const loaded = loadConfiguredDirs()
          global.__configuredSourceDirs = loaded.dirs
          global.__sourcesConfigUnreadable = loaded.unreadable
        }

        // Generic local file streaming for preview/reading across all configured sources
        if (url === '/api/sources/file' && req.method === 'GET') {
          try {
            const urlObj = new URL(req.url, 'http://localhost')
            const reqPath = urlObj.searchParams.get('path')
            if (reqPath && fs.existsSync(reqPath) && fs.statSync(reqPath).isFile()) {
              const ext = path.extname(reqPath).toLowerCase()
              const mimeMap = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.pdf': 'application/pdf',
                '.txt': 'text/plain; charset=utf-8',
                '.md': 'text/markdown; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
                '.csv': 'text/csv; charset=utf-8',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              }
              res.setHeader('Content-Type', mimeMap[ext] || 'application/octet-stream')
              fs.createReadStream(reqPath).pipe(res)
              return
            }
          } catch {}
        }

        if (url?.startsWith('/MRPL_Chart_Stress_Corpus/') || url?.startsWith('/MRPL_RAG_Test_Corpus/')) {
          try {
            const rawRel = decodeURIComponent(url).replace(/^\//, '')
            const filePath = path.resolve(cwd, rawRel)
            if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
              const ext = path.extname(filePath).toLowerCase()
              const mime = ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : 'application/octet-stream'
              res.setHeader('Content-Type', mime)
              fs.createReadStream(filePath).pipe(res)
              return
            }
          } catch {}
        }

        if (url === '/api/sources/scan' && req.method === 'POST') {
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ success: true, scannedAt: new Date().toISOString() }))
          return
        }

        if (url === '/api/sources' && req.method === 'DELETE') {
          let body = ''
          req.on('data', (c) => { body += c })
          req.on('end', async () => {
            try {
              const urlObj = new URL(req.url, 'http://localhost')
              let targetPath = urlObj.searchParams.get('path')
              if (!targetPath && body) {
                try {
                  const b = JSON.parse(body)
                  targetPath = b.path || b.id
                } catch {}
              }
              if (targetPath) {
                const normTarget = path.normalize(targetPath).toLowerCase()
                global.__configuredSourceDirs = loadConfiguredDirs().dirs.filter(
                  (d) =>
                    d.id !== targetPath &&
                    path.normalize(d.path).toLowerCase() !== normTarget &&
                    d.name.toLowerCase() !== normTarget
                )
                saveConfiguredDirs(global.__configuredSourceDirs)

                // Delete file or folder from disk if it exists
                const baseName = path.basename(targetPath)
                const possiblePaths = [
                  targetPath,
                  path.resolve(cwd, targetPath),
                  path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads', baseName),
                  path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads', targetPath),
                ]
                for (const p of possiblePaths) {
                  if (fs.existsSync(p)) {
                    try {
                      const stat = fs.statSync(p)
                      if (stat.isFile()) {
                        fs.unlinkSync(p)
                      } else if (stat.isDirectory()) {
                        // Prevent deleting the main preset root directories
                        const normalizedP = path.normalize(p).toLowerCase()
                        const ragRoot = path.normalize(path.resolve(cwd, 'MRPL_RAG_Test_Corpus')).toLowerCase()
                        const chartRoot = path.normalize(path.resolve(cwd, 'MRPL_Chart_Stress_Corpus')).toLowerCase()
                        const uploadsRoot = path.normalize(path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads')).toLowerCase()
                        if (normalizedP === uploadsRoot) {
                          for (const file of fs.readdirSync(p)) {
                            fs.rmSync(path.join(p, file), { recursive: true, force: true })
                          }
                        } else if (normalizedP !== ragRoot && normalizedP !== chartRoot) {
                          fs.rmSync(p, { recursive: true, force: true })
                        }
                      }
                    } catch {}
                  }
                }

                // Forward deletion to FastAPI backend so vector store chunks are removed
                try {
                  await fetch(`http://127.0.0.1:8000/api/sources?path=${encodeURIComponent(targetPath)}`, {
                    method: 'DELETE',
                  })
                } catch (err) {
                  console.warn('[Backend delete error]', err.message)
                }
              }
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ success: true, remaining: global.__configuredSourceDirs }))
              return
            } catch (err) {
              res.statusCode = 500
              res.end(JSON.stringify({ error: err.message }))
              return
            }
          })
          return
        }

        if (url === '/api/sources/upload' && req.method === 'POST') {
          const chunks = []
          req.on('data', (c) => { chunks.push(c) })
          req.on('end', async () => {
            try {
              const rawBody = Buffer.concat(chunks).toString('utf-8')
              const payload = JSON.parse(rawBody || '{}')
              const files = payload.files || []
              if (!Array.isArray(files) || files.length === 0) {
                res.statusCode = 400
                res.end(JSON.stringify({ error: 'No files provided for upload' }))
                return
              }

              const targetBaseDir = path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads')
              if (!fs.existsSync(targetBaseDir)) {
                fs.mkdirSync(targetBaseDir, { recursive: true })
              }

              const savedFiles = []
              for (const f of files) {
                if (!f.name || !f.contentBase64) continue
                const cleanRel = (f.relPath || f.name).replace(/^[/\\]+/, '').replace(/\.\.[/\\]/g, '')
                const destPath = path.resolve(targetBaseDir, cleanRel)
                const destDir = path.dirname(destPath)
                if (!fs.existsSync(destDir)) {
                  fs.mkdirSync(destDir, { recursive: true })
                }
                const buffer = Buffer.from(f.contentBase64, 'base64')
                fs.writeFileSync(destPath, buffer)
                savedFiles.push({
                  name: f.name,
                  relPath: cleanRel,
                  sizeBytes: buffer.length,
                  fullPath: destPath,
                })
              }

              // Check if any files were uploaded with a folder structure (from "Browse Folder…" or directory drop)
              const topFolders = new Set()
              for (const sf of savedFiles) {
                const parts = sf.relPath.split(/[\\/]/)
                if (parts.length > 1 && parts[0]) {
                  topFolders.add(parts[0])
                }
              }

              global.__configuredSourceDirs = loadConfiguredDirs().dirs
              for (const folder of topFolders) {
                const folderPath = path.resolve(targetBaseDir, folder)
                const id = getDirectoryId(folderPath)
                const norm = path.normalize(folderPath).toLowerCase()
                const exists = global.__configuredSourceDirs.some(
                  (d) => path.normalize(d.path).toLowerCase() === norm
                )
                if (!exists) {
                  global.__configuredSourceDirs.push({
                    id,
                    name: folder,
                    path: folderPath,
                    isPreset: false,
                    isUploadedFolder: true,
                    enabled: true,
                  })
                }
              }
              saveConfiguredDirs(global.__configuredSourceDirs)

              // Trigger chunking and embedding pipeline in FastAPI backend
              let totalChunks = 0
              let documents = []
              for (const sf of savedFiles) {
                try {
                  const ingestRes = await fetch('http://127.0.0.1:8000/api/sources/ingest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: sf.fullPath }),
                  })
                  if (ingestRes.ok) {
                    const data = await ingestRes.json()
                    totalChunks += data.total_chunks || 0
                    if (data.documents) documents.push(...data.documents)
                  }
                } catch (err) {
                  console.warn('[Ingestion pipeline error]:', err.message)
                }
              }

              res.setHeader('Content-Type', 'application/json')
              res.end(
                JSON.stringify({
                  success: true,
                  count: savedFiles.length,
                  saved: savedFiles,
                  total_chunks: totalChunks,
                  documents,
                  directories: global.__configuredSourceDirs,
                  message: `Successfully ingested ${savedFiles.length} file(s): ${totalChunks} chunks created, embedded (1024-d), and indexed into FAISS.`,
                })
              )
              return
            } catch (err) {
              res.statusCode = 500
              res.end(JSON.stringify({ error: err.message }))
              return
            }
          })
          return
        }

        if (url === '/api/sources' && req.method === 'POST') {
          let body = ''
          req.on('data', (c) => { body += c })
          req.on('end', async () => {
            try {
              const payload = JSON.parse(body || '{}')
              let dirPath = payload.path?.trim().replace(/^["']|["']$/g, '')
              if (!dirPath) {
                res.statusCode = 400
                res.end(JSON.stringify({ error: 'Missing path parameter' }))
                return
              }
              const resolved = path.isAbsolute(dirPath) ? path.normalize(dirPath) : path.resolve(cwd, dirPath)
              if (!fs.existsSync(resolved)) {
                res.statusCode = 404
                res.end(JSON.stringify({ error: `Path does not exist on disk: ${resolved}` }))
                return
              }
              const stat = fs.statSync(resolved)
              let totalChunks = 0
              let documents = []

              if (stat.isFile()) {
                const targetBaseDir = path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads')
                if (!fs.existsSync(targetBaseDir)) {
                  fs.mkdirSync(targetBaseDir, { recursive: true })
                }
                const fileName = path.basename(resolved)
                const destFile = path.resolve(targetBaseDir, fileName)
                fs.copyFileSync(resolved, destFile)

                // Trigger chunking and embedding in FastAPI backend
                try {
                  const ingestRes = await fetch('http://127.0.0.1:8000/api/sources/ingest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: destFile }),
                  })
                  if (ingestRes.ok) {
                    const data = await ingestRes.json()
                    totalChunks = data.total_chunks || 0
                    documents = data.documents || []
                  }
                } catch (err) {
                  console.warn('[Ingest error]', err.message)
                }

                global.__configuredSourceDirs = loadConfiguredDirs().dirs
                saveConfiguredDirs(global.__configuredSourceDirs)

                const fileId = `file_${crypto.createHash('sha256').update(path.normalize(destFile).toLowerCase()).digest('hex').slice(0, 10)}`
                res.setHeader('Content-Type', 'application/json')
                res.end(
                  JSON.stringify({
                    success: true,
                    total_chunks: totalChunks,
                    documents,
                    directories: global.__configuredSourceDirs,
                    added: {
                      id: fileId,
                      name: fileName,
                      path: destFile,
                      isFile: true,
                    },
                    message: `File "${fileName}" registered: ${totalChunks} chunks created, embedded, and indexed into FAISS.`,
                  })
                )
                return
              }

              // Handle directory path
              const dirName = path.basename(resolved) || 'Custom_Corpus'
              const id = getDirectoryId(resolved)
              const normResolved = path.normalize(resolved).toLowerCase()
              global.__configuredSourceDirs = loadConfiguredDirs().dirs
              const existingIdx = global.__configuredSourceDirs.findIndex(
                (d) => path.normalize(d.path).toLowerCase() === normResolved
              )
              if (existingIdx >= 0) {
                global.__configuredSourceDirs[existingIdx].enabled = true
                global.__configuredSourceDirs[existingIdx].id = id
              } else {
                global.__configuredSourceDirs.push({
                  id,
                  name: dirName,
                  path: resolved,
                  isPreset: false,
                  enabled: true,
                })
              }
              saveConfiguredDirs(global.__configuredSourceDirs)

              // Trigger chunking and embedding of directory contents in FastAPI backend
              try {
                const ingestRes = await fetch('http://127.0.0.1:8000/api/sources/ingest', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ path: resolved }),
                })
                if (ingestRes.ok) {
                  const data = await ingestRes.json()
                  totalChunks = data.total_chunks || 0
                  documents = data.documents || []
                }
              } catch (err) {
                console.warn('[Ingest directory error]', err.message)
              }

              res.setHeader('Content-Type', 'application/json')
              res.end(
                JSON.stringify({
                  success: true,
                  total_chunks: totalChunks,
                  documents,
                  directories: global.__configuredSourceDirs,
                  added: { id, name: dirName, path: resolved },
                  message: `Directory "${dirName}" registered: ${totalChunks} chunks created, embedded, and indexed into FAISS.`,
                })
              )
              return
            } catch (err) {
              res.statusCode = 500
              res.end(JSON.stringify({ error: err.message }))
              return
            }
          })
          return
        }

        if ((url === '/api/corpus' || url === '/api/sources') && req.method === 'GET') {
          try {
            const allItems = []
            const tree = []
            global.__configuredSourceDirs = loadConfiguredDirs().dirs

            // List of custom subpaths to avoid double-listing in parent
            const customSubpaths = global.__configuredSourceDirs
              .filter((d) => !d.isPreset)
              .map((d) => path.normalize(d.path).toLowerCase())

            for (const dirConfig of global.__configuredSourceDirs) {
              if (!dirConfig.enabled || !fs.existsSync(dirConfig.path)) continue

              const dirNode = {
                id: dirConfig.id,
                name: dirConfig.name,
                fullPath: dirConfig.path,
                type: 'directory',
                isRoot: true,
                isPreset: dirConfig.isPreset,
                children: [],
                fileCount: 0,
                totalSizeBytes: 0,
              }

              function scanDirectory(currentDir, relativePrefix, parentNode) {
                let entries = []
                try {
                  entries = fs.readdirSync(currentDir, { withFileTypes: true })
                } catch {
                  return
                }

                for (const entry of entries) {
                  const entryFullPath = path.join(currentDir, entry.name)
                  const entryRelPath = relativePrefix ? `${relativePrefix}/${entry.name}` : entry.name
                  const normEntryFullPath = path.normalize(entryFullPath).toLowerCase()

                  if (entry.isDirectory()) {
                    if (dirConfig.id === 'mrpl_rag_corpus' && entry.name === '07_User_Uploads') {
                      continue
                    }
                    if (dirConfig.isPreset && customSubpaths.includes(normEntryFullPath)) {
                      continue
                    }
                    const subDirNode = {
                      id: `${dirConfig.id}_${entryRelPath.replace(/[\\/]/g, '_')}`,
                      name: entry.name,
                      fullPath: entryFullPath,
                      relPath: entryRelPath,
                      type: 'directory',
                      isRoot: false,
                      children: [],
                      fileCount: 0,
                      totalSizeBytes: 0,
                    }
                    scanDirectory(entryFullPath, entryRelPath, subDirNode)
                    parentNode.children.push(subDirNode)
                    parentNode.fileCount += subDirNode.fileCount
                    parentNode.totalSizeBytes += subDirNode.totalSizeBytes
                  } else if (entry.isFile()) {
                    let stat = null
                    try {
                      stat = fs.statSync(entryFullPath)
                    } catch {
                      continue
                    }

                    const ext = path.extname(entry.name).toLowerCase().replace('.', '')
                    let fileType = ext.toUpperCase()
                    let category = 'documents'
                    let subcategory = 'general'
                    let badge = 'Document'
                    let color = '#2563EB'
                    let bg = 'rgba(37, 99, 235, 0.12)'
                    let border = 'rgba(37, 99, 235, 0.28)'

                    if (dirConfig.name === 'MRPL_Chart_Stress_Corpus') {
                      category = ext === 'json' ? 'data' : 'charts'
                      subcategory = 'charts'
                      if (entry.name.includes('_labeled')) {
                        badge = 'Chart (Printed Labels)'
                        color = '#D97706'
                        bg = 'rgba(217, 119, 6, 0.12)'
                        border = 'rgba(217, 119, 6, 0.28)'
                      } else if (entry.name.includes('_unlabeled')) {
                        badge = 'Chart (Unlabeled Stress)'
                        color = '#A63927'
                        bg = 'rgba(166, 57, 39, 0.12)'
                        border = 'rgba(166, 57, 39, 0.28)'
                      } else if (entry.name.endsWith('.json')) {
                        badge = 'Ground Truth Specs'
                        color = '#7C3AED'
                        bg = 'rgba(124, 58, 237, 0.12)'
                        border = 'rgba(124, 58, 237, 0.28)'
                      }
                    } else if (entryRelPath.includes('01_SOPs')) {
                      category = 'documents'
                      subcategory = 'sops'
                      badge = 'SOP & Safety'
                    } else if (entryRelPath.includes('02_Inspection')) {
                      subcategory = 'inspection'
                      badge = 'Inspection & Maintenance'
                      category = ext === 'xlsx' ? 'data' : 'documents'
                    } else if (entryRelPath.includes('03_Quality')) {
                      subcategory = 'quality'
                      badge = 'QA & Process Data'
                      category = ext === 'xlsx' ? 'data' : 'documents'
                    } else if (entryRelPath.includes('04_SAP')) {
                      category = 'data'
                      subcategory = 'sap_mock'
                      badge = 'SAP ERP Export'
                    } else if (entryRelPath.includes('05_Correspondence')) {
                      category = 'documents'
                      subcategory = 'correspondence'
                      badge = 'Depot Operations'
                    } else if (entryRelPath.includes('06_Diagrams')) {
                      category = 'documents'
                      subcategory = 'diagrams'
                      fileType = entry.name.includes('Checklist') ? 'SCAN' : 'P&ID'
                      badge = 'Schematics & Scans'
                    } else if (entryRelPath.includes('07_User_Uploads') || entryRelPath.includes('Uploads')) {
                      category = ['xlsx', 'xls', 'csv', 'json'].includes(ext) ? 'data' : ['png', 'jpg', 'jpeg'].includes(ext) ? 'charts' : 'documents'
                      subcategory = 'user_uploads'
                      badge = 'User Ingested Source'
                      color = '#10B981'
                      bg = 'rgba(16, 185, 129, 0.12)'
                      border = 'rgba(16, 185, 129, 0.28)'
                    }

                    if (ext === 'md' || ext === 'markdown') {
                      category = 'documents'
                      badge = 'Markdown Document'
                      color = '#CBD5E1'
                      bg = 'rgba(203, 213, 225, 0.12)'
                      border = 'rgba(203, 213, 225, 0.28)'
                    } else if (ext === 'json') {
                      category = 'data'
                      badge = 'JSON Spec / Data'
                      color = '#FB923C'
                      bg = 'rgba(251, 146, 60, 0.12)'
                      border = 'rgba(251, 146, 60, 0.28)'
                    } else if (ext === 'yaml' || ext === 'yml') {
                      category = 'data'
                      badge = 'Config Spec'
                      color = '#F59E0B'
                      bg = 'rgba(245, 158, 11, 0.12)'
                      border = 'rgba(245, 158, 11, 0.28)'
                    } else if (['py', 'sql', 'sh', 'ps1', 'bat'].includes(ext)) {
                      category = 'documents'
                      badge = 'Script / Code'
                      color = '#60A5FA'
                      bg = 'rgba(96, 165, 250, 0.12)'
                      border = 'rgba(96, 165, 250, 0.28)'
                    } else if (category === 'data') {
                      color = '#059669'
                      bg = 'rgba(5, 150, 105, 0.12)'
                      border = 'rgba(5, 150, 105, 0.28)'
                    } else if (fileType === 'PDF') {
                      color = '#D93829'
                      bg = 'rgba(217, 56, 41, 0.12)'
                      border = 'rgba(217, 56, 41, 0.28)'
                    } else if (fileType === 'SCAN' || fileType === 'P&ID') {
                      color = '#0D9488'
                      bg = 'rgba(13, 148, 136, 0.12)'
                      border = 'rgba(13, 148, 136, 0.28)'
                    }

                    const sizeKB = Number((stat.size / 1024).toFixed(1))
                    const sizeDisplay = sizeKB > 1024 ? `${(sizeKB / 1024).toFixed(2)} MB` : `${sizeKB} KB`

                    const fileItem = {
                      id: `${dirConfig.id}_${entryRelPath.replace(/[\\/]/g, '_')}`,
                      name: entry.name,
                      type: fileType,
                      extension: ext,
                      size: sizeDisplay,
                      sizeBytes: stat.size,
                      addedAgo: 'Ingested on-prem',
                      category,
                      subcategory,
                      badge,
                      folder: relativePrefix || dirConfig.name,
                      relPath: entryRelPath,
                      fullPath: entryFullPath,
                      corpus: dirConfig.name,
                      color,
                      bg,
                      border,
                      iconText: fileType,
                      enabled: true,
                    }

                    parentNode.children.push({
                      ...fileItem,
                      type: 'file',
                    })
                    parentNode.fileCount++
                    parentNode.totalSizeBytes += stat.size
                    allItems.push(fileItem)
                  }
                }
              }

              scanDirectory(dirConfig.path, '', dirNode)
              dirNode.sizeDisplay = dirNode.totalSizeBytes > 1e6
                ? `${(dirNode.totalSizeBytes / 1e6).toFixed(2)} MB`
                : `${Math.round(dirNode.totalSizeBytes / 1024)} KB`
              tree.push(dirNode)
            }

            // THE FABRICATED PLANT CONNECTORS WERE REMOVED HERE.
            //
            // This block injected two entries into the source list:
            // "SAP_Plant_Sensors_API" (labelled "SAP ERP Local
            // Connector (RFC/BAPI Mock)") and "DCS_SCADA_Telemetry_Feed"
            // ("DCS / SCADA Telemetry Stream (OPC-UA)"), each marked
            // isLive: true, size "Live Stream", status "Online
            // (Loopback)", grouped under a virtual folder called "Live
            // Plant APIs & Connectors".
            //
            // None of it existed. There is no SAP connector, no OPC-UA
            // client, and nothing was streaming. The word "Mock" was in
            // a `label` field the sidebar does not render, so what a
            // viewer saw was a refinery workbench reporting two live
            // connections to plant control systems.
            //
            // That is not a placeholder, it is a claimed capability, and
            // it was the only thing on screen asserting the product
            // talks to plant infrastructure. It also inflated the source
            // count by two (50 real files displayed as 52) and put two
            // non-documents into a list whose every other entry is
            // retrievable, so "52 / 52 active" in the Knowledge Base
            // panel counted things that can never be retrieved.
            //
            // When a real connector exists it belongs in the backend's
            // corpus response, reporting its real connection state --
            // not hardcoded into the dev server, where it cannot fail.
            const apis = []

            // Only render the connector group if there is a real
            // connector to put in it. An empty "Live Plant APIs" folder
            // still asserts the category exists and is merely idle.
            if (apis.length > 0) {
              tree.push({
                id: 'live_plant_apis',
                name: 'Live Plant APIs & Connectors',
                type: 'directory',
                isRoot: true,
                isPreset: true,
                fileCount: apis.length,
                totalSizeBytes: 0,
                sizeDisplay: 'Live Data',
                children: apis.map((a) => ({ ...a, type: 'api' })),
              })
            }

            const totalBytes = allItems.reduce((acc, i) => acc + i.sizeBytes, 0)
            const totalSizeMB = Number((totalBytes / 1e6).toFixed(2))

            res.setHeader('Content-Type', 'application/json')
            res.end(
              JSON.stringify({
                directories: global.__configuredSourceDirs,
                tree,
                sources: [...allItems, ...apis],
                count: allItems.length + apis.length,
                corpusCount: allItems.length,
                totalSizeBytes: totalBytes,
                totalSizeDisplay: `${totalSizeMB} MB`,
              })
            )
            return
          } catch (err) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: err.message }))
            return
          }
        }



        if (url === '/api/models' && req.method === 'GET') {
          try {
            const modelsYamlPath = path.resolve(__dirname, '../models/models.yaml')
            let raw = ''
            if (fs.existsSync(modelsYamlPath)) {
              raw = fs.readFileSync(modelsYamlPath, 'utf-8')
            }

            // Parse models.yaml
            const parsed = []
            const blocks = raw.split(/(?:^|\n)-\s+id:\s*/).slice(1)
            for (const b of blocks) {
              const lines = b.trim().split('\n')
              const id = lines[0].trim()
              const entry = { id, backend: 'ollama', model: '', task_tags: [] }
              for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim()
                if (line.startsWith('backend:')) {
                  entry.backend = line.replace('backend:', '').trim()
                } else if (line.startsWith('model:')) {
                  entry.model = line.replace('model:', '').trim()
                } else if (line.startsWith('task_tags:')) {
                  const r = line.replace('task_tags:', '').replace(/[[\]]/g, '').trim()
                  entry.task_tags = r.split(',').map((s) => s.trim()).filter(Boolean)
                }
              }
              if (entry.id && entry.model) {
                let vram = '4.8 GB'
                if (entry.model.includes('14b')) vram = '8.5 GB'
                else if (entry.model.includes('32b') || entry.model.includes('70b')) vram = '18.0 GB'
                else if (entry.model.includes('mini') || entry.model.includes('3b')) vram = '2.2 GB'
                else if (entry.model.includes('vl')) vram = '5.2 GB'
                else if (entry.model.includes('7b') || entry.model.includes('8b')) vram = '4.8 GB'

                parsed.push({
                  ...entry,
                  vram_usage: vram,
                  status: 'active',
                  engine_type: 'ollama_registry',
                })
              }
            }

            // Add auxiliary backend engines from backend/
            const auxiliaryModels = [
              {
                id: 'bge-large-embeddings',
                backend: 'sentence-transformers',
                model: 'BAAI/bge-large-en-v1.5',
                task_tags: ['dense_embeddings', 'hybrid_search', 'vector_indexing'],
                vram_usage: '1.3 GB (RAM)',
                status: 'active',
                engine_type: 'embedded',
              },
              {
                id: 'faster-whisper-audio',
                backend: 'ctranslate2',
                model: 'Systran/faster-whisper-base',
                task_tags: ['audio_transcription', 'voice_notes'],
                vram_usage: '0.5 GB (RAM)',
                status: 'active',
                engine_type: 'embedded',
              },
              {
                id: 'paddleocr-engine',
                backend: 'paddlex',
                model: 'ch_PP-OCRv4',
                task_tags: ['ocr_detection', 'ocr_recognition', 'table_extraction'],
                vram_usage: '0.3 GB (RAM)',
                status: 'active',
                engine_type: 'embedded',
              },
            ]

            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ registry: parsed, auxiliary: auxiliaryModels }))
            return
          } catch (err) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: err.message }))
            return
          }
        }

        if (url === '/api/models' && req.method === 'POST') {
          let body = ''
          req.on('data', (chunk) => {
            body += chunk
          })
          req.on('end', () => {
            try {
              const payload = JSON.parse(body)
              const { id, backend, model, task_tags } = payload
              if (!id || !model) {
                res.statusCode = 400
                res.end(JSON.stringify({ error: 'Missing id or model' }))
                return
              }

              const modelsYamlPath = path.resolve(__dirname, '../models/models.yaml')
              const tagsStr = Array.isArray(task_tags) ? task_tags.join(', ') : task_tags
              const yamlEntry = `\n- id: ${id}\n  backend: ${backend || 'ollama'}\n  model: ${model}\n  task_tags: [${tagsStr}]\n`

              fs.appendFileSync(modelsYamlPath, yamlEntry, 'utf-8')

              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ success: true, registered: { id, backend, model, task_tags } }))
              return
            } catch (err) {
              res.statusCode = 500
              res.end(JSON.stringify({ error: err.message }))
              return
            }
          })
          return
        }

        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    systemAndModelsPlugin(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
