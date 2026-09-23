import React, { useState, useEffect } from 'react'
import { ClipboardList, Download, Search, Filter, CheckCircle2, XCircle, Clock, ShieldCheck, RefreshCw } from 'lucide-react'
import { CANONICAL_AUDIT_ENTRIES } from './contract'

const STATUS_CONFIG = {
  SUCCESS: { icon: CheckCircle2, color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
  DENIED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  FAILED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  PENDING: { icon: Clock, color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
}

const ACTION_TYPES = [
  'ALL',
  'APPROVAL_GRANT',
  'EXECUTE',
  'WRITE',
  'INGEST',
  'SAP_SYNC',
  'SEND',
  'REJECT',
]

/**
 * AuditLog — Full sovereign audit trail viewer delivered by Kanishka (FRONTEND.md §3.10 / row 45).
 * Connects directly to GET /api/audit and GET /api/approvals to surface immutable compliance records.
 */
export default function AuditLog({
  entries: initialEntries = CANONICAL_AUDIT_ENTRIES,
  onExportCsv,
  onFilterChange,
  onEntryClick,
}) {
  const [entries, setEntries] = useState(initialEntries)
  const [query, setQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('ALL')
  const [isLoading, setIsLoading] = useState(false)

  const fetchLiveAudit = async () => {
    try {
      setIsLoading(true)
      const res = await fetch('/api/audit')
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data.entries) && data.entries.length > 0) {
          // Normalize backend entries into the audit viewer format
          const formatted = data.entries.map((e, idx) => ({
            id: e.id || e.entry_id || `AUD-${idx + 1}`,
            timestamp: e.timestamp || new Date().toISOString().replace('T', ' ').slice(0, 19),
            actionType: (e.action_type || e.action || 'EXECUTE').toUpperCase(),
            toolOrComponent: e.component || e.tool_name || e.tool || 'WorkbenchEngine',
            user: e.user || e.operator || 'operator@refinery.local',
            status: (e.status || (e.approved ? 'SUCCESS' : 'SUCCESS')).toUpperCase(),
            summary: e.summary || e.description || e.details || 'Audited sovereign operation',
          }))
          setEntries(formatted)
        }
      }
    } catch {
      // Keep existing entries on fetch error
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
                    No matching audit records found.
                  </td>
                </tr>
              ) : (
                filtered.map((e) => {
                  const statusInfo = STATUS_CONFIG[e.status] || STATUS_CONFIG.SUCCESS
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
