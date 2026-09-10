/**
 * contract.js — Citation shape contract for the integration boundary.
 *
 * Owner: Netal (CARD 01 / FRONTEND.md §3.2)
 *
 * Real CitationCard component MUST accept exactly this shape:
 * {
 *   citationId: string | number, // 1-indexed identifier matching chip in message text
 *   sourceDocName: string,       // Human-readable doc name (e.g. "HCU_Operations_Manual.pdf")
 *   pageOrSection: string,       // Location (e.g. "Section 4.2 — Feed Rate Limits")
 *   passage: string,             // The exact retrieved text, rendered in monospace/serif
 *   sourceUrl?: string,          // Link back to Sources panel entry
 *   confidence?: number,         // Optional relevance score (0.0 - 1.0)
 * }
 *
 * Rendered inline, pushes content down (not overlay). Do not change this shape
 * without updating MessageBubble / ChatPane's citation-click handler.
 *
 * @typedef {Object} CitationCardProps
 * @property {string|number} citationId - Citation identifier or index
 * @property {string} sourceDocName - Document name
 * @property {string} pageOrSection - Page / section label
 * @property {string} passage - Exact retrieved text
 * @property {string} [sourceUrl] - Sources panel link
 * @property {number} [confidence] - Relevance score
 * @property {() => void} [onViewSource] - Optional click callback to open document in Sources panel
 */

/**
 * Lightweight runtime validation for CitationCard props.
 * Logs a dev-only console.warn if required fields are missing.
 *
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) {
    console.warn('[Integration: citations] Missing props: CitationCard requires props object.')
    return false
  }

  const missing = []
  if (props.citationId === undefined && props.id === undefined) missing.push('citationId')
  if (!props.sourceDocName && !props.doc) missing.push('sourceDocName')
  if (!props.pageOrSection && !props.section) missing.push('pageOrSection')
  if (props.passage === undefined) missing.push('passage')

  if (missing.length > 0) {
    console.warn(
      `[Integration: citations] Contract violation in CitationCard: missing required field(s): ${missing.join(
        ', '
      )}. Required shape: { citationId, sourceDocName, pageOrSection, passage }`,
      props
    )
    return false
  }
  return true
}

export const CANONICAL_CITATION = {
  citationId: '1',
  sourceDocName: 'HCU_Operations_Manual.pdf',
  pageOrSection: 'Section 4.2 — Feed Rate Limits',
  passage: 'Maximum allowable HCU fresh feed rate under current catalyst run length is 112% of design.',
  sourceUrl: '/sources?doc=HCU_Operations_Manual.pdf',
}
