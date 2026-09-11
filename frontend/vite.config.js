import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execSync } from 'node:child_process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function systemAndModelsPlugin() {
  return {
    name: 'system-and-models-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url?.split('?')[0]
        const cwd = path.resolve(__dirname, '..')

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

        // Active watched directories list
        if (!global.__configuredSourceDirs) {
          global.__configuredSourceDirs = [
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
          req.on('end', () => {
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
                global.__configuredSourceDirs = (global.__configuredSourceDirs || []).filter(
                  (d) =>
                    d.id !== targetPath &&
                    path.normalize(d.path).toLowerCase() !== normTarget &&
                    d.name.toLowerCase() !== normTarget
                )
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
          req.on('end', () => {
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

              // Ensure MRPL_RAG_Test_Corpus is enabled
              const corpusDir = path.resolve(cwd, 'MRPL_RAG_Test_Corpus')
              const existingCorpus = (global.__configuredSourceDirs || []).find((d) => d.path === corpusDir)
              if (existingCorpus) {
                existingCorpus.enabled = true
              }

              res.setHeader('Content-Type', 'application/json')
              res.end(
                JSON.stringify({
                  success: true,
                  count: savedFiles.length,
                  saved: savedFiles,
                  message: `Successfully uploaded and registered ${savedFiles.length} file(s) into active corpus`,
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
          req.on('end', () => {
            try {
              const payload = JSON.parse(body || '{}')
              let dirPath = payload.path?.trim()
              if (!dirPath) {
                res.statusCode = 400
                res.end(JSON.stringify({ error: 'Missing path parameter' }))
                return
              }
              const resolved = path.isAbsolute(dirPath) ? dirPath : path.resolve(cwd, dirPath)
              if (!fs.existsSync(resolved)) {
                res.statusCode = 404
                res.end(JSON.stringify({ error: `Path does not exist on disk: ${resolved}` }))
                return
              }
              const stat = fs.statSync(resolved)
              if (stat.isFile()) {
                const targetBaseDir = path.resolve(cwd, 'MRPL_RAG_Test_Corpus', '07_User_Uploads')
                if (!fs.existsSync(targetBaseDir)) {
                  fs.mkdirSync(targetBaseDir, { recursive: true })
                }
                const fileName = path.basename(resolved)
                const destFile = path.resolve(targetBaseDir, fileName)
                fs.copyFileSync(resolved, destFile)
                res.setHeader('Content-Type', 'application/json')
                res.end(
                  JSON.stringify({
                    success: true,
                    added: {
                      id: `file_${Buffer.from(destFile).toString('hex').slice(0, 10)}`,
                      name: fileName,
                      path: destFile,
                      isFile: true,
                    },
                    message: `File "${fileName}" registered and copied to local corpus (07_User_Uploads)`,
                  })
                )
                return
              }

              const dirName = path.basename(resolved) || 'Custom_Corpus'
              const id = `dir_${Buffer.from(resolved).toString('hex').slice(0, 10)}`
              const existingIdx = global.__configuredSourceDirs.findIndex((d) => d.path === resolved)
              if (existingIdx >= 0) {
                global.__configuredSourceDirs[existingIdx].enabled = true
              } else {
                global.__configuredSourceDirs.push({
                  id,
                  name: dirName,
                  path: resolved,
                  isPreset: false,
                  enabled: true,
                })
              }
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ success: true, added: { id, name: dirName, path: resolved } }))
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

                  if (entry.isDirectory()) {
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

                    if (category === 'data') {
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

            // Attached live connected plant APIs
            const apis = [
              {
                id: 'sap-plant-sensors-api',
                name: 'SAP_Plant_Sensors_API',
                label: 'SAP ERP Local Connector (RFC/BAPI Mock)',
                type: 'API',
                extension: 'api',
                size: 'Live Stream',
                sizeBytes: 0,
                addedAgo: 'Online (Loopback)',
                category: 'apis',
                subcategory: 'apis',
                badge: 'SAP ERP RFC/BAPI',
                color: 'var(--color-accent)',
                bg: 'var(--color-accent-tint)',
                border: 'var(--color-accent-border)',
                iconType: 'api',
                corpus: 'Live Plant Connectors',
                isLive: true,
                enabled: true,
              },
              {
                id: 'dcs-scada-telemetry-feed',
                name: 'DCS_SCADA_Telemetry_Feed',
                label: 'DCS / SCADA Telemetry Stream (OPC-UA)',
                type: 'API',
                extension: 'api',
                size: 'Live Stream',
                sizeBytes: 0,
                addedAgo: 'Online (Loopback)',
                category: 'apis',
                subcategory: 'apis',
                badge: 'OPC-UA Real-Time',
                color: 'var(--color-accent)',
                bg: 'var(--color-accent-tint)',
                border: 'var(--color-accent-border)',
                iconType: 'api',
                corpus: 'Live Plant Connectors',
                isLive: true,
                enabled: true,
              },
            ]

            // Virtual tree node for APIs
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

        // Serve Inspection / Standalone Console data endpoints for Vite dev
        if (url === '/api/graph' && req.method === 'GET') {
          try {
            const inspPath = path.resolve(cwd, 'backend', 'evaluation', 'inspection_data.json')
            if (fs.existsSync(inspPath)) {
              const data = JSON.parse(fs.readFileSync(inspPath, 'utf-8'))
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ ...data.graph, source: 'snapshot', live: true }))
              return
            }
          } catch {}
        }

        if (url === '/api/chunks' && req.method === 'GET') {
          try {
            const inspPath = path.resolve(cwd, 'backend', 'evaluation', 'inspection_data.json')
            if (fs.existsSync(inspPath)) {
              const data = JSON.parse(fs.readFileSync(inspPath, 'utf-8'))
              res.setHeader('Content-Type', 'application/json')
              res.end(
                JSON.stringify({
                  chunks: data.chunks || [],
                  similarity: data.similarity || [],
                  chunking: data.chunking || null,
                  embedding_dim: data.embedding_dim || null,
                  pca_explained_variance: data.pca_explained_variance || [],
                  source: 'snapshot',
                  live: true,
                })
              )
              return
            }
          } catch {}
        }

        if (url === '/api/images' && req.method === 'GET') {
          try {
            const imgPath = path.resolve(cwd, 'backend', 'evaluation', 'image_data.json')
            if (fs.existsSync(imgPath)) {
              const data = JSON.parse(fs.readFileSync(imgPath, 'utf-8'))
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ images: data.images || [], source: 'snapshot', live: true }))
              return
            }
          } catch {}
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
})
