/**
 * contract.js — Output File Card & Library shape contract for the integration boundary.
 *
 * Owner: Kanishka (CARD 04 / FRONTEND.md §3.7)
 *
 * Real OutputCards / OutputFileCard component MUST accept exactly this shape:
 * {
 *   files?: OutputFile[],
 *   onDownload?: (fileId: string) => void,
 *   onPreview?: (fileId: string) => void,
 *   filterType?: string,
 *   onFilterChange?: (type: string) => void,
 *   layout?: 'grid' | 'list' | 'inline',
 * }
 *
 * Each generated card must show:
 * - File type icon (DOCX, XLSX, PPTX, PDF)
 * - Filename
 * - Formatted file size & timestamp
 * - Source citations count as a badge (reinforcing groundedness)
 * - Download button & preview trigger
 *
 * @typedef {Object} OutputFile
 * @property {string} id - Unique file identifier
 * @property {string} filename - Document filename (e.g. "HCU_Runaway_Mitigation_Note.docx")
 * @property {'docx'|'xlsx'|'pptx'|'pdf'} fileType - File extension / format
 * @property {string} fileSize - Human-readable size (e.g. "184 KB")
 * @property {string} generatedAt - Formatted timestamp (YYYY-MM-DD HH:mm)
 * @property {number} citationsCount - Number of grounded citations
 * @property {string} downloadUrl - File download link
 * @property {string} [previewUrl] - Optional preview render URL
 * @property {'ready'|'generating'|'failed'} [status='ready'] - File readiness state
 * @property {string} [summary] - Optional deliverable summary
 *
 * @typedef {Object} OutputCardsProps
 * @property {OutputFile[]} [files] - Array of generated deliverables
 * @property {(fileId: string) => void} [onDownload] - Download callback
 * @property {(fileId: string) => void} [onPreview] - Preview modal callback
 * @property {string} [filterType='all'] - Format filter ('all'|'docx'|'xlsx'|'pptx')
 * @property {(type: string) => void} [onFilterChange] - Format filter callback
 * @property {'grid'|'list'|'inline'} [layout='grid'] - Visual layout mode
 */

/**
 * Lightweight runtime validation for OutputCards props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true
  if (props.files && !Array.isArray(props.files)) {
    console.warn('[Integration: output-cards] Contract violation: `files` must be an Array.', props)
    return false
  }
  if (props.onDownload && typeof props.onDownload !== 'function') {
    console.warn('[Integration: output-cards] Contract violation: `onDownload` must be a function.', props)
    return false
  }
  return true
}

export const CANONICAL_OUTPUTS = [
  {
    id: 'out-01',
    filename: 'HCU_Runaway_Mitigation_Approval_Note.docx',
    fileType: 'docx',
    fileSize: '184 KB',
    generatedAt: '2026-09-10 14:22',
    citationsCount: 4,
    downloadUrl: '#',
    status: 'ready',
    summary: 'Formal executive note detailing risk mitigations for HCU feed rate increase to 115%.',
  },
  {
    id: 'out-02',
    filename: 'Catalyst_Bed_Exotherm_Simulation.xlsx',
    fileType: 'xlsx',
    fileSize: '412 KB',
    generatedAt: '2026-09-10 13:45',
    citationsCount: 3,
    downloadUrl: '#',
    status: 'ready',
    summary: 'Thermocouple delta-T step projections across catalyst beds 1 through 4.',
  },
  {
    id: 'out-03',
    filename: 'Refinery_Operations_Review_Deck.pptx',
    fileType: 'pptx',
    fileSize: '2.1 MB',
    generatedAt: '2026-09-10 11:10',
    citationsCount: 6,
    downloadUrl: '#',
    status: 'ready',
    summary: 'Slide deck for morning operations briefing with unit superintendent.',
  },
]
