import { useState, useEffect, useCallback, useRef } from 'react'
import {
  X,
  FileText,
  Loader2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  FileCode,
  Download,
} from 'lucide-react'

// Simple in-memory render cache so reopening a file doesn't trigger re-render
const renderCache = new Map()

export function SourcePreviewModal({ file, isOpen, onClose }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [renderJob, setRenderJob] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [textContent, setTextContent] = useState(null)
  const [zoomLevel, setZoomLevel] = useState(100)
  const [unsupported, setUnsupported] = useState(false)

  const modalRef = useRef(null)

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Helper to derive clean API identifier (workspace-relative path)
  const getApiIdentifier = (file) => {
    if (!file) return ''
    if (file.relativePath) return file.relativePath
    if (file.corpus && file.relPath) {
      if (file.corpus === 'User Ingested Sources' || file.corpus === '07_User_Uploads') {
        return `MRPL_RAG_Test_Corpus/07_User_Uploads/${file.relPath}`
      }
      return `${file.corpus}/${file.relPath}`
    }
    return file.relPath || file.name
  }

  // Helper to derive clean user-facing logical location
  const getLogicalLocation = (file) => {
    if (!file) return ''
    const name = file.name || file.filename || ''
    const corpus = file.corpus || ''
    const relPath = (file.relPath || '').replace(/\\/g, '/')

    if (corpus && relPath) {
      if (relPath === name) {
        return `${corpus} / ${name}`
      }
      return `${corpus} / ${relPath.replace(/\//g, ' / ')}`
    }
    if (file.folder) {
      return `${corpus ? `${corpus} / ` : ''}${file.folder} / ${name}`
    }
    return corpus ? `${corpus} / ${name}` : name
  }

  // Process file whenever opened or changed
  useEffect(() => {
    if (!isOpen || !file) {
      setLoading(false)
      setError(null)
      setRenderJob(null)
      setPreviewUrl(null)
      setTextContent(null)
      setUnsupported(false)
      setCurrentPage(1)
      setTotalPages(1)
      setZoomLevel(100)
      return
    }

    const name = file.name || file.filename || ''
    const ext = (file.extension || name.slice(name.lastIndexOf('.') + 1)).toLowerCase()
    const filePath = getApiIdentifier(file)

    // Reset state
    setLoading(true)
    setError(null)
    setUnsupported(false)
    setTextContent(null)
    setPreviewUrl(null)
    setCurrentPage(1)
    setTotalPages(1)
    setZoomLevel(100)

    let cancelled = false

    // Route based on file type
    if (ext === 'pdf') {
      // PDF -> Serve directly via /api/sources/content
      const directUrl = `/api/sources/content?path=${encodeURIComponent(filePath)}`
      setPreviewUrl(directUrl)
      setLoading(false)
    } else if (['txt', 'md', 'json', 'csv', 'log', 'py', 'js', 'html', 'css', 'xml', 'yaml', 'yml'].includes(ext)) {
      // Plain text -> fetch via /api/sources/content
      fetch(`/api/sources/content?path=${encodeURIComponent(filePath)}`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to read text file`)
          return res.text()
        })
        .then((text) => {
          if (cancelled) return
          setTextContent(text)
          setLoading(false)
        })
        .catch((err) => {
          if (cancelled) return
          setError(err.message || 'Could not load text file content')
          setLoading(false)
        })
    } else if (['png', 'jpg', 'jpeg', 'webp', 'svg'].includes(ext)) {
      // Image -> Serve directly via /api/sources/content
      const directUrl = `/api/sources/content?path=${encodeURIComponent(filePath)}`
      setPreviewUrl(directUrl)
      setLoading(false)
    } else if (['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt'].includes(ext)) {
      // Office document -> Sandbox render pipeline
      const cacheKey = filePath
      if (renderCache.has(cacheKey)) {
        const cached = renderCache.get(cacheKey)
        setPreviewUrl(cached.preview_url)
        setTotalPages(cached.page_count || 1)
        setLoading(false)
        return
      }

      // Submit render job
      fetch('/api/sandbox/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath }),
      })
        .then((res) => {
          if (!res.ok) return res.json().then((d) => Promise.reject(new Error(d.detail || 'Render submission failed')))
          return res.json()
        })
        .then((data) => {
          if (cancelled) return
          const jobId = data.job_id

          // Poll job status
          const pollInterval = setInterval(() => {
            if (cancelled) {
              clearInterval(pollInterval)
              return
            }
            fetch(`/api/sandbox/render/${jobId}`)
              .then((r) => r.json())
              .then((job) => {
                if (cancelled) return
                if (job.status === 'ready') {
                  clearInterval(pollInterval)
                  setRenderJob(job)
                  setPreviewUrl(job.preview_url)
                  setTotalPages(job.page_count || 1)
                  setLoading(false)

                  // Save to render cache
                  renderCache.set(cacheKey, job)
                } else if (job.status === 'failed') {
                  clearInterval(pollInterval)
                  setError(job.error || 'Sandboxed document conversion failed')
                  setLoading(false)
                }
              })
              .catch((err) => {
                clearInterval(pollInterval)
                if (!cancelled) {
                  setError(err.message || 'Error polling conversion job')
                  setLoading(false)
                }
              })
          }, 400)
        })
        .catch((err) => {
          if (cancelled) return
          setError(err.message || 'Failed to submit document for conversion')
          setLoading(false)
        })
    } else {
      // Unsupported file type
      setUnsupported(true)
      setLoading(false)
    }

    return () => {
      cancelled = true
    }
  }, [isOpen, file])

  if (!isOpen || !file) return null

  const name = file.name || file.filename || 'Document'
  const ext = (file.extension || name.slice(name.lastIndexOf('.') + 1)).toUpperCase()

  const handleZoomIn = () => setZoomLevel((z) => Math.min(z + 25, 250))
  const handleZoomOut = () => setZoomLevel((z) => Math.max(z - 25, 50))
  const handleZoomReset = () => setZoomLevel(100)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={(e) => {
        if (modalRef.current && !modalRef.current.contains(e.target)) {
          onClose()
        }
      }}
    >
      <div
        ref={modalRef}
        className="flex flex-col w-full max-w-5xl h-[85vh] rounded-xl border shadow-2xl overflow-hidden select-none"
        style={{
          background: 'var(--color-bg)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }}
      >
        {/* ── Modal Header ────────────────────────────────────────────── */}
        <div
          className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0"
          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider flex-shrink-0"
              style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
            >
              {ext}
            </div>
            <div className="flex flex-col min-w-0">
              <h2 className="text-sm font-bold truncate leading-tight" style={{ color: 'var(--color-text)' }}>
                {name}
              </h2>
              <span className="text-[10px] font-mono truncate" style={{ color: 'var(--color-text-muted)' }}>
                {getLogicalLocation(file)}
              </span>
            </div>
          </div>

          {/* Header Controls */}
          <div className="flex items-center gap-3 flex-shrink-0">
            {/* Page Navigation for multi-page rendered docs */}
            {totalPages > 1 && !loading && !error && (
              <div
                className="flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-mono"
                style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
              >
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="p-0.5 rounded hover:bg-[var(--color-overlay)] disabled:opacity-30 cursor-pointer"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="px-1 font-semibold">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="p-0.5 rounded hover:bg-[var(--color-overlay)] disabled:opacity-30 cursor-pointer"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            )}

            {/* Zoom Controls */}
            {(previewUrl || textContent) && !loading && !error && (
              <div
                className="flex items-center gap-1 p-0.5 rounded-md border text-xs"
                style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
              >
                <button
                  type="button"
                  onClick={handleZoomOut}
                  className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
                  title="Zoom Out"
                >
                  <ZoomOut size={13} />
                </button>
                <span className="text-[10px] font-mono px-1 font-semibold">{zoomLevel}%</span>
                <button
                  type="button"
                  onClick={handleZoomIn}
                  className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
                  title="Zoom In"
                >
                  <ZoomIn size={13} />
                </button>
                <button
                  type="button"
                  onClick={handleZoomReset}
                  className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
                  title="Reset Zoom"
                >
                  <RotateCcw size={12} />
                </button>
              </div>
            )}

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-md border text-muted hover:text-[var(--color-text)] hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
              style={{ borderColor: 'var(--color-border)' }}
              title="Close preview (Esc)"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── Modal Content Body ──────────────────────────────────────── */}
        <div className="flex-1 min-h-0 overflow-auto p-4 flex items-center justify-center relative bg-[var(--color-bg)] custom-scrollbar">
          {/* 1. Loading State */}
          {loading && (
            <div className="flex flex-col items-center justify-center p-8 gap-3 text-center">
              <Loader2 size={32} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-semibold">Generating Sandboxed Document Preview…</span>
                <span className="text-xs text-muted">
                  Converting {ext} inside isolated container (Step 2/3 Sandbox)
                </span>
              </div>
            </div>
          )}

          {/* 2. Error State */}
          {error && !loading && (
            <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md text-center rounded-xl border border-red-500/30 bg-red-500/5">
              <AlertCircle size={32} className="text-red-500" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-bold text-red-500">Preview Generation Failed</span>
                <p className="text-xs text-muted leading-relaxed font-mono">{error}</p>
              </div>
            </div>
          )}

          {/* 3. Unsupported State */}
          {unsupported && !loading && (
            <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md text-center rounded-xl border p-6" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
              <FileCode size={36} className="text-amber-500" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-bold">Preview Not Available</span>
                <p className="text-xs text-muted leading-relaxed">
                  No visual preview adapter is registered for <b>.{ext.toLowerCase()}</b> files in this air-gapped workbench.
                </p>
                <span className="text-[11px] font-mono mt-2 p-2 rounded bg-[var(--color-overlay)] text-muted">
                  File Size: {file.size || 'Unknown'} · Location: {file.folder || 'Corpus Root'}
                </span>
              </div>
            </div>
          )}

          {/* 4. PDF Preview */}
          {ext.toLowerCase() === 'pdf' && previewUrl && !loading && !error && (
            <div className="w-full h-full flex items-center justify-center">
              <object
                data={previewUrl}
                type="application/pdf"
                className="w-full h-full rounded-lg border"
                style={{
                  borderColor: 'var(--color-border)',
                  transform: `scale(${zoomLevel / 100})`,
                  transformOrigin: 'top center',
                  transition: 'transform 0.15s ease-out',
                }}
              >
                <iframe src={previewUrl} className="w-full h-full rounded-lg border" title={name} />
              </object>
            </div>
          )}

          {/* 5. Sandboxed Rendered Office Doc Preview (PNG page or PDF) */}
          {['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt'].includes(ext.toLowerCase()) && previewUrl && !loading && !error && (
            <div className="flex flex-col items-center justify-start min-h-full py-4 overflow-auto">
              <img
                src={`${previewUrl}?page=${currentPage}`}
                alt={`${name} - Page ${currentPage}`}
                className="max-w-full rounded-lg shadow-lg border bg-white object-contain"
                style={{
                  borderColor: 'var(--color-border)',
                  transform: `scale(${zoomLevel / 100})`,
                  transformOrigin: 'top center',
                  transition: 'transform 0.15s ease-out',
                }}
              />
            </div>
          )}

          {/* 6. Direct Image Preview */}
          {['png', 'jpg', 'jpeg', 'webp', 'svg'].includes(ext.toLowerCase()) && previewUrl && !loading && !error && (
            <div className="flex items-center justify-center p-4 min-h-full">
              <img
                src={previewUrl}
                alt={name}
                className="max-w-full max-h-full rounded-lg shadow-md border object-contain bg-white"
                style={{
                  borderColor: 'var(--color-border)',
                  transform: `scale(${zoomLevel / 100})`,
                  transformOrigin: 'center center',
                  transition: 'transform 0.15s ease-out',
                }}
              />
            </div>
          )}

          {/* 7. Plain Text Preview */}
          {textContent !== null && !loading && !error && (
            <div className="w-full h-full flex flex-col p-2">
              <pre
                className="w-full h-full p-4 rounded-lg font-mono text-xs leading-relaxed overflow-auto whitespace-pre-wrap border select-text custom-scrollbar"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                  fontSize: `${(12 * zoomLevel) / 100}px`,
                }}
              >
                {textContent}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
