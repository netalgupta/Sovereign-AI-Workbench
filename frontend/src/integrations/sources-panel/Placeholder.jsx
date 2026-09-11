import React, { useState } from 'react'
import { BookOpen, Upload, ShieldCheck, CheckCircle2, Circle, FileText, Filter } from 'lucide-react'
import { CANONICAL_SOURCES } from './contract'

/**
 * Placeholder for SourcesPanel component.
 * Owner: Netal (FRONTEND.md §3.5)
 *
 * @param {import('./contract').SourcesPanelProps} props
 */
export default function Placeholder({
  sources = CANONICAL_SOURCES,
  onToggleScope,
  onAddSource,
  onSourceSelect,
  activeCategory = 'all',
  onCategoryChange,
  _variant = 'full',
}) {
  const [localCategory, setLocalCategory] = useState(activeCategory)
  const [localSources, setLocalSources] = useState(sources)

  const handleToggle = (id) => {
    if (onToggleScope) {
      const target = localSources.find((s) => s.id === id)
      onToggleScope(id, !target?.inScope)
    }
    setLocalSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, inScope: !s.inScope } : s))
    )
  }

  const handleCategorySelect = (cat) => {
    setLocalCategory(cat)
    if (onCategoryChange) onCategoryChange(cat)
  }

  const filtered = localSources.filter((s) =>
    localCategory === 'all' ? true : s.category === localCategory
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
            <BookOpen size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Knowledge Base Sources
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                Integration pending — owned by Netal
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              NotebookLM-style grounded ingestion management · FRONTEND.md §3.5
            </p>
          </div>
        </div>

        {/* NFR-4 Grounding Trust Invariant Badge */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-accent-border)',
          }}
        >
          <ShieldCheck size={14} style={{ color: 'var(--color-accent)' }} />
          <span className="font-medium text-[11px]" style={{ color: 'var(--color-text)' }}>
            This session is grounded only in the sources listed here.
          </span>
        </div>
      </div>

      {/* ── Filter Bar & Actions ────────────────────────────────────────── */}
      <div
        className="px-6 py-2.5 border-b flex items-center justify-between gap-4 text-xs"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-1.5 overflow-x-auto py-0.5">
          <Filter size={13} style={{ color: 'var(--color-text-muted)' }} />
          {['all', 'sops', 'inspection', 'quality', 'sap_mock', 'correspondence', 'diagrams'].map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => handleCategorySelect(cat)}
              className="px-2.5 py-1 rounded text-xs capitalize transition-colors font-medium"
              style={{
                background: localCategory === cat ? 'var(--color-accent)' : 'transparent',
                color: localCategory === cat ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              {cat.replace('_', ' ')}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => onAddSource && onAddSource(null)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium text-xs shadow-xs"
          style={{
            background: 'var(--color-accent)',
            color: '#fff',
          }}
        >
          <Upload size={13} />
          <span>Add Source</span>
        </button>
      </div>

      {/* ── Ingested Documents List ─────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-2">
        {filtered.map((doc) => (
          <div
            key={doc.id}
            onClick={() => onSourceSelect && onSourceSelect(doc.id)}
            className="p-3.5 rounded-xl border flex items-center justify-between gap-4 transition-colors cursor-pointer hover:shadow-xs"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-card-border)',
            }}
          >
            <div className="flex items-center gap-3 min-w-0">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-surface)',
                  color: 'var(--color-accent)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <FileText size={16} />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
                  {doc.name}
                </p>
                <p className="text-[11px] font-mono mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                  {doc.size} · Ingested {doc.date} ·{' '}
                  <span className="capitalize">{doc.category}</span>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleToggle(doc.id)
              }}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium border"
              style={{
                background: doc.inScope ? 'var(--color-overlay)' : 'transparent',
                borderColor: doc.inScope ? 'var(--color-accent-border)' : 'var(--color-border)',
                color: doc.inScope ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
            >
              {doc.inScope ? <CheckCircle2 size={13} /> : <Circle size={13} />}
              <span>{doc.inScope ? 'In Scope' : 'Excluded'}</span>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
