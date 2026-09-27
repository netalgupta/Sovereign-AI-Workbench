import React, { useState } from 'react'
import {
  PanelLeftOpen,
  PanelLeftClose,
  Plus,
  FileText,
  Image as ImageIcon,
  Database,
  Sparkles,
  ChevronLeft,
} from 'lucide-react'
import { usePreviewStore } from '../../store/previewStore'
import { useChatStore } from '../../store/chatStore'

/**
 * MinimalistCollapsedSourcesRail
 *
 * Implements the exact ultra-thin, sleek collapsed sources rail requested by the user:
 * 1. Top expand button [|>
 * 2. Add source '+' button
 * 3. File type icon chips (DOCX in blue, PDF in red, Sparkle/key note in blue, Photos/Drawings in coral)
 * 4. Hover tooltips with document name, file size & type
 * 5. 1-click preview on clicking any document icon
 * 6. Total sources count chip at bottom
 */
export function MinimalistCollapsedSourcesRail({
  sources = [],
  onExpand,
  onAddSource,
}) {
  const openPreview = usePreviewStore((s) => s.openPreview)
  const sourcesEnabled = useChatStore((s) => s.sourcesEnabled)
  const toggleSourcesEnabled = useChatStore((s) => s.toggleSourcesEnabled)
  const [hoveredFile, setHoveredFile] = useState(null)
  const [tooltipPos, setTooltipPos] = useState({ top: 0 })

  // Deduplicate or take first 14 key sources to render in the thin rail
  const displaySources = sources.slice(0, 16)

  const handleMouseEnter = (file, e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltipPos({ top: rect.top + rect.height / 2 })
    setHoveredFile(file)
  }

  const handleMouseLeave = () => {
    setHoveredFile(null)
  }

  return (
    <aside
      className="h-full w-10 flex flex-col items-center py-2.5 select-none transition-all relative flex-shrink-0"
      style={{
        background: 'transparent',
      }}
      aria-label="Collapsed sources navigation rail"
    >
      {/* ── 1. Top Expand Button [|> ───────────────────────────────── */}
      <button
        type="button"
        onClick={onExpand}
        className="w-7 h-7 rounded-lg flex items-center justify-center text-[var(--color-text-muted)] hover:text-white hover:bg-[var(--color-accent)] transition-all cursor-pointer group"
        title="Expand Sources panel"
        aria-label="Expand Sources panel"
      >
        <div className="flex items-center justify-center">
          {/* Panel toggle glyph matching image [|> */}
          <PanelLeftOpen size={14} strokeWidth={2.2} className="group-hover:scale-105 transition-transform" />
        </div>
      </button>

      {/* ── 2. Add Source '+' Button ───────────────────────────────── */}
      <button
        type="button"
        onClick={onAddSource}
        className="w-7 h-7 mt-1.5 rounded-lg flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-all cursor-pointer"
        title="Add source folder or file to corpus"
        aria-label="Add source folder or file"
      >
        <Plus size={15} strokeWidth={2.2} />
      </button>

      {/* ── Source Status / Quick Toggle Indicator ─────────────────── */}
      <button
        type="button"
        onClick={toggleSourcesEnabled}
        className="w-7 h-7 mt-1 mb-1 rounded-lg flex items-center justify-center text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] transition-all cursor-pointer group"
        title={
          sourcesEnabled
            ? 'Sources Grounding: ON (click to bypass local sources)'
            : 'Sources Grounding: OFF (click to enable local grounding)'
        }
        aria-label="Toggle sources consideration"
      >
        <span
          className={`w-2 h-2 rounded-full transition-all group-hover:scale-125 ${
            sourcesEnabled ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400/90'
          }`}
        />
      </button>

      {/* ── 3. Vertical Stack of File Type Icons ───────────────────── */}
      <div className="flex-1 w-full flex flex-col items-center gap-2 overflow-y-auto no-scrollbar py-2">
        {displaySources.map((file, idx) => {
          const name = file.name || file.path || `Source ${idx + 1}`
          const ext = (file.type || name.split('.').pop() || '').toUpperCase()

          const isPdf = ext === 'PDF' || name.toLowerCase().endsWith('.pdf')
          const isImage =
            ext === 'PNG' ||
            ext === 'JPG' ||
            ext === 'JPEG' ||
            ext === 'P&ID' ||
            name.toLowerCase().includes('pid') ||
            name.toLowerCase().includes('draw')
          const isData = ext === 'CSV' || ext === 'XLSX' || ext === 'XLS'
          const isKeySparkle = idx === 2 // key extraction / summary star in 3rd position matching user screenshot

          return (
            <div
              key={file.id || file.path || idx}
              onClick={() => openPreview(file)}
              onMouseEnter={(e) => handleMouseEnter(file, e)}
              onMouseLeave={handleMouseLeave}
              className="relative group cursor-pointer"
            >
              {isPdf ? (
                /* PDF Badge in soft red matching user image */
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-[9px] tracking-tight transition-transform group-hover:scale-110 shadow-xs"
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    color: '#f87171',
                    border: '1.5px solid rgba(239, 68, 68, 0.35)',
                  }}
                  title={name}
                >
                  PDF
                </div>
              ) : isKeySparkle ? (
                /* Key Sparkle / Diamond in soft blue */
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110"
                  style={{ color: '#60a5fa' }}
                  title={name}
                >
                  <Sparkles size={16} strokeWidth={2.2} className="fill-[#60a5fa] text-[#60a5fa]" />
                </div>
              ) : isImage ? (
                /* Image / P&ID Drawing in coral red */
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 shadow-xs"
                  style={{
                    background: 'rgba(248, 113, 113, 0.12)',
                    color: '#f87171',
                    border: '1.5px solid rgba(248, 113, 113, 0.35)',
                  }}
                  title={name}
                >
                  <ImageIcon size={14} strokeWidth={2.2} />
                </div>
              ) : isData ? (
                /* Data table / CSV in emerald */
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 shadow-xs"
                  style={{
                    background: 'rgba(52, 211, 153, 0.12)',
                    color: '#34d399',
                    border: '1.5px solid rgba(52, 211, 153, 0.35)',
                  }}
                  title={name}
                >
                  <Database size={13} strokeWidth={2.2} />
                </div>
              ) : (
                /* Standard Document / Word in soft blue matching user image */
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 shadow-xs"
                  style={{
                    background: 'rgba(96, 165, 250, 0.12)',
                    color: '#60a5fa',
                    border: '1.5px solid rgba(96, 165, 250, 0.35)',
                  }}
                  title={name}
                >
                  <FileText size={14} strokeWidth={2.2} />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── 4. Bottom Total Badge ───────────────────────────────────── */}
      <div
        onClick={onExpand}
        className="mt-1 px-1.5 py-0.5 rounded-md text-[9px] font-mono font-bold cursor-pointer hover:text-[var(--color-accent)] transition-colors"
        style={{
          background: 'var(--color-overlay)',
          color: 'var(--color-text-muted)',
        }}
        title={`${sources.length} total sources — Click to expand`}
      >
        {sources.length}
      </div>

      {/* ── Floating Hover Tooltip (Pops to the left of the rail) ──── */}
      {hoveredFile && (
        <div
          className="fixed pointer-events-none z-50 px-2.5 py-1.5 rounded-lg border text-xs shadow-xl transition-opacity animate-in fade-in zoom-in-95 duration-100"
          style={{
            left: '48px',
            top: `${tooltipPos.top}px`,
            transform: 'translateY(-50%)',
            background: 'var(--color-surface)',
            borderColor: 'var(--color-accent-border)',
            color: 'var(--color-text)',
            maxWidth: '280px',
          }}
        >
          <div className="font-medium truncate text-xs text-[var(--color-text)]">
            {hoveredFile.name || hoveredFile.path}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-muted)] font-mono mt-0.5">
            <span>{hoveredFile.type || 'DOCUMENT'}</span>
            {hoveredFile.size && <span>· {hoveredFile.size}</span>}
            <span className="text-[var(--color-accent)]">· Click to preview</span>
          </div>
        </div>
      )}
    </aside>
  )
}
