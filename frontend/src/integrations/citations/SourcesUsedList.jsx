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
import { ChevronRight, FileText, ExternalLink, FileCode, FileSpreadsheet } from 'lucide-react'

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
  const docName = citation.doc || citation.source_document || citation.document_name || 'Document'
  const sectionName = citation.section || (citation.page_number ? `p. ${citation.page_number}` : '')
  const passageText = citation.passage || citation.text || citation.excerpt || ''

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
        <DocIcon filename={docName} />

        {/* WHICH MARKERS POINT HERE. Rows are grouped by location, so a
            reader tracing [3] in the answer needs to see which row it
            belongs to — otherwise grouping trades one confusion for
            another. */}
        {citation.markers?.length > 0 && (
          <span
            className="text-[9px] font-mono leading-none px-1 py-0.5 rounded"
            style={{
              color: 'var(--color-text-faint)',
              background: 'var(--color-overlay)',
            }}
          >
            {citation.markers.map((m) => `[${m}]`).join('')}
          </span>
        )}

        <span
          className="font-medium text-xs leading-tight"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {docName}
        </span>

        {sectionName && (
          <>
            <span style={{ color: 'var(--color-text-faint)' }}>·</span>
            <span
              className="text-[10px] leading-tight"
              style={{ color: 'var(--color-text-faint)' }}
            >
              {sectionName}
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
              {passageText}
            </div>

            {/* Footer link */}
            <div
              className="flex justify-end px-2.5 py-1"
              style={{ borderTop: '1px solid var(--color-border)' }}
            >
              <Link
                to="/sources"
                className="inline-flex items-center gap-1 text-[10px] font-medium transition-fast"
                style={{ color: 'var(--color-accent)', textDecoration: 'none' }}
                onClick={(e) => e.stopPropagation()}
              >
                View full source
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

  // ONE ROW PER PLACE, NOT PER PASSAGE.
  //
  // Neighbour expansion deliberately returns the chunks either side of a
  // hit, so a single procedure commonly arrives as two or three
  // passages from the same document and page. Rendered one row each,
  // that reads as three sources agreeing -- measured on the real
  // corpus: "CCR1 regeneration cycle inspection findings" returns 6
  // passages from 5 distinct locations, and the panel said 6.
  //
  // Overstating how many independent sources support an answer is a
  // grounding defect, not a cosmetic one: the count is the thing a
  // reader uses to judge how well-evidenced a claim is.
  //
  // The MARKERS are untouched. The answer cites [1]..[6] and those must
  // keep resolving; each row lists which markers point at it.
  const grouped = []
  const byPlace = new Map()
  for (const citation of citations) {
    const doc = citation.doc || citation.source_document || 'Document'
    const place = citation.section || (citation.page_number ? `p. ${citation.page_number}` : '')
    const key = `${doc}::${place}`
    const existing = byPlace.get(key)
    if (existing) {
      existing.markers.push(citation.id)
      // Keep the longest passage: it is the most informative preview of
      // what was actually read at this location.
      if ((citation.passage || '').length > (existing.passage || '').length) {
        existing.passage = citation.passage
      }
    } else {
      const row = { ...citation, doc, section: place, markers: [citation.id] }
      byPlace.set(key, row)
      grouped.push(row)
    }
  }

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
        {grouped.map((citation) => (
          <SourceRow key={citation.markers.join('-')} citation={citation} />
        ))}
      </div>
    </div>
  )
}
