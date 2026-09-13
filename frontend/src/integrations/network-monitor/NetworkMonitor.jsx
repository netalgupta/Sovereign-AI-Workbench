import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, ShieldAlert, Cpu, HardDrive, Wifi, WifiOff, ArrowUpRight } from 'lucide-react'

// Poll interval matches the documented backend contract (backend/main.py):
// "The frontend polls /api/network/status about once a second." There is no
// websocket — 1s polling IS the live feed.
const POLL_INTERVAL_MS = 1000

// Backend ConnectionInfo carries both `local_addr`/`remote_addr` (legacy,
// default "") and `local_address`/`remote_address` (the real fields).
function normalizeConn(c = {}) {
  return {
    id: c.id || '',
    local_addr: c.local_addr || c.local_address || '',
    remote_addr: c.remote_addr || c.remote_address || '',
    status: c.status || '',
    is_external: Boolean(c.is_external),
    process: c.process || '—',
    timestamp: c.timestamp || '',
  }
}

function fmtElapsed(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 1) return null
  if (totalSeconds < 60) return `${totalSeconds}s`
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

// Alarm semantics per CARD 07 (see also backend/audit/network_monitor.py):
// the ALARM is driven ONLY by `externalCount`, which is this application's
// process tree. `hostExternalCount` is the whole machine (browser, IDE, OS)
// and is shown as clearly-labelled context — it must never drive the alarm.
const SECURE = '#10b981'
const DANGER = '#ef4444'
const UNKNOWN = '#f59e0b'

/**
 * Real NetworkMonitor — bar (chat footer) and full (/monitor) variants.
 * Self-polls /api/network/status; never fabricates a secure state when the
 * backend is unreachable.
 *
 * @param {import('./contract').NetworkMonitorProps & { hostExternalCount?: number, hostNote?: string }} props
 */
