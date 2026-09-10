/**
 * contract.js — Citation shape contract for the integration boundary.
 *
 * This file is the single source of truth for the Citation data shape.
 * Both the API layer (api.js) and the UI layer (CitationChip.jsx) reference
 * this shape definition.
 *
 * When Aditya's real backend returns citations, the API response must conform
 * to this shape. No other file needs to change.
 *
 * When Netal's real Citation UI lands, she imports this contract to validate
 * her component props against it.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * Citation shape:
 * {
 *   id:      number,  — 1-indexed, matches the [N] chip in the message text
 *   doc:     string,  — human-readable document name (e.g. "HCU_Operations_Manual.pdf")
 *   section: string,  — page/section label (e.g. "Section 4.2 — Feed Rate Limits")
 *   passage: string,  — the exact retrieved text passage shown in the expansion card
 * }
 * ─────────────────────────────────────────────────────────────────────────────
 */

/**
 * Validate that a citation object conforms to the contract.
 * Returns true if valid, false otherwise. Used in dev/debug only.
 *
 * @param {unknown} citation
 * @returns {boolean}
 */
export function isValidCitation(citation) {
  return (
    citation !== null &&
    typeof citation === 'object' &&
    typeof citation.id === 'number' &&
    typeof citation.doc === 'string' &&
    typeof citation.section === 'string' &&
    typeof citation.passage === 'string'
  )
}

/**
 * The canonical empty citation — used as a default prop fallback.
 * @type {{ id: number, doc: string, section: string, passage: string }}
 */
export const EMPTY_CITATION = {
  id: 0,
  doc: '',
  section: '',
  passage: '',
}
