import React from 'react'
import { Shield, ShieldAlert, ArrowUpRight, Cpu, HardDrive, Wifi, Radio } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { CANONICAL_NETWORK_STATE } from './contract'

/**
 * Placeholder for NetworkMonitor component.
 * Owner: Sahil (FRONTEND.md §3.9 / CARD 07)
 *
 * @param {import('./contract').NetworkMonitorProps} props
 */
export default function Placeholder({
  status = CANONICAL_NETWORK_STATE.status,
  externalCount = CANONICAL_NETWORK_STATE.externalCount,
  connections = CANONICAL_NETWORK_STATE.connections,
  metrics = CANONICAL_NETWORK_STATE.metrics,
  mode = 'bar',
  onViewFullMonitor,
}) {
  const navigate = useNavigate()
  const isSecure = externalCount === 0 && status !== 'external_detected'

  const handleOpenFull = () => {
    if (onViewFullMonitor) {
      onViewFullMonitor()
    } else {
      navigate('/monitor')
    }
  }

  // ── VARIANT 1: Bottom Bar Widget (for ChatPane footer) ─────────────────────
  if (mode === 'bar') {
    return (
      <aside
        aria-label="Network Monitor status bar"
        className="w-full border-t px-4 py-1.5 flex items-center justify-between text-xs font-mono select-none"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }}
      >
        <div className="flex items-center gap-3">
          {/* Status Indicator */}
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                isSecure ? 'bg-emerald-500 animate-pulse' : 'bg-red-500 animate-ping'
              }`}
            />
            <span
              className="font-medium font-sans text-[11px]"
              style={{ color: isSecure ? 'var(--color-text)' : '#ef4444' }}
            >
              {isSecure ? 'Air-Gap Secure' : 'ALERT: External Traffic'}
            </span>
          </div>

          <span className="text-[10px] text-zinc-400 dark:text-zinc-600">|</span>

          {/* External connections count */}
          <div className="flex items-center gap-1 text-[11px]">
            <span style={{ color: isSecure ? 'var(--color-text-muted)' : '#ef4444' }}>
              ● {externalCount} external connections
            </span>
          </div>

          <span className="hidden sm:inline text-[10px] text-zinc-400 dark:text-zinc-600">|</span>

          {/* Integration Handoff Pill */}
          <span
            className="hidden sm:inline text-[10px] font-mono px-1.5 py-0.2 rounded"
            style={{
              background: 'var(--color-overlay)',
              color: 'var(--color-text-muted)',
            }}
          >
            WebSocket feed pending — owned by Sahil
          </span>
        </div>

        {/* Action Link to /monitor */}
        <button
          type="button"
          onClick={handleOpenFull}
          className="flex items-center gap-1 text-[11px] font-sans font-medium hover:underline transition-colors"
          style={{ color: 'var(--color-accent)' }}
        >
          <span>Live Sockets ({connections.length})</span>
          <ArrowUpRight size={12} />
        </button>
      </aside>
    )
  }

  // ── VARIANT 2: Full Monitor Page View (for /monitor route) ─────────────────
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
              background: isSecure ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
              color: isSecure ? '#10b981' : '#ef4444',
            }}
          >
            {isSecure ? <Shield size={18} /> : <ShieldAlert size={18} />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Real-Time Air-Gap &amp; Network Monitor
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                Integration pending — owned by Sahil
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              CARD 07 / FRONTEND.md §3.9 live WebSocket connection surveillance
            </p>
          </div>
        </div>

        {/* Anti-hallucination metric */}
        <div
          className="px-3 py-1.5 rounded-lg border text-xs font-mono"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
          }}
        >
          Time since last external attempt:{' '}
          <strong style={{ color: 'var(--color-success)' }}>N/A (none recorded this session)</strong>
        </div>
      </div>

      {/* ── Live System Resource Metric Cards ───────────────────────────── */}
      <div className="px-6 py-4 grid grid-cols-1 sm:grid-cols-3 gap-4 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <div className="p-3 rounded-xl border flex items-center justify-between" style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}>
          <div className="flex items-center gap-2 text-xs">
            <Cpu size={16} style={{ color: 'var(--color-accent)' }} />
            <span style={{ color: 'var(--color-text)' }}>CPU Load</span>
          </div>
          <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
            {metrics?.cpuPercent || 14}%
          </span>
        </div>

        <div className="p-3 rounded-xl border flex items-center justify-between" style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}>
          <div className="flex items-center gap-2 text-xs">
            <HardDrive size={16} style={{ color: 'var(--color-accent)' }} />
            <span style={{ color: 'var(--color-text)' }}>Memory Footprint</span>
          </div>
          <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
            {metrics?.memoryGb || 3.8} GB
          </span>
        </div>

        <div className="p-3 rounded-xl border flex items-center justify-between" style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}>
          <div className="flex items-center gap-2 text-xs">
            <Wifi size={16} style={{ color: isSecure ? '#10b981' : '#ef4444' }} />
            <span style={{ color: 'var(--color-text)' }}>External Traffic</span>
          </div>
          <span className="font-mono text-xs font-bold text-emerald-500">
            {metrics?.networkRate || '0.0 MB/s'} (0 sockets)
          </span>
        </div>
      </div>

      {/* ── Live Active Sockets Table ────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div
          className="rounded-xl border shadow-xs overflow-hidden"
          style={{
            background: 'var(--color-card-bg)',
            borderColor: 'var(--color-card-border)',
          }}
        >
          <div className="px-4 py-2.5 border-b flex items-center justify-between font-mono text-[11px]" style={{ borderColor: 'var(--color-border)' }}>
            <span className="font-bold uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
              Active Socket Table ({connections.length})
            </span>
            <span className="text-[10px] text-emerald-500 flex items-center gap-1 font-sans">
              <Radio size={11} className="animate-pulse" /> Live local feed
            </span>
          </div>

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
                <th className="py-2.5 px-4 font-semibold">Local Address</th>
                <th className="py-2.5 px-4 font-semibold">Remote Address</th>
                <th className="py-2.5 px-4 font-semibold">Status</th>
                <th className="py-2.5 px-4 font-semibold">Bound Process</th>
                <th className="py-2.5 px-4 font-semibold">Classification</th>
              </tr>
            </thead>
            <tbody className="divide-y font-mono text-[11px]" style={{ borderColor: 'var(--color-border)' }}>
              {connections.map((c) => (
                <tr key={c.id} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                  <td className="py-2.5 px-4" style={{ color: 'var(--color-text)' }}>
                    {c.local_addr}
                  </td>
                  <td className="py-2.5 px-4" style={{ color: 'var(--color-text-muted)' }}>
                    {c.remote_addr}
                  </td>
                  <td className="py-2.5 px-4 font-bold text-emerald-500">{c.status}</td>
                  <td className="py-2.5 px-4 font-semibold" style={{ color: 'var(--color-accent)' }}>
                    {c.process || 'kernel'}
                  </td>
                  <td className="py-2.5 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        c.is_external ? 'bg-red-500/20 text-red-500' : 'bg-emerald-500/10 text-emerald-500'
                      }`}
                    >
                      {c.is_external ? 'EXTERNAL (ALERT)' : 'LOOPBACK / AIR-GAP'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
