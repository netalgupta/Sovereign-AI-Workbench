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
