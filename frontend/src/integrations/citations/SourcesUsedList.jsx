/**
 * SourcesUsedList.jsx — "Sources used" section inside the thinking block.
 *
 * Replaces CitationChip inline superscripts entirely.
 *
 * Placement: inside the collapsible thinking block, below the pipeline steps.
 * Each citation row matches the step-row interaction pattern already established
 * (collapsible-grid, same dot + label + chevron rhythm).
 *
 * Integration contract: same Citation shape from contract.js.
 * Same adapter rule: imports only from this folder, Netal slots in here.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, FileText, ExternalLink, FileCode, FileSpreadsheet, Eye } from 'lucide-react'
import { usePreviewStore } from '../../store/previewStore'

// ---------------------------------------------------------------------------
// Derive a file-type icon from the doc extension — mirrors Sources rail icons
// ---------------------------------------------------------------------------
function DocIcon({ filename }) {
  const ext = filename?.split('.').pop()?.toLowerCase()
  const style = { flexShrink: 0 }

  if (ext === 'pdf') {
    return <FileText size={12} strokeWidth={1.8} style={{ ...style, color: 'var(--color-accent)' }} />
  }
  if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') {
    return <FileSpreadsheet size={12} strokeWidth={1.8} style={{ ...style, color: '#2d7a3a' }} />
  }
  if (ext === 'docx' || ext === 'doc') {
    return <FileText size={12} strokeWidth={1.8} style={{ ...style, color: '#1a5db5' }} />
  }
  return <FileCode size={12} strokeWidth={1.8} style={{ ...style, color: 'var(--color-text-muted)' }} />
}

// ---------------------------------------------------------------------------
// Single source row — collapses/expands its passage inline
// ---------------------------------------------------------------------------
function SourceRow({ citation }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="flex flex-col">
      {/* ── Clickable row: icon + filename + section + chevron ─────────── */}
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="inline-flex items-center gap-2 text-left cursor-pointer group py-0.5 text-xs select-none w-fit"
        style={{ background: 'transparent', border: 'none' }}
        aria-expanded={isOpen}
      >
        <DocIcon filename={citation.doc} />

        <span
          className="font-medium text-xs leading-tight"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {citation.doc}
        </span>

        {citation.section && (
          <>
            <span style={{ color: 'var(--color-text-faint)' }}>·</span>
            <span
              className="text-[10px] leading-tight"
              style={{ color: 'var(--color-text-faint)' }}
            >
              {citation.section}
            </span>
          </>
        )}

        <ChevronRight
          size={11}
          strokeWidth={2}
          className="transition-transform duration-200 ml-0.5"
          style={{
            transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
            color: 'var(--color-text-faint)',
          }}
        />
      </button>

      {/* ── Passage expansion — reuses collapsible-grid from index.css ─── */}
      <div className={`collapsible-grid ${isOpen ? 'is-expanded' : ''}`}>
        <div className="collapsible-inner">
          <div
            className="my-1.5 ml-1"
            style={{
              borderLeft: '2px solid var(--color-accent)',
              borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
              overflow: 'hidden',
            }}
          >
            {/* Passage text — monospace, visually distinct */}
            <div
              className="px-2.5 py-2 text-[10.5px] leading-relaxed"
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-text)',
                background: 'var(--color-overlay)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {citation.passage}
            </div>

            {/* Footer links: Preview & Sources Hub */}
            <div
              className="flex justify-end items-center gap-3 px-2.5 py-1"
              style={{ borderTop: '1px solid var(--color-border)' }}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  usePreviewStore.getState().openPreview(citation.doc)
                }}
                className="inline-flex items-center gap-1 text-[10px] font-medium transition-fast cursor-pointer hover:underline"
                style={{ color: 'var(--color-accent)' }}
              >
                <Eye size={10} strokeWidth={2} />
                Preview document
              </button>

              <Link
                to="/sources"
                className="inline-flex items-center gap-1 text-[10px] font-medium transition-fast opacity-70 hover:opacity-100"
                style={{ color: 'var(--color-text-muted)', textDecoration: 'none' }}
                onClick={(e) => e.stopPropagation()}
              >
                Sources Hub
                <ExternalLink size={9} strokeWidth={2} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SourcesUsedList — the full "Sources used" block inside the thinking section
// ---------------------------------------------------------------------------

/**
 * @param {{ citations: Array<{id: number, doc: string, section: string, passage: string}> }} props
 */
export function SourcesUsedList({ citations }) {
  if (!citations || citations.length === 0) return null

  return (
    <div className="flex flex-col" style={{ marginTop: '10px' }}>
      {/* Section header — same muted uppercase label pattern as "REASONING TRACE" */}
      <div
        className="text-[9px] font-semibold uppercase tracking-widest mb-1.5 select-none"
        style={{ color: 'var(--color-text-faint)', letterSpacing: '0.1em' }}
      >
        Sources used
      </div>

      {/* Source rows, each independently collapsible */}
      <div
        className="pl-3.5 flex flex-col gap-1.5"
        style={{ borderLeft: '2px solid var(--color-border)' }}
      >
        {citations.map((citation) => (
          <SourceRow key={citation.id} citation={citation} />
        ))}
      </div>
    </div>
  )
}
