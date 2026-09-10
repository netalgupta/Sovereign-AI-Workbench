import React, { useState } from 'react'
import { ClipboardList, Download, Search, Filter, CheckCircle2, XCircle, Clock } from 'lucide-react'
import { CANONICAL_AUDIT_ENTRIES } from './contract'

const STATUS_CONFIG = {
  SUCCESS: { icon: CheckCircle2, color: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' },
  DENIED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)' },
  FAILED: { icon: XCircle, color: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)' },
  PENDING: { icon: Clock, color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)' },
}

/**
 * Placeholder for AuditLog component.
 * Owner: Kanishka (FRONTEND.md §3.10)
 *
 * @param {import('./contract').AuditLogProps} props
 */
export default function Placeholder({
  entries = CANONICAL_AUDIT_ENTRIES,
  onExportCsv,
  onFilterChange,
  onEntryClick,
}) {
  const [query, setQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('ALL')

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
    // Default mock export handler
    const headers = 'ID,Timestamp,ActionType,Component,User,Status,Summary\n'
    const rows = entries
      .map(
        (e) =>
          `"${e.id}","${e.timestamp}","${e.actionType}","${e.toolOrComponent}","${e.user}","${e.status}","${e.summary}"`
      )
      .join('\n')
    const blob = new Blob([headers + rows], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `sovereign_audit_log_${Date.now()}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const filtered = entries.filter((e) => {
    const matchesAction = actionFilter === 'ALL' || e.actionType === actionFilter
    const matchesText =
      e.id.toLowerCase().includes(query.toLowerCase()) ||
      e.summary.toLowerCase().includes(query.toLowerCase()) ||
      e.toolOrComponent.toLowerCase().includes(query.toLowerCase()) ||
      e.user.toLowerCase().includes(query.toLowerCase())
    return matchesAction && matchesText
  })

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Top Header & Integration Handoff Banner ─────────────────────── */}
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
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-accent)',
            }}
          >
            <ClipboardList size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                System &amp; Air-Gap Audit Log
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                Integration pending — owned by Kanishka
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Tamper-evident operational event stream · FRONTEND.md §3.10
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleExport}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-medium text-xs shadow-xs transition-colors hover:shadow-sm"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-accent-border)',
            color: 'var(--color-accent)',
          }}
        >
          <Download size={13} />
          <span>Export CSV</span>
        </button>
      </div>

      {/* ── Filters & Search ────────────────────────────────────────────── */}
      <div
        className="px-6 py-2.5 border-b flex flex-wrap items-center justify-between gap-3 text-xs"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="relative flex-1 max-w-sm">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-muted)' }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search by user, module, or summary..."
            className="w-full pl-8 pr-3 py-1.5 rounded-md border text-xs focus:outline-none focus:ring-1"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        <div className="flex items-center gap-1 overflow-x-auto text-[11px] font-mono">
          <Filter size={12} style={{ color: 'var(--color-text-muted)' }} />
          {['ALL', 'APPROVAL_GRANT', 'EXECUTE', 'WRITE', 'INGEST', 'SAP_SYNC'].map((act) => (
            <button
              key={act}
              type="button"
              onClick={() => handleActionChange(act)}
              className="px-2 py-0.5 rounded transition-colors"
              style={{
                background: actionFilter === act ? 'var(--color-accent)' : 'transparent',
                color: actionFilter === act ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              {act}
            </button>
          ))}
        </div>
      </div>

      {/* ── Audit Table ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div
          className="rounded-xl border shadow-xs overflow-hidden"
          style={{
            background: 'var(--color-card-bg)',
            borderColor: 'var(--color-card-border)',
          }}
        >
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr
                className="border-b font-mono text-[11px] uppercase tracking-wider"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                <th className="py-2.5 px-4 font-semibold">Timestamp</th>
                <th className="py-2.5 px-4 font-semibold">Action</th>
                <th className="py-2.5 px-4 font-semibold">Component</th>
                <th className="py-2.5 px-4 font-semibold">Operator / Agent</th>
                <th className="py-2.5 px-4 font-semibold">Status</th>
                <th className="py-2.5 px-4 font-semibold">Event Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y font-mono text-[11px]" style={{ borderColor: 'var(--color-border)' }}>
              {filtered.map((row) => {
                const conf = STATUS_CONFIG[row.status] || STATUS_CONFIG.SUCCESS
                const Icon = conf.icon
                return (
                  <tr
                    key={row.id}
                    onClick={() => onEntryClick && onEntryClick(row.id)}
                    className="hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer transition-colors"
                  >
                    <td className="py-2.5 px-4 text-[11px] whitespace-nowrap" style={{ color: 'var(--color-text-muted)' }}>
                      {row.timestamp}
                    </td>
                    <td className="py-2.5 px-4 whitespace-nowrap">
                      <span
                        className="px-2 py-0.5 rounded text-[10px] font-bold"
                        style={{
                          background: 'var(--color-overlay)',
                          color: 'var(--color-accent)',
                          border: '1px solid var(--color-border)',
                        }}
                      >
                        {row.actionType}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 font-semibold whitespace-nowrap" style={{ color: 'var(--color-text)' }}>
                      {row.toolOrComponent}
                    </td>
                    <td className="py-2.5 px-4 whitespace-nowrap" style={{ color: 'var(--color-text-muted)' }}>
                      {row.user}
                    </td>
                    <td className="py-2.5 px-4 whitespace-nowrap">
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold"
                        style={{ background: conf.bg, color: conf.color }}
                      >
                        <Icon size={11} />
                        <span>{row.status}</span>
                      </span>
                    </td>
                    <td className="py-2.5 px-4 font-sans text-xs" style={{ color: 'var(--color-text)' }}>
                      {row.summary}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
