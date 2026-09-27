import React, { useState, useEffect } from 'react'
import { Download, FileText, FileSpreadsheet, Presentation, Filter, FolderDown, Eye } from 'lucide-react'
import { OutputJobsList } from './OutputJobsList'
import { usePreviewStore } from '../../store/previewStore'

// Sent by the approval flow the moment a file is written, so the list
// shows it at once instead of on the next 10 s poll.
export const OUTPUTS_CHANGED = 'workbench:outputs-changed'

const ICONS = {
  docx: { icon: FileText, color: '#3b82f6', label: 'DOCX' },
  xlsx: { icon: FileSpreadsheet, color: '#10b981', label: 'XLSX' },
  pptx: { icon: Presentation, color: '#f59e0b', label: 'PPTX' },
  pdf: { icon: FileText, color: '#ef4444', label: 'PDF' },
}

/**
 * RealOutputCards — Real deliverable component by Kanishka (FRONTEND.md §3.7).
 * Connects directly to GET /api/outputs to list real generated files from storage/outputs/.
 */
export default function RealOutputCards({
  files: initialFiles = [],
  onDownload,
  filterType: initialFilter = 'all',
}) {
  const [files, setFiles] = useState(initialFiles)
  const [filter, setFilter] = useState(initialFilter)
  const [isLoading, setIsLoading] = useState(false)
  // Why the list is empty matters: nothing generated yet is not the same as
  // the backend being unreachable, and the page must not say "LIVE" either way.
  const [loadError, setLoadError] = useState(null)

  // Fetch real outputs from the backend
  useEffect(() => {
    let active = true
    const fetchOutputs = async () => {
      try {
        setIsLoading(true)
        const res = await fetch('/api/outputs')
        if (!active) return
        if (!res.ok) {
          setLoadError(`The backend answered ${res.status} for /api/outputs.`)
          return
        }
        const data = await res.json()
        // THE REAL LIST, INCLUDING WHEN IT IS EMPTY. This kept a built-in
        // sample list of three deliverables -- an "HCU Runaway Mitigation
        // Approval Note" about a 115% feed rate among them -- and showed it
        // whenever the backend returned nothing or could not be reached,
        // with download buttons, on a page headed LIVE OUTPUTS. Nobody
        // approved those files and they do not exist.
        setFiles(Array.isArray(data.files) ? data.files : [])
        setLoadError(null)
      } catch (err) {
        if (active) setLoadError(`Could not reach the backend (${err?.message || 'network error'}).`)
      } finally {
        if (active) setIsLoading(false)
      }
    }
    fetchOutputs()
    const timer = setInterval(fetchOutputs, 10000)
    window.addEventListener(OUTPUTS_CHANGED, fetchOutputs)
    return () => {
      active = false
      clearInterval(timer)
      window.removeEventListener(OUTPUTS_CHANGED, fetchOutputs)
    }
  }, [])

  const handleDownload = (file) => {
    if (onDownload) {
      onDownload(file.id)
      return
    }
    // Direct browser download from storage/outputs/
    const downloadUrl = `/api/outputs/${encodeURIComponent(file.filename)}/download`
    const a = document.createElement('a')
    a.href = downloadUrl
    a.download = file.filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const openPreview = usePreviewStore((s) => s.openPreview)
  // The newest file, if it was written in the last few minutes: the one the
  // operator just approved, which is what they came to this tab to find.
  const newest = files.length && Date.now() / 1000 - (files[0].writtenAt || 0) < 300 ? files[0].filename : null

  const filtered = files.filter((f) => {
    if (filter === 'all') return true
    return (f.fileType || '').toLowerCase() === filter.toLowerCase()
  })

  return (
    <div className="flex-1 flex flex-col h-full min-w-0 p-6 overflow-y-auto overflow-x-hidden" style={{ background: 'var(--color-bg)' }}>
      {/* ── Top Header & Integration Banner ─────────────────────────────── */}
      <div
        className="p-5 rounded-2xl border mb-6 flex flex-wrap items-center justify-between gap-4 shadow-sm"
        style={{
          background: 'var(--color-card-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1 basis-[320px]">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{
              background: 'var(--color-accent-tint)',
              color: 'var(--color-accent)',
              border: '1px solid var(--color-border)',
            }}
          >
            <FolderDown size={20} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold tracking-tight whitespace-nowrap" style={{ color: 'var(--color-text)' }}>
                Generated Deliverable Library
              </h2>
              <span
                className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider whitespace-nowrap"
                style={{
                  background: 'var(--color-success-tint)',
                  color: 'var(--color-success)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                }}
              >
                {loadError ? 'BACKEND UNREACHABLE' : `LIVE OUTPUTS (${files.length})`}
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
              Approved, approval-gated deliverables in <code>outputs/</code> — DOCX, XLSX, PPTX &amp; PDF (FRONTEND.md §3.7).
            </p>
          </div>
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 p-1 rounded-lg border bg-surface/50 text-xs font-mono flex-shrink-0">
          <Filter size={13} className="text-zinc-400 ml-1.5 mr-0.5" />
          {['all', 'docx', 'xlsx', 'pptx', 'pdf'].map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFilter(t)}
              className="px-2.5 py-1 rounded-md transition-colors uppercase font-medium text-[11px]"
              style={{
                background: filter === t ? 'var(--color-accent)' : 'transparent',
                color: filter === t ? '#ffffff' : 'var(--color-text-muted)',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* ── Jobs being written right now ────────────────────────────────── */}
      <OutputJobsList />

      {/* ── File Grid ───────────────────────────────────────────────────── */}
      {loadError ? (
        <div className="p-12 text-center rounded-xl border text-xs font-mono"
             style={{ color: 'var(--color-text-muted)', borderColor: 'var(--color-border)' }}>
          {loadError} Nothing is listed rather than showing files that may not exist.
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-12 text-center rounded-xl border text-xs font-mono"
             style={{ color: 'var(--color-text-muted)', borderColor: 'var(--color-border)' }}>
          {isLoading
            ? 'Reading the outputs directory…'
            : filter === 'all'
              ? 'No deliverables yet. Ask for a presentation, report or spreadsheet in chat; it appears here once you approve it.'
              : `No ${filter.toUpperCase()} deliverables yet.`}
        </div>
      ) : (
        <div className="grid gap-4 w-full" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))' }}>
          {filtered.map((file) => {
            const ext = (file.fileType || '').toLowerCase()
            const typeConfig = ICONS[ext] || { icon: FileText, color: 'var(--color-accent)', label: ext.toUpperCase() }
            const Icon = typeConfig.icon

            return (
              <div
                key={file.id || file.filename}
                className="p-5 rounded-xl border flex flex-col justify-between gap-3 min-w-0 shadow-xs transition-all hover:border-zinc-400 dark:hover:border-zinc-600 hover:-translate-y-0.5 hover:shadow-md"
                style={{
                  background: 'var(--color-card-bg)',
                  borderColor: file.filename === newest ? 'var(--color-accent)' : 'var(--color-border)',
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="p-2.5 rounded-lg flex-shrink-0"
                    style={{ background: `${typeConfig.color}18`, color: typeConfig.color }}
                  >
                    <Icon size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4
                      className="font-bold text-xs leading-snug line-clamp-2 break-all"
                      style={{ color: 'var(--color-text)' }}
                      title={file.filename}
                    >
                      {file.filename}
                    </h4>
                    <p className="text-[11px] font-mono mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                      {typeConfig.label} · {file.fileSize || `${Math.round((file.sizeBytes || 0) / 1024)} KB`}
                      {file.filename === newest && <span style={{ color: 'var(--color-accent)' }}> · just written</span>}
                    </p>
                  </div>
                </div>

                <div
                  className="pt-3 border-t flex flex-wrap items-center justify-between gap-2"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <span className="text-[10px] font-mono whitespace-nowrap" style={{ color: 'var(--color-text-muted)' }}>
                    {file.generatedAt || ''}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0 ml-auto">
                  <button
                    type="button"
                    onClick={() => openPreview({ id: file.path, name: file.filename, filename: file.filename, relativePath: file.path, relPath: file.path, path: file.path, type: ext })}
                    className="px-3 py-1 rounded font-medium text-xs flex items-center gap-1.5 whitespace-nowrap transition-colors cursor-pointer border hover:bg-[var(--color-overlay)]"
                    style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                  >
                    <Eye size={12} />
                    <span>Open</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDownload(file)}
                    className="px-3 py-1 rounded font-medium text-xs flex items-center gap-1.5 whitespace-nowrap transition-colors cursor-pointer hover:brightness-110"
                    style={{
                      background: 'var(--color-accent)',
                      color: '#ffffff',
                    }}
                  >
                    <Download size={12} />
                    <span>Download</span>
                  </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
