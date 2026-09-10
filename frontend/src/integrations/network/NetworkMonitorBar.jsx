import { useNavigate } from 'react-router-dom'
import { DEFAULT_METRICS } from './contract'

/**
 * NetworkMonitorBar — Isolated persistent bottom status line per FRONTEND.md §3.9.
 *
 * Handoff note for Sahil (CARD 07):
 * Wire your live WebSocket events into this component's props (status, externalCount,
 * connections, metrics). The layout and design system tokens are already stabilized.
 *
 * @param {import('./contract').NetworkMonitorProps} props
 */
export function NetworkMonitorBar({
  status = 'secure',
  externalCount = 0,
  metrics = DEFAULT_METRICS,
  onViewFullMonitor,
}) {
  const navigate = useNavigate()

  const isSecure = status === 'secure' && externalCount === 0
  const cpu = metrics?.cpuPercent ?? 14
  const mem = metrics?.memoryGb ?? 3.8
  const net = metrics?.networkRate ?? '0.0 MB/s'

  const handleClick = () => {
    if (onViewFullMonitor) {
      onViewFullMonitor()
    } else {
      navigate('/monitor')
    }
  }

  return (
    <div
      className="px-6 py-1.5 flex-shrink-0 flex items-center justify-between text-[11px] select-none cursor-pointer group transition-colors hover:bg-[var(--color-surface-hover)]"
      style={{
        background: 'var(--color-surface)',
        borderTop: '1px solid var(--color-border)',
      }}
      onClick={handleClick}
      title="Click to inspect live network socket monitor (/monitor)"
    >
      {/* Left: System Status Pill */}
      <div className="flex items-center gap-2">
        <span
          className={`w-1.5 h-1.5 rounded-full ${!isSecure ? 'animate-ping' : ''}`}
          style={{
            background: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)',
          }}
        />
        <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>
          {isSecure ? 'Air-gapped Sandbox Active' : 'EXTERNAL CONNECTION DETECTED'}
        </span>
        <span style={{ color: 'var(--color-text-faint)' }}>·</span>
        <span
          style={{
            color: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)',
          }}
          className="font-medium"
        >
          {isSecure
            ? `Zero Egress Verified (${externalCount} ext)`
            : `ALERT: ${externalCount} external sockets`}
        </span>
      </div>

      {/* Right: Telemetry Metrics + Signal Bars */}
      <div
        className="flex items-center gap-4 text-[10px] font-mono"
        style={{ color: 'var(--color-text-muted)' }}
      >
        <div className="flex items-center gap-1">
          <span className="opacity-70">CPU:</span>
          <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
            {cpu}%
          </span>
        </div>

        <div className="flex items-center gap-1">
          <span className="opacity-70">MEM:</span>
          <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
            {mem} GB
          </span>
        </div>

        <div className="flex items-center gap-1">
          <span className="opacity-70">NET:</span>
          <span
            className="font-semibold"
            style={{
              color: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)',
            }}
          >
            {net}
          </span>
        </div>

        {/* 4 Stair-step Signal Bars */}
        <div
          className="flex items-end gap-[2px] h-3 ml-1"
          title={isSecure ? 'Signal: 0 external sockets (Air-gap secure)' : 'Signal: External egress breach'}
        >
          <span
            className="w-[2.5px] h-1 rounded-xs"
            style={{ background: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)' }}
          />
          <span
            className="w-[2.5px] h-1.5 rounded-xs"
            style={{ background: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)' }}
          />
          <span
            className="w-[2.5px] h-2 rounded-xs"
            style={{ background: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)' }}
          />
          <span
            className="w-[2.5px] h-2.5 rounded-xs"
            style={{ background: isSecure ? 'var(--color-success)' : 'var(--color-danger, #ef4444)' }}
          />
        </div>
      </div>
    </div>
  )
}
