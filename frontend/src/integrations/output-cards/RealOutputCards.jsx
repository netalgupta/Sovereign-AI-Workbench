import React, { useState, useEffect } from 'react'
import { Sparkles, Download, CheckCircle2, FileText, FileSpreadsheet, Presentation, Filter, FolderDown } from 'lucide-react'
import { CANONICAL_OUTPUTS } from './contract'

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
  files: initialFiles = CANONICAL_OUTPUTS,
  onDownload,
  filterType: initialFilter = 'all',
}) {
  const [files, setFiles] = useState(initialFiles)
  const [filter, setFilter] = useState(initialFilter)
  const [isLoading, setIsLoading] = useState(false)

  // Fetch real outputs from the backend
  useEffect(() => {
    let active = true
    const fetchOutputs = async () => {
      try {
        setIsLoading(true)
        const res = await fetch('/api/outputs')
        if (res.ok && active) {
          const data = await res.json()
          if (Array.isArray(data.files) && data.files.length > 0) {
            setFiles(data.files)
          }
        }
      } catch {
        // Keep fallback on error
      } finally {
        if (active) setIsLoading(false)
      }
    }
    fetchOutputs()
    return () => {
      active = false
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

  const filtered = files.filter((f) => {
    if (filter === 'all') return true
    return (f.fileType || '').toLowerCase() === filter.toLowerCase()
  })

  return (
    <div className="flex-1 flex flex-col h-full p-6 overflow-y-auto" style={{ background: 'var(--color-bg)' }}>
      {/* ── Top Header & Integration Banner ─────────────────────────────── */}
      <div
        className="p-5 rounded-2xl border mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm"
        style={{
          background: 'var(--color-card-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{
              background: 'var(--color-accent-tint)',
              color: 'var(--color-accent)',
              border: '1px solid var(--color-border)',
            }}
          >
            <FolderDown size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Generated Deliverable Library
              </h2>
              <span
                className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider"
                style={{
                  background: 'var(--color-success-tint)',
                  color: 'var(--color-success)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                }}
              >
                LIVE OUTPUTS ({files.length})
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
              Sovereign generated artifacts in <code>storage/outputs/</code> · Approval-gated DOCX, XLSX, PPTX &amp; PDF (FRONTEND.md §3.7).
            </p>
          </div>
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 p-1 rounded-lg border bg-surface/50 text-xs font-mono">
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

      {/* ── File Grid ───────────────────────────────────────────────────── */}
      {filtered.length === 0 ? (
        <div className="p-12 text-center rounded-xl border text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
          No generated outputs found matching filter &quot;{filter.toUpperCase()}&quot;.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-6xl">
          {filtered.map((file) => {
            const ext = (file.fileType || '').toLowerCase()
            const typeConfig = ICONS[ext] || { icon: FileText, color: 'var(--color-accent)', label: ext.toUpperCase() }
            const Icon = typeConfig.icon

            return (
              <div
                key={file.id || file.filename}
                className="p-5 rounded-xl border flex flex-col justify-between gap-3 shadow-xs transition-all hover:border-zinc-400 dark:hover:border-zinc-600"
                style={{
                  background: 'var(--color-card-bg)',
                  borderColor: 'var(--color-border)',
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
                      className="font-bold text-xs truncate"
                      style={{ color: 'var(--color-text)' }}
                      title={file.filename}
                    >
                      {file.filename}
                    </h4>
                    <p className="text-[11px] font-mono mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                      {file.fileSize || `${Math.round((file.sizeBytes || 0) / 1024)} KB`} ·{' '}
                      {file.citationsCount || 0} verified citation(s)
                    </p>
                  </div>
                </div>

                <div
                  className="pt-3 border-t flex items-center justify-between"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                    {file.generatedAt || 'Recent'}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleDownload(file)}
                    className="px-3 py-1 rounded font-medium text-xs flex items-center gap-1.5 transition-colors cursor-pointer"
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
            )
          })}
        </div>
      )}
    </div>
  )
}