export default function NetworkMonitor({
  connections: propConnections = [],
  metrics: propMetrics,
  mode = 'bar',
  onViewFullMonitor,
}) {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [lastExternalAt, setLastExternalAt] = useState(null)
  const [now, setNow] = useState(0)
  const prevCountRef = useRef(0)

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const res = await fetch('/api/network/status')
        if (!active) return
        if (!res.ok) {
          setError(true)
          return
        }
        const payload = await res.json()
        if (!active) return
        setError(false)
        setData(payload)
        setNow(Date.now())
        const ext = typeof payload.externalCount === 'number' ? payload.externalCount : -1
        if (ext > 0 && prevCountRef.current === 0) setLastExternalAt(Date.now())
        prevCountRef.current = ext
      } catch {
        if (!active) return
        setError(true)
      }
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  const live = Boolean(data) && data.scope === 'application'
  const extApp = live && typeof data.externalCount === 'number' ? data.externalCount : null
  const hostExt = live && typeof data.hostExternalCount === 'number' ? data.hostExternalCount : null
  const hostNote = live ? data.hostNote || '' : ''

  // Order matters: an errored poll means we can no longer attest to the
  // last successful reading, so the stale data is NOT shown as green.
  const security = error
    ? 'unreachable'
    : !live || extApp === null
    ? 'checking'
    : extApp > 0
    ? 'external_detected'
    : 'secure'

  const isSecure = security === 'secure'
  const conns = (error ? [] : data?.connections || propConnections).map(normalizeConn)
  const metrics = error ? null : data?.metrics || propMetrics || null
  const elapsedText =
    lastExternalAt == null || !now ? null : fmtElapsed(Math.floor((now - lastExternalAt) / 1000))

  const handleOpenFull = () => {
    if (onViewFullMonitor) onViewFullMonitor()
    else navigate('/monitor')
  }

  const dotColor = isSecure
    ? SECURE
    : security === 'external_detected'
    ? DANGER
    : UNKNOWN
  const headline =
    security === 'external_detected'
      ? `ALERT: External Traffic — ${extApp} external connection${extApp === 1 ? '' : 's'}`
      : isSecure
      ? 'Air-Gap Secure — 0 external connections'
      : security === 'unreachable'
      ? 'Monitor not connected — backend not running'
      : 'Checking connection…'

  // ── BAR (persistent chat footer) ─────────────────────────────────────────
  if (mode === 'bar') {
    return (
      <aside
        aria-label="Network monitor status bar"
        className="w-full border-t px-4 py-1.5 flex items-center justify-between text-xs font-mono select-none"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              aria-hidden="true"
              className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                isSecure ? 'animate-pulse' : security === 'external_detected' ? 'animate-ping' : ''
              }`}
              style={{ background: dotColor }}
            />
            <span
              className="font-medium font-sans text-[11px] truncate"
              style={{ color: isSecure ? 'var(--color-text)' : dotColor }}
            >
              {headline}
            </span>
          </div>

          {isSecure && hostExt !== null && (
            <span className="hidden lg:inline-flex items-center gap-1 text-[10px]" title={hostNote}>
              <span className="text-zinc-400 dark:text-zinc-600">|</span>
              <span className="text-zinc-500 dark:text-zinc-400">
                host · {hostExt >= 0 ? hostExt : '?'} (other apps on this machine — context only)
              </span>
            </span>
          )}

          {elapsedText && (
            <span className="hidden sm:inline text-[10px] text-zinc-500 dark:text-zinc-400">
              | last external attempt {elapsedText} ago
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleOpenFull}
          className="flex items-center gap-1 text-[11px] font-sans font-medium hover:underline transition-colors cursor-pointer flex-shrink-0"
          style={{ color: 'var(--color-accent)' }}
        >
          <span>{security === 'checking' ? 'Open monitor' : `Live sockets (${conns.length})`}</span>
          <ArrowUpRight size={12} />
        </button>
      </aside>
    )
  }

  // ── FULL (/monitor) ──────────────────────────────────────────────────────
  const statusPillColor = isSecure
    ? SECURE
    : security === 'external_detected'
    ? DANGER
    : UNKNOWN
  const externalConns = conns.filter((c) => c.is_external)

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      <div
        className="px-6 py-4 border-b flex flex-col xl:flex-row xl:items-center justify-between gap-3"
        style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{
              background: `${statusPillColor}1a`,
              color: statusPillColor,
            }}
          >
            {isSecure ? <Shield size={18} /> : security === 'external_detected' ? <ShieldAlert size={18} /> : <WifiOff size={18} />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Network Monitor — Application Egress
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{ background: `${statusPillColor}1a`, color: statusPillColor }}
              >
                {security === 'external_detected'
                  ? `external: ${extApp}`
                  : isSecure
                  ? 'air-gap secure'
                  : security === 'unreachable'
                  ? 'not connected'
                  : 'checking'}
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              This application's process tree only. Live {POLL_INTERVAL_MS}ms polling of{' '}
              <code className="text-[10px]">/api/network/status</code> — red fires only on this
              app's own external connections, never on the host figure.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <div
            className="px-3 py-1.5 rounded-lg border"
            style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
          >
            Time since last external attempt:{' '}
            <strong style={{ color: isSecure ? SECURE : DANGER }}>
              {elapsedText ? `${elapsedText} ago` : 'N/A — none recorded this session'}
            </strong>
          </div>
          {hostExt !== null && (
            <div
              className="px-3 py-1.5 rounded-lg border bg-amber-500/5 border-amber-500/20 text-[10px] max-w-[260px]"
              title={hostNote}
            >
              <strong className="block text-[10px] uppercase tracking-wide">Host context (informational)</strong>
              <span style={{ color: 'var(--color-text-muted)' }}>
                {hostExt >= 0 ? `${hostExt} external connection${hostExt === 1 ? '' : 's'}` : 'count unknown'} belonging to
                other apps on this machine — never drives this alarm.
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-6 max-w-6xl w-full mx-auto">
        {security === 'external_detected' && (
          <div
            className="rounded-xl border px-4 py-3 flex items-start gap-2.5 text-xs"
            style={{
              background: `${DANGER}12`,
              borderColor: `${DANGER}45`,
              color: 'var(--color-text)',
            }}
          >
            <ShieldAlert size={16} className="flex-shrink-0 mt-0.5" style={{ color: DANGER }} />
            <div>
              <strong style={{ color: DANGER }}>
                External egress detected from this application: {extApp} connection
                {extApp === 1 ? '' : 's'}.
              </strong>
              <div className="mt-1" style={{ color: 'var(--color-text-muted)' }}>
                {externalConns.map((c) => (
                  <div key={c.id || `${c.remote_addr}-${c.timestamp}`} className="font-mono">
                    {c.remote_addr} — {c.process}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {security === 'unreachable' && (
          <div
            className="rounded-xl border px-4 py-3 text-xs"
            style={{ background: `${UNKNOWN}10`, borderColor: `${UNKNOWN}40`, color: 'var(--color-text)' }}
          >
            <strong style={{ color: UNKNOWN }}>Monitor is not connected.</strong>{' '}
            <span style={{ color: 'var(--color-text-muted)' }}>
              /api/network/status is unreachable, so no secure/all-clear claim is being shown. Start
              the backend to restore live monitoring.
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
                  {metrics && typeof metrics.cpuPercent === 'number' ? `${metrics.cpuPercent}%` : '—'}
                </span>
              </div>
            </div>
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
                  {metrics && typeof metrics.memoryGb === 'number' ? `${metrics.memoryGb} GB` : '—'}
                </span>
              </div>
            </div>
          </div>

          <div
            className="p-4 rounded-xl border flex items-center justify-between shadow-xs"
            style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
          >
            <div className="flex items-center gap-2.5 text-xs">
              <div className="p-2 rounded-lg" style={{ background: 'var(--color-surface)', color: isSecure ? 'var(--color-text-muted)' : DANGER }}>
                <Wifi size={16} />
              </div>
              <div>
                <span className="block text-[11px]" style={{ color: 'var(--color-text-muted)' }}>External Sockets</span>
                <span className="font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                  {extApp === null ? '—' : `${extApp} ext`}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div
          className="rounded-xl border shadow-xs overflow-hidden"
          style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
        >
          <div
            className="px-4 py-3 border-b flex items-center justify-between font-mono text-[11px]"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center gap-2">
              <span className="font-bold uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
                Socket Surveillance Table
              </span>
              <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                {security === 'checking' ? 'awaiting first poll…' : `${conns.length} socket${conns.length === 1 ? '' : 's'}`}
              </span>
            </div>
          </div>

          {conns.length === 0 ? (
            <div
              className="px-4 py-10 text-center text-xs"
              style={{ color: 'var(--color-text-muted)' }}
            >
              {security === 'checking'
                ? 'Waiting for the first /api/network/status response.'
                : security === 'unreachable'
                ? 'Monitor disconnected — no socket data available.'
                : 'No open sockets in this application’s process tree right now.'}
            </div>
          ) : (
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
                  {conns.map((c) => (
                    <tr key={c.id || `${c.remote_addr}-${c.timestamp}`} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                      <td className="py-2.5 px-4" style={{ color: 'var(--color-text)' }}>{c.local_addr}</td>
                      <td className="py-2.5 px-4" style={{ color: 'var(--color-text-muted)' }}>{c.remote_addr}</td>
                      <td className="py-2.5 px-4 font-semibold text-zinc-500 dark:text-zinc-400">{c.status}</td>
                      <td className="py-2.5 px-4 font-medium" style={{ color: 'var(--color-accent)' }}>{c.process}</td>
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}