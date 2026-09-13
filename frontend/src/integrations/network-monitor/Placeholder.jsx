import React from 'react'
import { Shield, ShieldAlert, ShieldX, ArrowUpRight, Cpu, HardDrive, Wifi, Radio } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

/**
 * NetworkMonitor / Placeholder component.
 * Owner: Sahil (FRONTEND.md §3.9 / CARD 07)
 *
 * Provides persistent zero-egress hardware telemetry.
 * If backend telemetry is unreachable or encounters a socket read/permission error,
 * it strictly surfaces a grey/muted "Status unavailable" state — NEVER a fake "Air-Gap Secure" state.
 *
 * @param {import('./contract').NetworkMonitorProps} props
 */
export default function Placeholder({
  mode = 'bar',
  onViewFullMonitor,
}) {
  const navigate = useNavigate()
  const [liveData, setLiveData] = React.useState(null)
  const [fetchFailed, setFetchFailed] = React.useState(false)

  React.useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const res = await fetch('/api/network/status')
        if (res.ok && active) {
          const data = await res.json()
          setLiveData(data)
          setFetchFailed(false)
        } else if (active) {
          setFetchFailed(true)
        }
      } catch {
        if (active) setFetchFailed(true)
      }
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  // Telemetry is ONLY valid if backend actively answered without an error status
  const isAvailable = Boolean(
    liveData &&
    !fetchFailed &&
    liveData.status !== 'error' &&
    liveData.status !== 'unknown'
  )

  const isSecure = isAvailable && liveData.is_air_gapped && (liveData.externalCount === 0)
  const isAlert = isAvailable && (!liveData.is_air_gapped || liveData.externalCount > 0)

  const effExternalCount = isAvailable ? (liveData.externalCount ?? 0) : null
  const effConnections = isAvailable && Array.isArray(liveData.connections) ? liveData.connections : []
  const effMetrics = isAvailable ? liveData.metrics : null

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
        className="w-full border-t px-8 py-2.5 flex items-center justify-between text-xs font-mono select-none transition-colors"
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
                !isAvailable
                  ? 'bg-zinc-400 dark:bg-zinc-600'
                  : isSecure
                  ? 'bg-emerald-500 animate-pulse'
                  : 'bg-red-500 animate-ping'
              }`}
            />
            <span
              className="font-medium font-sans text-[11px]"
              style={{
                color: !isAvailable
                  ? 'var(--color-text-muted)'
                  : isSecure
                  ? 'var(--color-text)'
                  : '#ef4444',
              }}
            >
              {!isAvailable
                ? 'Status unavailable'
                : isSecure
                ? 'Air-Gap Secure'
                : 'ALERT: External Traffic'}
            </span>
          </div>

          <span className="text-[10px] text-zinc-400 dark:text-zinc-600">|</span>

          {/* External connections count */}
          <div className="flex items-center gap-1 text-[11px]">
            <span
              style={{
                color: !isAvailable
                  ? 'var(--color-text-faint)'
                  : isSecure
                  ? 'var(--color-text-muted)'
                  : '#ef4444',
              }}
            >
              {!isAvailable ? '● Telemetry offline' : `● ${effExternalCount} external connections`}
            </span>
          </div>

          <span className="hidden sm:inline text-[10px] text-zinc-400 dark:text-zinc-600">|</span>

          {/* Integration Status Pill */}
          <span
            className="hidden sm:inline text-[10px] font-mono"
            style={{
              color: isAvailable ? 'var(--color-success)' : 'var(--color-text-faint)',
            }}
          >
            {isAvailable ? 'Live Backend Zero-Egress Stream' : 'Backend Disconnected'}
          </span>
        </div>

        {/* Action Link to /monitor */}
        <button
          type="button"
          onClick={handleOpenFull}
          className="flex items-center gap-1 text-[11px] font-sans font-medium hover:underline transition-colors cursor-pointer"
          style={{ color: isAvailable ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
        >
          <span>Live Sockets ({isAvailable ? effConnections.length : '—'})</span>
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
      {/* ── Top Header ─────────────────────── */}
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
              background: !isAvailable
                ? 'rgba(140, 140, 150, 0.1)'
                : isSecure
                ? 'rgba(16, 185, 129, 0.1)'
                : 'rgba(239, 68, 68, 0.1)',
              color: !isAvailable ? 'var(--color-text-muted)' : isSecure ? '#10b981' : '#ef4444',
            }}
          >
            {!isAvailable ? <ShieldX size={18} /> : isSecure ? <Shield size={18} /> : <ShieldAlert size={18} />}
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
                  color: isAvailable ? 'var(--color-success)' : 'var(--color-text-muted)',
                }}
              >
                {isAvailable ? 'Live Hardware Poller Active' : 'Telemetry Offline'}
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              CARD 07 / FRONTEND.md §3.9 process-scoped zero-egress surveillance
            </p>
          </div>
        </div>

        {/* Status explanation */}
        <div
          className="px-3 py-1.5 rounded-lg border text-xs font-mono"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
          }}
        >
          Telemetry State:{' '}
          <strong
            style={{
              color: !isAvailable
                ? 'var(--color-text-muted)'
                : isSecure
                ? 'var(--color-success)'
                : '#ef4444',
            }}
          >
            {!isAvailable
              ? 'Unavailable (Offline / Unreachable)'
              : isSecure
              ? 'Zero External Sockets Verified'
              : `${effExternalCount} External Sockets Detected`}
          </strong>
        </div>
      </div>

      {/* ── Scrollable Body Content ───────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-6 max-w-6xl w-full mx-auto">
        {/* ── Live System Resource Metric Cards ─── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 opacity-90">
          <div
            className="p-4 rounded-xl border flex items-center justify-between shadow-xs"
            style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
          >
            <div className="flex items-center gap-2.5 text-xs">
              <div className="p-2 rounded-lg" style={{ background: 'var(--color-surface)', color: 'var(--color-accent)' }}>
                <Cpu size={16} />
              </div>
              <div>
                <span className="block text-[11px]" style={{ color: 'var(--color-text-muted)' }}>CPU Utilization</span>
                <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                  {isAvailable && effMetrics?.cpuPercent != null ? `${effMetrics.cpuPercent}%` : '—'}
                </span>
              </div>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--color-overlay)', color: isAvailable ? 'var(--color-success)' : 'var(--color-text-muted)' }}>
              {isAvailable ? 'live' : 'offline'}
            </span>
          </div>

          <div
            className="p-4 rounded-xl border flex items-center justify-between shadow-xs"
            style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
          >
            <div className="flex items-center gap-2.5 text-xs">
              <div className="p-2 rounded-lg" style={{ background: 'var(--color-surface)', color: 'var(--color-accent)' }}>
                <HardDrive size={16} />
              </div>
              <div>
                <span className="block text-[11px]" style={{ color: 'var(--color-text-muted)' }}>Memory Footprint</span>
                <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                  {isAvailable && effMetrics?.memoryGb != null ? `${effMetrics.memoryGb} GB` : '—'}
                </span>
              </div>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--color-overlay)', color: isAvailable ? 'var(--color-success)' : 'var(--color-text-muted)' }}>
              {isAvailable ? 'live' : 'offline'}
            </span>
          </div>

          <div
            className="p-4 rounded-xl border flex items-center justify-between shadow-xs"
            style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
          >
            <div className="flex items-center gap-2.5 text-xs">
              <div
                className="p-2 rounded-lg"
                style={{
                  background: 'var(--color-surface)',
                  color: !isAvailable ? 'var(--color-text-muted)' : isSecure ? 'var(--color-text-muted)' : '#ef4444',
                }}
              >
                <Wifi size={16} />
              </div>
              <div>
                <span className="block text-[11px]" style={{ color: 'var(--color-text-muted)' }}>External Sockets</span>
                <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                  {!isAvailable ? 'Unavailable' : `${effExternalCount} external`}
                </span>
              </div>
            </div>
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                !isAvailable
                  ? 'text-zinc-400 bg-zinc-500/10'
                  : isSecure
                  ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                  : 'text-red-500 bg-red-500/10'
              }`}
            >
              {!isAvailable ? 'offline' : isSecure ? 'air-gap safe' : 'egress alert'}
            </span>
          </div>
        </div>

        {/* ── Socket Table Container ──── */}
        <div
          className="rounded-xl border shadow-xs overflow-hidden"
          style={{
            background: 'var(--color-card-bg)',
            borderColor: 'var(--color-card-border)',
          }}
        >
          <div
            className="px-4 py-3 border-b flex items-center justify-between font-mono text-[11px]"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-surface)',
            }}
          >
            <div className="flex items-center gap-2">
              <span className="font-bold uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
                Active Socket Table (Application Process Tree)
              </span>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                  isAvailable
                    ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
                    : 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20'
                }`}
              >
                {isAvailable ? 'Live Data' : 'Unavailable'}
              </span>
            </div>

            <span className="text-[10px] text-zinc-400 dark:text-zinc-500 flex items-center gap-1.5 font-mono">
              <Radio size={12} className={isAvailable ? 'text-emerald-500 animate-pulse' : 'opacity-60'} />
              <span>{isAvailable ? 'Streaming from /api/network/status' : 'No connection to backend'}</span>
            </span>
          </div>

          <div className="overflow-x-auto">
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
                  <th className="py-2.5 px-4 font-semibold">Socket Status</th>
                  <th className="py-2.5 px-4 font-semibold">Bound Process</th>
                  <th className="py-2.5 px-4 font-semibold">Classification</th>
                </tr>
              </thead>
              <tbody className="divide-y font-mono text-[11px]" style={{ borderColor: 'var(--color-border)' }}>
                {!isAvailable || effConnections.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-zinc-400 dark:text-zinc-500 font-mono">
                      {!isAvailable
                        ? 'Status unavailable — cannot read active sockets from the backend.'
                        : 'No active sockets in application process tree.'}
                    </td>
                  </tr>
                ) : (
                  effConnections.map((c) => (
                    <tr
                      key={c.id}
                      className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                    >
                      <td className="py-2.5 px-4" style={{ color: 'var(--color-text)' }}>
                        {c.local_addr || c.local_address}
                      </td>
                      <td className="py-2.5 px-4" style={{ color: 'var(--color-text-muted)' }}>
                        {c.remote_addr || c.remote_address || '—'}
                      </td>
                      <td className="py-2.5 px-4 font-semibold text-zinc-500 dark:text-zinc-400">
                        {c.status}
                      </td>
                      <td className="py-2.5 px-4 font-medium" style={{ color: 'var(--color-accent)' }}>
                        {c.process || 'python'}
                      </td>
                      <td className="py-2.5 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            c.is_external
                              ? 'bg-red-500/10 text-red-400 border-red-500/20'
                              : 'bg-zinc-500/10 text-zinc-500 dark:text-zinc-400 border-zinc-500/20'
                          }`}
                        >
                          {c.is_external ? 'EXTERNAL' : 'LOOPBACK / LOCAL'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
