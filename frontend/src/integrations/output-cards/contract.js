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

// CANONICAL_OUTPUTS was here: three invented deliverables (an "HCU Runaway
// Mitigation Approval Note" for a 115% feed rate among them) used as the
// default `files` prop. The Outputs page showed them, with working download
// buttons, under a "LIVE OUTPUTS" heading whenever the backend returned
// nothing or could not be reached. Nobody approved those files and they do
// not exist; the page reads the real directory and says when it is empty.
