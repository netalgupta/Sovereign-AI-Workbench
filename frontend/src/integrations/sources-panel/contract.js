/**
 * contract.js — Sources Panel shape contract for the integration boundary.
 *
 * Owner: Netal (CARD 02 / FRONTEND.md §3.5)
 *
 * Real SourcesPanel component MUST accept exactly this shape:
 * {
 *   sources?: SourceDocument[],
 *   onToggleScope?: (sourceId: string, inScope: boolean) => void,
 *   onAddSource?: (file: File) => void | Promise<void>,
 *   onSourceSelect?: (sourceId: string) => void,
 *   activeCategory?: string,
 *   onCategoryChange?: (category: string) => void,
 * }
 *
 * Grounding Trust Invariant (NFR-4):
 * The persistent verbatim label must be visible:
 * "This session is grounded only in the sources listed here."
 *
 * @typedef {Object} SourceDocument
 * @property {string} id - Unique document identifier (e.g. "sop-hcu-01")
 * @property {string} name - Human-readable document name (e.g. "HCU_Operations_Manual.pdf")
 * @property {'pdf'|'docx'|'scan'|'photo'|'table'|'schematic'} type - Document category icon key
 * @property {string} size - Formatted file size string (e.g. "4.2 MB")
 * @property {string} date - Ingestion or modification date (YYYY-MM-DD)
 * @property {string} category - Classification category ('sop' | 'catalyst' | 'emissions' | 'telemetry' | 'economics' | 'audit')
 * @property {boolean} inScope - Toggle status for current session retrieval inclusion
 * @property {'indexed'|'syncing'|'ready'|'error'} status - Ingestion pipeline state
 * @property {string[]} [tags] - Optional topic keywords
 *
 * @typedef {Object} SourcesPanelProps
 * @property {SourceDocument[]} [sources] - Knowledge base document list
 * @property {(sourceId: string, inScope: boolean) => void} [onToggleScope] - Scope toggle callback
 * @property {(file: File) => void | Promise<void>} [onAddSource] - File upload callback
 * @property {(sourceId: string) => void} [onSourceSelect] - Document click callback
 * @property {string} [activeCategory='all'] - Currently filtered category tab
 * @property {(category: string) => void} [onCategoryChange] - Category tab switch callback
 * @property {'full'|'rail'} [variant='full'] - Full page view vs sidebar rail view
 */

/**
 * Lightweight runtime validation for SourcesPanel props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true // default state uses internal fallbacks
  if (props.sources && !Array.isArray(props.sources)) {
    console.warn('[Integration: sources-panel] Contract violation: `sources` must be an Array.', props)
    return false
  }
  if (props.onToggleScope && typeof props.onToggleScope !== 'function') {
    console.warn('[Integration: sources-panel] Contract violation: `onToggleScope` must be a function.', props)
    return false
  }
  if (props.onAddSource && typeof props.onAddSource !== 'function') {
    console.warn('[Integration: sources-panel] Contract violation: `onAddSource` must be a function.', props)
    return false
  }
  return true
}

export const CANONICAL_SOURCES = [
  {
    id: 'sop-hcu-01',
    name: 'HCU_Operations_Manual.pdf',
    type: 'pdf',
    size: '4.2 MB',
    date: '2026-09-08',
    category: 'sop',
    inScope: true,
    status: 'indexed',
    tags: ['hcu', 'feed-rate', 'limits'],
  },
  {
    id: 'cat-02',
    name: 'Catalyst_Runaway_Mitigation_Guide.pdf',
    type: 'pdf',
    size: '2.8 MB',
    date: '2026-09-09',
    category: 'catalyst',
    inScope: true,
    status: 'indexed',
    tags: ['catalyst', 'exotherm', 'emergency'],
  },
  {
    id: 'env-03',
    name: 'MRPL_Emissions_Compliance_2026.docx',
    type: 'docx',
    size: '1.4 MB',
    date: '2026-09-09',
    category: 'emissions',
    inScope: false,
    status: 'indexed',
    tags: ['flaring', 'so2', 'cpcb'],
  },
]
