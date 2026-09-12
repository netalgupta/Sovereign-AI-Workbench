/**
 * contract.js — Audit Log Viewer shape contract for the integration boundary.
 *
 * Owner: Kanishka (CARD 06 / FRONTEND.md §3.10)
 *
 * Real AuditLog component MUST accept exactly this shape:
 * {
 *   entries?: AuditLogEntry[],
 *   onExportCsv?: () => void,
 *   onFilterChange?: (filters: { actionType?: string, dateRange?: string, searchQuery?: string }) => void,
 *   onEntryClick?: (entryId: string) => void,
 * }
 *
 * Audit Viewer features per §3.10:
 * - Table: timestamp, action type, tool/component involved, user, status
 * - Filter by action type, date range
 * - Export button → downloads CSV
 * - Search bar for free-text filtering across the log
 *
 * @typedef {Object} AuditLogEntry
 * @property {string} id - Unique log entry ID (e.g. "AUD-20260910-001")
 * @property {string} timestamp - Timestamp formatted as YYYY-MM-DD HH:mm:ss
 * @property {'WRITE'|'SEND'|'SAP_SYNC'|'INGEST'|'EXECUTE'|'APPROVAL_GRANT'|'REJECT'} actionType - Action category
 * @property {string} toolOrComponent - System module (e.g. "HumanApprovalGate", "SymPyVerifier", "YOLOv8")
 * @property {string} user - Operator or agent identifier
 * @property {'SUCCESS'|'DENIED'|'PENDING'|'FAILED'} status - Outcome status
 * @property {string} [summary] - Human-readable action description
 * @property {Record<string, any>} [details] - Detailed parameter diff
 *
 * @typedef {Object} AuditLogProps
 * @property {AuditLogEntry[]} [entries] - Audit log records
 * @property {() => void} [onExportCsv] - CSV export callback
 * @property {(filters: { actionType?: string, dateRange?: string, searchQuery?: string }) => void} [onFilterChange] - Filter change handler
 * @property {(entryId: string) => void} [onEntryClick] - Entry inspect callback
 */

/**
 * Lightweight runtime validation for AuditLog props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true
  if (props.entries && !Array.isArray(props.entries)) {
    console.warn('[Integration: audit-log] Contract violation: `entries` must be an Array.', props)
    return false
  }
  if (props.onExportCsv && typeof props.onExportCsv !== 'function') {
    console.warn('[Integration: audit-log] Contract violation: `onExportCsv` must be a function.', props)
    return false
  }
  return true
}

export const CANONICAL_AUDIT_ENTRIES = [
  {
    id: 'AUD-20260910-001',
    timestamp: '2026-09-10 14:22:15',
    actionType: 'APPROVAL_GRANT',
    toolOrComponent: 'HumanApprovalGate',
    user: 'advay.chavan@refinery.local',
    status: 'SUCCESS',
    summary: 'Operator authorized HCU fresh feed rate increase from 100% to 115%.',
  },
  {
    id: 'AUD-20260910-002',
    timestamp: '2026-09-10 14:21:40',
    actionType: 'EXECUTE',
    toolOrComponent: 'SymPyVerifier',
    user: 'reasoning-agent',
    status: 'SUCCESS',
    summary: 'Verified exotherm margin Delta_T <= 143.2°C under peak quench limits.',
  },
  {
    id: 'AUD-20260910-003',
    timestamp: '2026-09-10 13:50:02',
    actionType: 'WRITE',
    toolOrComponent: 'DeliverableCompiler',
    user: 'coder-agent',
    status: 'SUCCESS',
    summary: 'Exported HCU_Runaway_Mitigation_Approval_Note.docx (184 KB).',
  },
  {
    id: 'AUD-20260910-004',
    timestamp: '2026-09-10 12:15:18',
    actionType: 'INGEST',
    toolOrComponent: 'FAISS_VectorStore',
    user: 'system',
    status: 'SUCCESS',
    summary: 'Re-indexed SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx chunk embeddings with SHA-256 integrity seal.',
  },
  {
    id: 'AUD-20260910-005',
    timestamp: '2026-09-10 11:04:33',
    actionType: 'SAP_SYNC',
    toolOrComponent: 'SAP_RFC_Gateway',
    user: 'system',
    status: 'DENIED',
    summary: 'Write access to production DCS tag blocked — air-gapped read-only mode active.',
  },
]
