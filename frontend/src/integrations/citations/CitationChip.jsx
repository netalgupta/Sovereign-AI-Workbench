/**
 * CitationChip.jsx — Inline citation chip with expandable source card.
 *
 * FRONTEND.md §3.2 — critical rendering rules:
 *  1. The chip itself is a <sup> superscript: purely inline, flows with text,
 *     looks like a footnote number. Width = fit-content (just the number + padding).
 *  2. The expansion card is a SEPARATE block-level element rendered via
 *     React Fragment — it appears below the line, pushing content down.
 *     It is NOT wrapped with the <sup> in a single container.
 *  3. The <div> expansion works because MarkdownBody renders its <p> as
 *     a <div> (valid HTML, allows block children). ChatPane static content
 *     also uses <div> wrappers for any paragraph containing CitationChips.
 *
 * Visual: "...potential off-spec products.¹ ² ³" — tiny raised numbers,
 * terracotta when active, muted when not, no visible box in collapsed state.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText, ExternalLink, Eye } from 'lucide-react'
import { usePreviewStore } from '../../store/previewStore'
import { CopyButton } from '../../components/common/CopyButton'

/**
 * @param {{ citation: { id: number, doc: string, section: string, passage: string } }} props
 */
// The cited file, at the cited page, in the Sources viewer. A citation
// carries the document's name; the backend finds it inside the sources.
function openCited(citation) {
  const doc = citation.source_document || citation.doc
  if (!doc) return
  usePreviewStore.getState().openPreview({
    id: doc,
    name: doc,
    filename: doc,
    relativePath: doc,
    page: Number(citation.page_number) || null,
  })
}

export function CitationChip({ citation }) {
  const [isOpen, setIsOpen] = useState(false)

  if (!citation) return null

  return (
    <>
      {/* ── 1. Inline superscript — plain text link, zero visual weight ───────
          No background, no border, no box. Just a raised colored number,
          identical in visual weight to a Wikipedia citation mark.
          Hover: underline only (like any text link).                        */}
      <sup
        style={{
          fontSize: '0.72em',
          lineHeight: 1,
          verticalAlign: 'super',
          // Pull consecutive chips tight together (no inherent spacing)
          letterSpacing: '0',
        }}
      >
        <button
          type="button"
          onClick={() => {
            // A touch on [n] shows the evidence: the file opens in the
            // viewer at the cited page, and the passage expands under the line.
            if (!isOpen) openCited(citation)
            setIsOpen((o) => !o)
          }}
          aria-expanded={isOpen}
          aria-label={`Open citation ${citation.id}: ${citation.doc}${citation.page_number ? `, page ${citation.page_number}` : ''}`}
          title={`${citation.doc}${citation.page_number ? ` — page ${citation.page_number}` : ''} (opens in the viewer)`}
          style={{
            // Reset ALL button defaults
            appearance: 'none',
            WebkitAppearance: 'none',
            background: 'none',
            border: 'none',
            borderRadius: 0,
            padding: 0,
            margin: '0 1px',
            // Text styling only — looks like a footnote superscript
            fontFamily: 'var(--font-ui)',
            fontSize: 'inherit',
            fontWeight: 500,
            lineHeight: 'inherit',
            color: 'var(--color-accent)',
            cursor: 'pointer',
            textDecoration: isOpen ? 'underline' : 'none',
            textUnderlineOffset: '2px',
            outline: 'none',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.textDecoration = 'underline' }}
          onMouseLeave={(e) => { e.currentTarget.style.textDecoration = isOpen ? 'underline' : 'none' }}
        >
          [{citation.id}]
        </button>
      </sup>

      {/* ── 2. Block expansion card ──────────────────────────────────────────
          Rendered via Fragment — sibling to the <sup>, NOT a child of it.
          This is block-level and only appears when isOpen === true.
          It pushes subsequent content down per §3.2.                        */}
      {isOpen && (
        <div
          className="animate-fade-in"
          style={{
            display: 'block',
            margin: '6px 0 6px',
            // Accent left border — the §3.2 signature visual
            borderLeft: '3px solid var(--color-accent)',
            borderRadius: '0 var(--radius-md) var(--radius-md) 0',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderLeftColor: 'var(--color-accent)',
            borderLeftWidth: '3px',
            boxShadow: 'var(--shadow-sm)',
            overflow: 'hidden',
          }}
        >
          {/* Source metadata */}
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
              padding: '8px 10px 6px',
            }}
          >
            <FileText
              size={13}
              strokeWidth={1.8}
              style={{ color: 'var(--color-accent)', flexShrink: 0, marginTop: 1 }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
              <span
                style={{
                  fontWeight: 600,
                  fontSize: '11px',
                  lineHeight: 1.3,
                  color: 'var(--color-text)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {citation.doc}
              </span>
              <span style={{ fontSize: '10px', color: 'var(--color-text-muted)', lineHeight: 1.3 }}>
                {citation.section}
              </span>
            </div>
          </div>

          {/* Divider */}
          <div style={{ height: '1px', background: 'var(--color-border)', margin: '0' }} />

          {/* Retrieved passage — monospace, visually distinct from generated text */}
          <div
            style={{
              padding: '7px 10px',
              fontFamily: 'var(--font-mono)',
              fontSize: '10.5px',
              lineHeight: 1.65,
              color: 'var(--color-text)',
              background: 'var(--color-overlay)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {citation.passage}
          </div>

          {/* Footer: preview & view full source */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '12px',
              padding: '5px 10px',
              borderTop: '1px solid var(--color-border)',
            }}
          >
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                openCited(citation)
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                fontSize: '10px',
                fontWeight: 500,
                color: 'var(--color-accent)',
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
              }}
            >
              <Eye size={10} strokeWidth={2} />
              Preview document
            </button>

            <CopyButton
              text={() =>
                `"${(citation.passage || '').trim()}"\n-- ${citation.source_document || citation.doc}` +
                (citation.page_number ? `, p. ${citation.page_number}` : '')
              }
              label="Copy passage"
              title="Copy the passage with its source"
              size={10}
              style={{ fontSize: '10px', padding: 0 }}
            />

            <Link
              to="/sources"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                fontSize: '10px',
                fontWeight: 500,
                color: 'var(--color-text-muted)',
                opacity: 0.75,
                textDecoration: 'none',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              Sources Hub
              <ExternalLink size={9} strokeWidth={2} />
            </Link>
          </div>
        </div>
      )}
    </>
  )
}
