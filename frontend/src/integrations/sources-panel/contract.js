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
    id: 'sop-114-rev3',
    name: 'SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx',
    type: 'docx',
    size: '37.7 KB',
    date: '2026-09-10',
    category: 'sops',
    inScope: true,
    status: 'indexed',
    tags: ['hcu-2', 'catalyst', 'wabt-limits', 'beds-1-3'],
  },
  {
    id: 'safety-benzene',
    name: 'Aromatic_Complex_Benzene_Safety_Circular.docx',
    type: 'docx',
    size: '37.0 KB',
    date: '2026-09-10',
    category: 'sops',
    inScope: true,
    status: 'indexed',
    tags: ['aromatic-complex', 'benzene-1ppm', 'twa-limit', 'ppe'],
  },
  {
    id: 'insp-ccr1',
    name: 'Inspection_Report_CCR1_Regeneration_Cycle.pdf',
    type: 'pdf',
    size: '38.2 KB',
    date: '2026-09-10',
    category: 'inspection',
    inScope: true,
    status: 'indexed',
    tags: ['ccr-1', 'regeneration-cycle-18', 'd-102-dryer', 'form-f-140-a'],
  },
  {
    id: 'maint-q3',
    name: 'Maintenance_Log_Q3_2026.xlsx',
    type: 'xlsx',
    size: '11.4 KB',
    date: '2026-09-10',
    category: 'inspection',
    inScope: true,
    status: 'indexed',
    tags: ['work-orders', 'downtime', 'r-201', 'k-201', 'q3-2026'],
  },
  {
    id: 'inc-hassan',
    name: 'Pipeline_Incident_Report_Hassan_Segment.pdf',
    type: 'pdf',
    size: '36.3 KB',
    date: '2026-09-10',
    category: 'inspection',
    inScope: true,
    status: 'indexed',
    tags: ['mangalore-hassan', 'pump-p-hs-02', 'flange-leak', 'remediation'],
  },
  {
    id: 'qa-novolen',
    name: 'Novolen_Batch_QA_Report_Aug2026.pdf',
    type: 'pdf',
    size: '42.1 KB',
    date: '2026-09-10',
    category: 'quality',
    inScope: true,
    status: 'indexed',
    tags: ['novolen', 'batch-h110f-0847', 'mfi-spec', 'catalyst-rate'],
  },
  {
    id: 'trend-psa',
    name: 'PSA_Hydrogen_Purity_Trend_Log.xlsx',
    type: 'xlsx',
    size: '11.4 KB',
    date: '2026-09-10',
    category: 'quality',
    inScope: true,
    status: 'indexed',
    tags: ['psa-1', 'psa-2', 'psa-3', 'purity-drift', 'hydrogen'],
  },
  {
    id: 'lab-merox',
    name: 'Sulphur_Spec_Compliance_LabSheet.xlsx',
    type: 'xlsx',
    size: '9.8 KB',
    date: '2026-09-10',
    category: 'quality',
    inScope: true,
    status: 'indexed',
    tags: ['lpg-merox', 'kero-merox', '10ppm-limit', 'exceedance'],
  },
  {
    id: 'sap-materials',
    name: 'SAP_Mock_Materials_Master_Export.xlsx',
    type: 'xlsx',
    size: '11.8 KB',
    date: '2026-09-10',
    category: 'sap_mock',
    inScope: true,
    status: 'indexed',
    tags: ['sap-erp', 'vend-1042', 'materials-master', 'spares'],
  },
  {
    id: 'depot-kasargod',
    name: 'Correspondence_Depot_HQ_Thread_Kasargod.docx',
    type: 'docx',
    size: '36.6 KB',
    date: '2026-09-10',
    category: 'correspondence',
    inScope: true,
    status: 'indexed',
    tags: ['kasargod-depot', 'tank-tk-k-03', 'calibration-variance'],
  },
  {
    id: 'pid-hcu',
    name: 'Hydrocracker_PID_Schematic.png',
    type: 'schematic',
    size: '93.8 KB',
    date: '2026-09-10',
    category: 'diagrams',
    inScope: true,
    status: 'indexed',
    tags: ['hcu-2', 'p-and-id', 'v-201-to-v-208', 'reactor-r-201'],
  },
  {
    id: 'map-pipeline',
    name: 'Pipeline_Segment_Map_Mangalore_Hassan.png',
    type: 'schematic',
    size: '59.0 KB',
    date: '2026-09-10',
    category: 'diagrams',
    inScope: true,
    status: 'indexed',
    tags: ['mangalore-hassan', 'pumping-station', 'corridor-map'],
  },
  {
    id: 'ocr-ccr1',
    name: 'Scanned_Inspection_Checklist_CCR1.png',
    type: 'scan',
    size: '1.96 MB',
    date: '2026-09-10',
    category: 'diagrams',
    inScope: true,
    status: 'indexed',
    tags: ['ccr-1', 'form-f-140-a', 'scanned-form', 'ocr-verified'],
  },
]
