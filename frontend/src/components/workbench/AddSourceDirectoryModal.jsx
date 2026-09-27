import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'

import {
  X,
  FolderPlus,
  FilePlus,
  Folder,
  HardDrive,
  CheckCircle2,
  Trash2,
  UploadCloud,
  Plus,
  Loader2,
  FileText,
  Check,
  AlertCircle,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { showToast } from '../../store/toastStore'
import { useIngestionStore } from '../../store/ingestionStore'

// Helper to convert browser File object to Base64
const readFileAsBase64 = (file) => {
  return new Promise((resolve, reject) => {
    if (!file || file.size === 0) {
      resolve('')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result === 'string') {
        const comma = result.indexOf(',')
        resolve(comma >= 0 ? result.slice(comma + 1) : result)
      } else {
        resolve('')
      }
    }
    reader.onerror = (err) => reject(err)
    reader.readAsDataURL(file)
  })
}

export function AddSourceDirectoryModal({ isOpen, onClose, onDirectoriesUpdated, currentDirectories = [] }) {
  const [customPath, setCustomPath] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const folderInputRef = useRef(null)
  const fileInputRef = useRef(null)

  const activeJob = useIngestionStore((s) => s.activeJob)
  const startTracking = useIngestionStore((s) => s.startTracking)

  // Auto-close modal when an in-progress job finishes (activeJob transitions
  // from running → complete/failed).
  const [jobStarted, setJobStarted] = useState(false)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (jobStarted && (activeJob?.state === 'complete' || activeJob?.state === 'failed')) {
      // Dispatch immediately on completion so sidebar updates chunks & tree right away
      window.dispatchEvent(new CustomEvent('corpus-updated'))
      if (onDirectoriesUpdated) onDirectoriesUpdated()

      const t = setTimeout(() => {
        setJobStarted(false)
        onCloseRef.current?.()
      }, 2500)
      return () => clearTimeout(t)
    }
  }, [activeJob?.state, jobStarted])

  // Core file batch upload handler
  const uploadFiles = async (fileList) => {
    const rawArray = Array.from(fileList || [])
    const filesArray = rawArray.filter((file) => {
      const p = (file.webkitRelativePath || file.name).replace(/\\/g, '/')
      const parts = p.split('/')
      const ignored = ['node_modules', '.git', '.venv', '__pycache__', '.idea', '.vscode', 'dist', 'build']
      return !parts.some((part) => ignored.includes(part) || part.startsWith('.'))
    })

    if (filesArray.length === 0) {
      showToast('No valid document files found in selected folder', 'info')
      return
    }

    setIsSubmitting(true)
    setUploadStatus(`Preparing ${filesArray.length} file(s)...`)

    try {
      const filesToUpload = []
      for (let i = 0; i < filesArray.length; i++) {
        const file = filesArray[i]
        if (file.size === 0) {
          showToast(`Skipped 0-byte empty file: ${file.name}`, 'warning')
          continue
        }
        setUploadStatus(`Reading ${i + 1}/${filesArray.length}: ${file.name}...`)
        try {
          const base64 = await readFileAsBase64(file)
          if (!base64) {
            showToast(`Could not read ${file.name} (file may be locked or empty)`, 'error')
            continue
          }
          const relPath = file.webkitRelativePath || file.name
          filesToUpload.push({
            name: file.name,
            relPath,
            contentBase64: base64,
            sizeBytes: file.size,
          })
        } catch (readErr) {
          console.warn(`Could not read file ${file.name}:`, readErr)
        }
      }

      if (filesToUpload.length === 0) {
        throw new Error('No readable non-empty files found to upload')
      }

      const res = await fetch('/api/sources/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: filesToUpload }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || data.detail || 'Failed to upload source file(s)')
      }

      // Start tracking AFTER the backend has registered the job
      if (data.job_id) {
        // Do NOT dispatch corpus-updated here — ingestion has not happened
        // yet. The useEffect watching activeJob.state === 'complete' handles
        // the refresh at the right moment (after all documents are indexed).
        startTracking(data.job_id)
        setJobStarted(true)
      } else {
        // Synchronous path (no background job) — safe to refresh now
        window.dispatchEvent(new CustomEvent('corpus-updated', { detail: data }))
        if (onDirectoriesUpdated) onDirectoriesUpdated(data)
        onClose()
      }
    } catch (err) {
      showToast(err.message || 'Failed to upload source documents', 'error')
    } finally {
      setIsSubmitting(false)
      setUploadStatus('')
    }
  }

  // Handle manual path submission
  const handleAddPath = async (e) => {
    e?.preventDefault()
    const pathToAdd = customPath.trim().replace(/^["']|["']$/g, '')
    if (!pathToAdd) {
      showToast('Please enter a valid directory or file path', 'error')
      return
    }

    setIsSubmitting(true)
    setUploadStatus('Resolving path, chunking document(s) & generating embeddings...')
    try {
      const res = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathToAdd, recursive: true }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || data.detail || 'Failed to add source')
      }

      showToast(data.message || `Source queued for indexing: ${pathToAdd}`, 'success')
      setCustomPath('')
      // Start tracking AFTER backend confirms the job exists.
      // Call startTracking BEFORE setJobStarted so activeJob is non-null
      // when the effect first evaluates jobStarted=true.
      if (data.job_id) {
        // Do NOT dispatch corpus-updated here — ingestion is still running.
        // The completion useEffect dispatches it once the job is done.
        startTracking(data.job_id)
        setJobStarted(true)
      } else {
        window.dispatchEvent(new CustomEvent('corpus-updated', { detail: data }))
        if (onDirectoriesUpdated) onDirectoriesUpdated(data)
        onClose()
      }
    } catch (err) {
      showToast(err.message || 'Failed to register source', 'error')
    } finally {
      setIsSubmitting(false)
      setUploadStatus('')
    }
  }

  // Native OS folder picker — instantly opens native folder dialog
  const handleBrowseFolder = async () => {
    // 1. Try modern directory picker (Chrome, Edge, Opera, Chromium)
    if (typeof window.showDirectoryPicker === 'function') {
      try {
        const dirHandle = await window.showDirectoryPicker({ mode: 'read' })
        if (dirHandle) {
          setIsSubmitting(true)
          setUploadStatus(`Reading contents of "${dirHandle.name}"…`)
          const files = []
          const scanHandle = async (handle, pathPrefix = '') => {
            for await (const entry of handle.values()) {
              const rel = pathPrefix ? `${pathPrefix}/${entry.name}` : entry.name
              if (entry.kind === 'file') {
                const f = await entry.getFile()
                Object.defineProperty(f, 'webkitRelativePath', {
                  value: `${dirHandle.name}/${rel}`,
                  writable: true,
                })
                files.push(f)
              } else if (entry.kind === 'directory') {
                const skip = ['node_modules', '.git', '.venv', '__pycache__', '.idea', '.vscode', 'dist', 'build']
                if (!skip.includes(entry.name) && !entry.name.startsWith('.')) {
                  await scanHandle(entry, rel)
                }
              }
            }
          }
          await scanHandle(dirHandle)
          if (files.length > 0) {
            await uploadFiles(files)
            return
          } else {
            showToast('No valid documents found in selected folder', 'info')
            setIsSubmitting(false)
            setUploadStatus('')
            return
          }
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          // User closed folder picker
          setIsSubmitting(false)
          setUploadStatus('')
          return
        }
        console.warn('showDirectoryPicker cancelled or error, falling back to input:', e)
      }
    }
    // 2. Fallback: trigger native OS folder picker input
    folderInputRef.current?.click()
  }

  // Native OS file picker — instantly opens native Windows file explorer dialog
  const handleBrowseFiles = () => {
    fileInputRef.current?.click()
  }

  // Handle native folder browse input
  const handleFolderPicked = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    await uploadFiles(files)
    e.target.value = ''
  }

  // Handle native files browse input
  const handleFilesPicked = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    await uploadFiles(files)
    e.target.value = ''
  }

  // Handle drag & drop with recursive folder traversal
  const handleDrop = async (e) => {
    e.preventDefault()
    setDragOver(false)
    if (!e.dataTransfer) return

    const items = e.dataTransfer.items
    if (items && items.length > 0) {
      const filesToProcess = []

      const traverseEntry = async (item, pathPrefix = '') => {
        return new Promise((resolve) => {
          if (item.isFile) {
            item.file((file) => {
              Object.defineProperty(file, 'webkitRelativePath', {
                value: pathPrefix ? `${pathPrefix}/${file.name}` : file.name,
                writable: true,
              })
              filesToProcess.push(file)
              resolve()
            })
          } else if (item.isDirectory) {
            const dirReader = item.createReader()
            const readEntries = () => {
              dirReader.readEntries(async (entries) => {
                if (entries.length === 0) {
                  resolve()
                } else {
                  for (const entry of entries) {
                    await traverseEntry(entry, pathPrefix ? `${pathPrefix}/${item.name}` : item.name)
                  }
                  readEntries()
                }
              })
            }
            readEntries()
          } else {
            resolve()
          }
        })
      }

      const entries = []
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null
        if (entry) entries.push(entry)
      }

      if (entries.length > 0) {
        for (const entry of entries) {
          await traverseEntry(entry)
        }
        if (filesToProcess.length > 0) {
          await uploadFiles(filesToProcess)
          return
        }
      }
    }

    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      await uploadFiles(files)
    }
  }

  // Remove directory
  const handleRemoveDir = async (dirPath) => {
    try {
      const res = await fetch(`/api/sources?path=${encodeURIComponent(dirPath)}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        showToast('Source removed from retrieval scope', 'info')
        window.dispatchEvent(new CustomEvent('corpus-updated'))
        if (onDirectoriesUpdated) onDirectoriesUpdated()
      }
    } catch {
      showToast('Failed to remove source', 'error')
    }
  }

  const modalContent = (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="add-source-modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0, 0, 0, 0.55)', backdropFilter: 'blur(4px)' }}
          onClick={onClose}
        >
          <motion.div
            key="add-source-modal-card"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-lg rounded-xl shadow-2xl border flex flex-col overflow-hidden"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
            onClick={(e) => e.stopPropagation()}
          >

        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{
                background: 'var(--color-accent-tint, rgba(37,99,235,0.12))',
                color: 'var(--color-accent)',
                border: '1px solid var(--color-border)',
              }}
            >
              <FolderPlus size={16} strokeWidth={2.2} />
            </div>
            <div>
              <h3 className="text-sm font-bold leading-tight" style={{ color: 'var(--color-text)' }}>
                Add Source Directories & Files
              </h3>
              <p className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                Air-gapped on-prem ingestion into local knowledge base
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
          >
            <X size={15} />
          </button>
        </div>

        {/* Hidden inputs for instant native file & folder picking */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.xlsx,.xls,.txt,.csv,.json,.md,.yaml,.yml,.py,.sql,.png,.jpg,.jpeg"
          style={{ display: 'none' }}
          onChange={handleFilesPicked}
        />
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          style={{ display: 'none' }}
          onChange={handleFolderPicked}
        />

        {/* Modal Body */}
        <div className="p-5 flex flex-col gap-4 overflow-y-auto max-h-[75vh]">
          {/* Quick Browse Buttons (Native System Picker) */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleBrowseFolder}
              className="flex items-center gap-2.5 p-3 rounded-lg border text-left transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] group disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'var(--color-bg)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-accent)',
                }}
              >
                <Folder size={16} />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Browse Folder…
                </span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  Pick directory from PC
                </span>
              </div>
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleBrowseFiles}
              className="flex items-center gap-2.5 p-3 rounded-lg border text-left transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] group disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'var(--color-bg)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: '#059669',
                }}
              >
                <FilePlus size={16} />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Browse Files…
                </span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  PDF, DOCX, XLSX, PNG
                </span>
              </div>
            </button>
          </div>

          {/* Active Ingestion Progress Card (Live Polling via backend ProgressTracker) */}
          {(isSubmitting || (activeJob && (activeJob.state === 'running' || activeJob.state === 'complete' || activeJob.state === 'failed'))) && (
            <div
              className="flex flex-col gap-3 p-4 rounded-xl border animate-fade-in"
              style={{
                background: activeJob?.state === 'complete'
                  ? 'rgba(16, 185, 129, 0.08)'
                  : activeJob?.state === 'failed'
                  ? 'rgba(239, 68, 68, 0.08)'
                  : 'var(--color-accent-tint, rgba(37,99,235,0.06))',
                borderColor: activeJob?.state === 'complete'
                  ? 'rgba(16, 185, 129, 0.4)'
                  : activeJob?.state === 'failed'
                  ? 'rgba(239, 68, 68, 0.4)'
                  : 'var(--color-accent)',
              }}
            >
              {/* ── Stage pipeline header ── */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {activeJob?.state === 'complete' ? (
                    <CheckCircle2 size={15} className="text-emerald-500 flex-shrink-0" />
                  ) : activeJob?.state === 'failed' ? (
                    <AlertCircle size={15} className="text-red-500 flex-shrink-0" />
                  ) : (
                    <Loader2 size={14} className="animate-spin text-[var(--color-accent)] flex-shrink-0" />
                  )}
                  <span className="font-bold text-xs" style={{ color: 'var(--color-text)' }}>
                    {activeJob?.state === 'complete'
                      ? `Done \u2014 ${activeJob.completed || activeJob.total_documents} file(s) indexed`
                      : activeJob?.state === 'failed'
                      ? `Failed: ${activeJob.error || 'Unknown error'}`
                      : activeJob?.total_documents
                      ? (activeJob.total_documents > 1
                          ? `Processing ${Math.min((activeJob.completed || 0) + 1, activeJob.total_documents)} / ${activeJob.total_documents} file(s)`
                          : 'Processing 1 / 1 file')
                      : uploadStatus || 'Initialising\u2026'}
                  </span>
                </div>
                {/* Live elapsed timer */}
                {activeJob?.elapsed_seconds != null && (
                  <span className="text-[10px] font-mono tabular-nums flex-shrink-0" style={{ color: 'var(--color-text-muted)' }}>
                    {activeJob.state === 'complete'
                      ? `\u2713 ${activeJob.elapsed_seconds}s`
                      : activeJob.state === 'running' && activeJob.estimated_remaining_seconds
                      ? `${activeJob.elapsed_seconds}s \u00b7 ~${activeJob.estimated_remaining_seconds}s left`
                      : `${activeJob.elapsed_seconds}s`}
                  </span>
                )}
              </div>

              {/* ── 4-step pipeline visualiser ── */}
              {(() => {
                const STAGES = [
                  { key: 'extracting', label: 'Extract', desc: 'Reading & OCR' },
                  { key: 'chunking',   label: 'Chunk',   desc: 'Splitting text' },
                  { key: 'embedding',  label: 'Embed',   desc: 'Vectorising' },
                  { key: 'indexing',   label: 'Index',   desc: 'Writing FAISS' },
                ]
                const currentStage = activeJob?.current_document?.stage || ''
                let stageIdx = STAGES.findIndex(s => s.key === currentStage)
                if (stageIdx === -1 && (currentStage === 'queued' || activeJob?.state === 'running')) {
                  stageIdx = 0
                }
                const isComplete = activeJob?.state === 'complete'
                const isFailed   = activeJob?.state === 'failed'
                // Within-file pseudo-progress: each of 4 stages = 25%, active = midpoint
                const stageProgress = isComplete ? 100
                  : isFailed ? 100
                  : stageIdx >= 0 ? Math.max(14, Math.round((stageIdx + 0.55) * 25))
                  : activeJob?.total_documents > 0
                    ? Math.max(10, Math.round(((activeJob.completed || 0) / activeJob.total_documents) * 100))
                    : activeJob?.state === 'running' ? 12 : 0
                return (
                  <div className="flex flex-col gap-2.5">
                    {/* Stage bubbles + connectors */}
                    <div className="flex items-start">
                      {STAGES.map((s, i) => {
                        const done    = isComplete || stageIdx > i
                        const active  = !isComplete && !isFailed && stageIdx === i
                        const failed  = isFailed && stageIdx === i
                        const pending = !done && !active && !failed
                        return (
                          <div key={s.key} className="flex items-center flex-1 min-w-0">
                            <div className="flex flex-col items-center" style={{ flex: 1 }}>
                              {/* Circle */}
                              <div
                                className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-500"
                                style={{
                                  background: done ? 'rgba(16,185,129,0.18)' : active ? 'var(--color-accent)' : failed ? 'rgba(239,68,68,0.18)' : 'var(--color-overlay)',
                                  border: done ? '1.5px solid rgba(16,185,129,0.5)' : active ? '1.5px solid var(--color-accent)' : failed ? '1.5px solid rgba(239,68,68,0.4)' : '1.5px solid var(--color-border)',
                                  color: done ? '#10b981' : active ? '#fff' : failed ? '#ef4444' : 'var(--color-text-faint)',
                                  boxShadow: active ? '0 0 0 3px rgba(37,99,235,0.18)' : 'none',
                                }}
                              >
                                {done ? '\u2713' : failed ? '\u2715' : i + 1}
                              </div>
                              {/* Label */}
                              <span className="text-[9px] font-semibold mt-0.5 uppercase tracking-wide" style={{ color: done ? '#10b981' : active ? 'var(--color-accent)' : 'var(--color-text-faint)' }}>
                                {s.label}
                              </span>
                              {/* Sub-desc only on active */}
                              {active && (
                                <span className="text-[8.5px] mt-0.5 text-center leading-tight" style={{ color: 'var(--color-text-muted)' }}>
                                  {s.desc}
                                </span>
                              )}
                            </div>
                            {/* Connector */}
                            {i < STAGES.length - 1 && (
                              <div className="h-px flex-1 mx-0.5 transition-all duration-500" style={{ background: done ? 'rgba(16,185,129,0.4)' : 'var(--color-border)', marginTop: '-14px' }} />
                            )}
                          </div>
                        )
                      })}
                    </div>

                    {/* Progress bar */}
                    <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-border)' }}>
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${stageProgress}%`,
                          background: isComplete
                            ? 'linear-gradient(90deg,#10b981,#34d399)'
                            : isFailed
                            ? '#ef4444'
                            : 'linear-gradient(90deg,var(--color-accent),#60a5fa)',
                        }}
                      />
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-[9px]" style={{ color: 'var(--color-text-faint)' }}>
                        {isComplete
                          ? 'All stages complete'
                          : isFailed
                          ? 'Pipeline failed'
                          : stageIdx >= 0
                          ? `Stage ${stageIdx + 1} of 4 \u2014 ${STAGES[stageIdx]?.desc}`
                          : activeJob?.state === 'running'
                          ? 'Stage 1 of 4 \u2014 Starting pipeline\u2026'
                          : 'Ready'}
                      </span>
                      <span className="text-[9px] font-mono tabular-nums" style={{ color: 'var(--color-text-faint)' }}>
                        {stageProgress}%
                      </span>
                    </div>
                  </div>
                )
              })()}

              {/* ── Current file banner ── */}
              {activeJob?.current_document && activeJob.state !== 'complete' && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                  <FileText size={12} className="flex-shrink-0" style={{ color: 'var(--color-accent)' }} />
                  <span className="font-mono text-[10.5px] truncate flex-1" style={{ color: 'var(--color-text)' }}>
                    {activeJob.current_document.name}
                  </span>
                  <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded font-semibold flex-shrink-0"
                    style={{ background: 'var(--color-accent-tint)', border: '1px solid var(--color-accent-border)', color: 'var(--color-accent)' }}>
                    {activeJob.current_document.stage}
                  </span>
                </div>
              )}

              {/* ── Per-doc list (multi-file) ── */}
              {activeJob?.documents && activeJob.documents.length > 1 && (
                <div className="flex flex-col gap-0.5 max-h-28 overflow-y-auto pr-1">
                  {activeJob.documents.map((doc, idx) => {
                    const done    = doc.stage === 'indexed'
                    const running = ['extracting','chunking','embedding','indexing'].includes(doc.stage)
                    const failed  = doc.stage === 'failed'
                    return (
                      <div key={doc.path || idx} className="flex items-center justify-between py-1 px-2 rounded text-[10.5px]" style={{ background: running ? 'var(--color-surface)' : 'transparent' }}>
                        <span className="truncate pr-2 font-mono" style={{ color: 'var(--color-text)' }}>{doc.name}</span>
                        <span className="flex-shrink-0 font-semibold text-[9.5px]" style={{ color: done ? '#10b981' : running ? 'var(--color-accent)' : failed ? '#ef4444' : 'var(--color-text-faint)' }}>
                          {done ? '\u2713 indexed' : running ? `\u27f3 ${doc.stage}` : failed ? '\u2715 failed' : 'queued'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Drag & Drop Zone */}
          <div
            onDragOver={(e) => {
              if (isSubmitting) return
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-4 flex flex-col items-center justify-center text-center transition-fast ${
              isSubmitting ? 'opacity-50 pointer-events-none' : ''
            }`}
            style={{
              borderColor: dragOver ? 'var(--color-accent)' : 'var(--color-border-strong, var(--color-border))',
              background: dragOver ? 'var(--color-overlay)' : 'var(--color-bg)',
            }}
          >
            <UploadCloud
              size={24}
              strokeWidth={1.8}
              className="mb-1.5"
              style={{ color: dragOver ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
            />
            <span className="text-xs font-medium" style={{ color: 'var(--color-text)' }}>
              Drag and drop folders or files here
            </span>
            <span className="text-[10px] mt-0.5" style={{ color: 'var(--color-text-faint)' }}>
              Browser sandboxed transfer. For zero-copy in-place indexing, use Browse or Path below.
            </span>
          </div>

          {/* Manual Path Entry Form */}
          <form onSubmit={handleAddPath} className="flex flex-col gap-2">
            <label className="text-xs font-semibold flex items-center justify-between">
              <span style={{ color: 'var(--color-text)' }}>Enter Host Filesystem Path</span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                Absolute or relative
              </span>
            </label>
            <div className="flex items-center gap-2">
              <div
                className="flex-1 flex items-center gap-2 px-3 py-2 rounded-md border text-xs"
                style={{
                  background: 'var(--color-bg)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <HardDrive size={14} className="flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                <input
                  type="text"
                  value={customPath}
                  onChange={(e) => setCustomPath(e.target.value)}
                  placeholder="e.g. C:\SIH\SIH26117-Sovereign-Workbench\MRPL_Chart_Stress_Corpus"
                  className="flex-1 bg-transparent outline-none font-mono text-[11px]"
                  style={{ color: 'var(--color-text)' }}
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting || !customPath.trim()}
                className="px-3.5 py-2 rounded-md text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-fast cursor-pointer disabled:opacity-50"
                style={{
                  background: 'var(--color-accent)',
                  color: '#fff',
                }}
              >
                <Plus size={13} strokeWidth={2.4} />
                <span>Add</span>
              </button>
            </div>
          </form>

          {/* Watched Directories List */}
          <div className="flex flex-col gap-2 pt-2 border-t" style={{ borderColor: 'var(--color-border)' }}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold uppercase tracking-wider text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                Active Watched Directories ({currentDirectories.length})
              </span>
              <span className="text-[10px] text-muted font-mono">Dynamic On-Disk Sync</span>
            </div>

            <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto pr-1">
              {currentDirectories.map((dir) => (
                <div
                  key={dir.id || dir.path}
                  className="flex items-center justify-between p-2 rounded-md border text-xs"
                  style={{
                    background: 'var(--color-bg)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0 pr-2">
                    <CheckCircle2
                      size={13}
                      className="flex-shrink-0"
                      style={{ color: 'var(--color-success, #2f7a52)' }}
                    />
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1.5 truncate">
                        <span className="font-semibold text-[11px] truncate" style={{ color: 'var(--color-text)' }}>
                          {dir.name}
                        </span>
                        {dir.isPreset && (
                          <span
                            className="text-[9px] px-1 py-0.2 rounded font-mono font-semibold"
                            style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
                          >
                            DEFAULT
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono truncate" style={{ color: 'var(--color-text-muted)' }} title={dir.fullPath || dir.path}>
                        {dir.fullPath || dir.path}
                      </span>
                    </div>
                  </div>

                  {!dir.isPreset && (
                    <button
                      type="button"
                      onClick={() => handleRemoveDir(dir.path)}
                      className="p-1 rounded hover:bg-[var(--color-overlay)] text-muted hover:text-red-500 transition-fast cursor-pointer"
                      title="Remove from watched sources"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          className="px-5 py-3 border-t flex items-center justify-between"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
        >
          <span className="text-[11px]" style={{ color: 'var(--color-text-faint)' }}>
            Zero-egress: files are processed strictly on local hardware
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-xs font-medium border cursor-pointer hover:bg-[var(--color-surface)]"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
          >
            Done
          </button>
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
  // Render into document.body via portal so that position:fixed escapes
  // all ancestor transform/stacking contexts (motion.div layout animations).
  if (typeof document === 'undefined') return null
  return createPortal(modalContent, document.body)
}
