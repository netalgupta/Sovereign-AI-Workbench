import React, { useState, useEffect } from 'react'
import { ClipboardList, Download, Search, Filter, CheckCircle2, XCircle, Clock, ShieldCheck, RefreshCw } from 'lucide-react'

const STATUS_CONFIG = {
  SUCCESS: { icon: CheckCircle2, color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
  DENIED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  FAILED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  PENDING: { icon: Clock, color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
  APPROVED: { icon: CheckCircle2, color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
  REJECTED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  RECORDED: { icon: Clock, color: '#6b7280', bg: 'rgba(107, 114, 128, 0.12)' },
}

// The backend's own event types (backend/audit/audit_log.py AuditEvent), and
// the status each one IS. Every record used to be shown as SUCCESS -- a
// refused approval and a failed write included -- because the page read a
// `status` field the log does not have and defaulted it.
const EVENT_STATUS = {
  APPROVAL_REQUESTED: 'PENDING',
  APPROVAL_GRANTED: 'APPROVED',
  APPROVAL_REFUSED: 'REJECTED',
  TOOL_EXECUTED: 'SUCCESS',
  TOOL_FAILED: 'FAILED',
  CALCULATION: 'RECORDED',
  CORRECTION: 'RECORDED',
}

export function toAuditRow(e, idx) {
  const event = String(e.event || '').toUpperCase()
  return {
    id: `${e.request_id || 'entry'}-${idx}`,
    requestId: e.request_id || '',
    timestamp: e.timestamp ? String(e.timestamp).replace('T', ' ').replace(/\+00:00$/, ' UTC') : '',
    actionType: event,
    toolOrComponent: e.details?.tool_name || e.actor || '',
    user: e.actor || '',
    status: EVENT_STATUS[event] || 'RECORDED',
    summary: e.summary || '',
  }
}

const ACTION_TYPES = ['ALL', ...Object.keys(EVENT_STATUS)]

/**
 * AuditLog — Full sovereign audit trail viewer delivered by Kanishka (FRONTEND.md §3.10 / row 45).
 * Connects directly to GET /api/audit and GET /api/approvals to surface immutable compliance records.
 */
export default function AuditLog({
  entries: initialEntries = [],
  onExportCsv,
  onFilterChange,
  onEntryClick,
}) {
  const [entries, setEntries] = useState(initialEntries)
  const [query, setQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('ALL')
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState(null)

  // THE REAL TRAIL OR NOTHING. This defaulted to built-in entries -- an
  // "Operator authorized HCU fresh feed rate increase from 100% to 115%" by a
  // named teammate -- kept them when the backend was empty or unreachable,
  // and filled missing fields with a current time and a made-up operator.
  const fetchLiveAudit = async () => {
    try {
      setIsLoading(true)
      const res = await fetch('/api/audit?limit=1000')
      if (!res.ok) {
        setLoadError(`The backend answered ${res.status} for /api/audit.`)
        setEntries([])
        return
      }
      const data = await res.json()
      const rows = Array.isArray(data.entries) ? data.entries.map(toAuditRow) : []
      rows.reverse() // newest first
      setEntries(rows)
      setLoadError(null)
    } catch (err) {
      setLoadError(`Could not reach the backend (${err?.message || 'network error'}).`)
      setEntries([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchLiveAudit()
  }, [])

  const handleActionChange = (act) => {
    setActionFilter(act)
    if (onFilterChange) onFilterChange({ actionType: act, searchQuery: query })
  }

  const handleQueryChange = (q) => {
    setQuery(q)
    if (onFilterChange) onFilterChange({ actionType: actionFilter, searchQuery: q })
  }

  const handleExport = () => {
    if (onExportCsv) {
      onExportCsv()
      return
    }
    // Standard CSV export
    const headers = 'ID,Timestamp,ActionType,Component,User,Status,Summary\n'
    const rows = filtered
      .map(
        (e) =>
          `"${e.id}","${e.timestamp}","${e.actionType}","${e.toolOrComponent}","${e.user}","${e.status}","${(e.summary || '').replace(/"/g, '""')}"`
      )
      .join('\n')
    const blob = new Blob([headers + rows], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `sovereign_audit_trail_${Date.now()}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const filtered = entries.filter((e) => {
    const matchesAction = actionFilter === 'ALL' || e.actionType === actionFilter
    const searchLower = query.toLowerCase()
    const matchesQuery =
      !query ||
      (e.summary && e.summary.toLowerCase().includes(searchLower)) ||
      (e.toolOrComponent && e.toolOrComponent.toLowerCase().includes(searchLower)) ||
      (e.user && e.user.toLowerCase().includes(searchLower)) ||
      (e.id && e.id.toLowerCase().includes(searchLower))
    return matchesAction && matchesQuery
  })

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden" style={{ background: 'var(--color-bg)' }}>
      {/* ── Top Header Banner ────────────────────────────────────────────── */}
      <div
        className="px-6 py-4 border-b flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        style={{
          background: 'var(--color-card-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{
              background: 'var(--color-accent-tint)',
              color: 'var(--color-accent)',
              border: '1px solid var(--color-border)',
            }}
          >
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Immutable Audit Log &amp; Governance Trail
              </h1>
              <span
                className="px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider uppercase"
                style={{
                  background: 'var(--color-success-tint)',
                  color: 'var(--color-success)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                }}
              >
                NFR-7 COMPLIANT
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Append-only audit trail recording every tool call, document write, and operator authorization (FRONTEND.md §3.10).
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchLiveAudit}
            disabled={isLoading}
            className="p-2 rounded-lg border text-xs font-mono flex items-center gap-1.5 hover:bg-surface-hover transition-colors cursor-pointer"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
            title="Refresh audit log"
          >
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Sync</span>
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            style={{
              background: 'var(--color-accent)',
              color: '#ffffff',
            }}
          >
            <Download size={13} />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* ── Search & Filter Controls ────────────────────────────────────── */}
      <div
        className="px-6 py-3 border-b flex flex-col sm:flex-row items-center justify-between gap-3 text-xs"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="relative w-full sm:w-80">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="text"
            placeholder="Search audit trail..."
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border text-xs font-mono outline-none"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0 font-mono text-[11px]">
          <Filter size={13} className="text-zinc-400 flex-shrink-0 mr-1" />
          {ACTION_TYPES.map((act) => (
            <button
              key={act}
              type="button"
              onClick={() => handleActionChange(act)}
              className="px-2.5 py-1 rounded-md transition-colors flex-shrink-0 uppercase font-medium text-[10px]"
              style={{
                background: actionFilter === act ? 'var(--color-accent)' : 'transparent',
                color: actionFilter === act ? '#ffffff' : 'var(--color-text-muted)',
              }}
            >
              {act}
            </button>
          ))}
        </div>
      </div>

      {/* ── Audit Table ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6">
        <div
          className="rounded-xl overflow-hidden border shadow-xs"
          style={{
            background: 'var(--color-card-bg)',
            borderColor: 'var(--color-border)',
          }}
        >
          <table className="w-full text-left text-xs border-collapse font-sans">
            <thead>
              <tr
                className="text-[11px] uppercase tracking-wider font-semibold border-b font-mono"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                <th className="py-2.5 px-4 w-36">Entry ID</th>
                <th className="py-2.5 px-4 w-44">Timestamp</th>
                <th className="py-2.5 px-4 w-32">Action</th>
                <th className="py-2.5 px-4 w-44">Component</th>
                <th className="py-2.5 px-4 w-48">Operator</th>
                <th className="py-2.5 px-4 w-28 text-center">Status</th>
                <th className="py-2.5 px-4">Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y font-mono" style={{ borderColor: 'var(--color-border)' }}>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-zinc-400 text-xs">
                    {loadError
                      ? `${loadError} Nothing is shown rather than records that may not exist.`
                      : entries.length === 0
                        ? 'The audit log is empty: nothing has been approved, refused, written or calculated yet.'
                        : 'No matching audit records found.'}
                  </td>
                </tr>
              ) : (
                filtered.map((e) => {
                  const statusInfo = STATUS_CONFIG[e.status] || STATUS_CONFIG.RECORDED
                  const StatusIcon = statusInfo.icon

                  return (
                    <tr
                      key={e.id}
                      onClick={() => onEntryClick && onEntryClick(e.id)}
                      className="transition-colors hover:bg-[var(--color-surface-hover)] cursor-pointer"
                    >
                      <td className="py-3 px-4 text-zinc-400 text-[11px] font-semibold">{e.id}</td>
                      <td className="py-3 px-4 text-[11px] text-zinc-500 dark:text-zinc-400">{e.timestamp}</td>
                      <td className="py-3 px-4">
                        <span
                          className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide"
                          style={{
                            background: 'var(--color-overlay)',
                            border: '1px solid var(--color-border)',
                            color: 'var(--color-text)',
                          }}
                        >
                          {e.actionType}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold" style={{ color: 'var(--color-text)' }}>
                        {e.toolOrComponent}
                      </td>
                      <td className="py-3 px-4 text-[11px] text-zinc-500 dark:text-zinc-400 truncate max-w-[180px]">
                        {e.user}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold"
                          style={{ background: statusInfo.bg, color: statusInfo.color }}
                        >
                          <StatusIcon size={11} strokeWidth={2.5} />
                          <span>{e.status}</span>
                        </span>
                      </td>
                      <td className="py-3 px-4 font-sans text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                        {e.summary}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
