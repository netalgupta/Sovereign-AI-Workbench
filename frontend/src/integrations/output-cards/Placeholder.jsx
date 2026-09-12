import React, { useState } from 'react'
import { FileSpreadsheet, FileText, Presentation, Download, Eye, ShieldCheck, Filter, FolderDown } from 'lucide-react'
import { CANONICAL_OUTPUTS } from './contract'

const TYPE_ICONS = {
  docx: { icon: FileText, color: '#3b82f6', label: 'DOCX' },
  xlsx: { icon: FileSpreadsheet, color: '#10b981', label: 'XLSX' },
  pptx: { icon: Presentation, color: '#f59e0b', label: 'PPTX' },
  pdf: { icon: FileText, color: '#ef4444', label: 'PDF' },
}

/**
 * Placeholder for OutputCards component.
 * Owner: Kanishka (FRONTEND.md §3.7)
 *
 * @param {import('./contract').OutputCardsProps} props
 */
export default function Placeholder({
  files = CANONICAL_OUTPUTS,
  onDownload,
  onPreview,
  filterType = 'all',
  onFilterChange,
  _layout = 'grid',
}) {
  const [activeFilter, setActiveFilter] = useState(filterType)

  const handleFilter = (type) => {
    setActiveFilter(type)
    if (onFilterChange) onFilterChange(type)
  }

  const filtered = files.filter((f) =>
    activeFilter === 'all' ? true : f.fileType === activeFilter
  )

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Top Header & Integration Handoff Banner ─────────────────────── */}
      <div
        className="px-6 py-4 border-b flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        style={{
          background: 'var(--color-card-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-accent)',
            }}
          >
            <FolderDown size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Generated Output Library
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                Integration pending — owned by Kanishka
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Deliverable files (DOCX, XLSX, PPTX) with source citation badges · FRONTEND.md §3.7
            </p>
          </div>
        </div>

        <div className="text-xs font-mono text-right" style={{ color: 'var(--color-text-muted)' }}>
          Total deliverables: <strong style={{ color: 'var(--color-text)' }}>{files.length}</strong>
        </div>
      </div>

      {/* ── Filter Bar ──────────────────────────────────────────────────── */}
      <div
        className="px-6 py-2.5 border-b flex items-center justify-between gap-4 text-xs"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-1.5">
          <Filter size={13} style={{ color: 'var(--color-text-muted)' }} />
          {['all', 'docx', 'xlsx', 'pptx'].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => handleFilter(type)}
              className="px-2.5 py-1 rounded text-xs uppercase font-mono font-medium transition-colors"
              style={{
                background: activeFilter === type ? 'var(--color-accent)' : 'transparent',
                color: activeFilter === type ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {/* ── Deliverables Grid ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-6xl mx-auto">
          {filtered.map((item) => {
            const typeConf = TYPE_ICONS[item.fileType] || TYPE_ICONS.docx
            const Icon = typeConf.icon
            return (
              <div
                key={item.id}
                className="rounded-xl border p-4 flex flex-col justify-between gap-4 transition-all duration-150 hover:shadow-sm"
                style={{
                  background: 'var(--color-card-bg)',
                  borderColor: 'var(--color-card-border)',
                }}
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: `${typeConf.color}20`, color: typeConf.color }}
                      >
                        <Icon size={16} />
                      </div>
                      <div>
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold"
                          style={{ background: `${typeConf.color}20`, color: typeConf.color }}
                        >
                          {typeConf.label}
                        </span>
                        <span className="text-[11px] font-mono ml-2" style={{ color: 'var(--color-text-muted)' }}>
                          {item.fileSize}
                        </span>
                      </div>
                    </div>

                    {/* Source Grounding Citations Badge */}
                    <div
                      className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono border"
                      style={{
                        background: 'var(--color-surface)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-accent)',
                      }}
                      title="Number of grounded citations backing this deliverable"
                    >
                      <ShieldCheck size={11} />
                      <span>{item.citationsCount} sources</span>
                    </div>
                  </div>

                  <h3 className="text-xs font-bold leading-snug" style={{ color: 'var(--color-text)' }}>
                    {item.filename}
                  </h3>
                  {item.summary && (
                    <p className="text-[11px] mt-1.5 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
                      {item.summary}
                    </p>
                  )}
                </div>

                <div
                  className="pt-3 border-t flex items-center justify-between text-[11px]"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                    {item.generatedAt}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => onPreview && onPreview(item.id)}
                      className="p-1.5 rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                      style={{ color: 'var(--color-text-muted)' }}
                      title="Preview deliverable"
                    >
                      <Eye size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDownload && onDownload(item.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded font-medium text-xs shadow-xs"
                      style={{
                        background: 'var(--color-accent)',
                        color: '#fff',
                      }}
                    >
                      <Download size={11} />
                      <span>Download</span>
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
