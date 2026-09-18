/**
 * contract.js — Network Monitor shape contract for the integration boundary.
 *
 * Owner: Sahil (CARD 07 / FRONTEND.md §3.9)
 *
 * Real NetworkMonitor component MUST accept exactly this shape:
 * {
 *   status?: 'secure' | 'external_detected' | 'checking' | 'unreachable',
 *   externalCount?: number,     // THIS APP ONLY. 0 = green dot, >0 = RED immediately
 *   connections?: NetworkConnection[],
 *   metrics?: SystemMetrics,
 *   mode?: 'bar' | 'full' | 'widget', // 'bar' for chat footer, 'full' for /monitor route
 *   onViewFullMonitor?: () => void,
 * }
 *
 * The component self-polls GET /api/network/status at ~1s (the documented
 * live-feed contract — backend/main.py), so `status`, `externalCount`,
 * `connections` and `metrics` are optional initial overrides and are never
 * hardcoded in the UI.
 *
 * Anti-hallucination note from CARD 07 + backend/audit/network_monitor.py:
 * This must NEVER be a static/hardcoded display, and never a green
 * "air-gap secure" claim when the backend is unreachable. It is wired to
 * the live /api/network/status feed.
 *
 * ALARM SEMANTICS: the response carries BOTH `externalCount` (this
 * application's process tree — the alarm input) and `hostExternalCount`
 * (whole machine, incl. browser/IDE/OS — context only). The UI drives the
 * red alarm SOLELY from `externalCount`; `hostExternalCount` is rendered
 * as clearly-labelled context and must never change the status color.
 * Historical bug this replaces: the UI alarmed on 44 host-wide connections
 * owned by Chrome/Spotify/Teams while the product itself had zero egress.
 *
 * @typedef {Object} NetworkConnection
 * @property {string} id - Unique connection identifier
 * @property {string} remote_addr - Target address (e.g. "127.0.0.1:8000" or external IP)
 * @property {string} local_addr - Source socket address
 * @property {string} status - Socket state (e.g. "ESTABLISHED", "LISTEN", "CLOSE_WAIT")
 * @property {boolean} is_external - True if non-RFC1918 or outside loopback/LAN
 * @property {string} [process] - Associated process name (e.g. "python", "ollama")
 * @property {string} [timestamp] - ISO timestamp or formatted time string
 *
 * @typedef {Object} SystemMetrics
 * @property {number} cpuPercent - CPU utilization percentage (0-100)
 * @property {number} memoryGb - Memory consumption in Gigabytes
 * @property {string} networkRate - Current transfer rate string (e.g. "0.0 MB/s")
 *
 * @typedef {Object} NetworkMonitorProps
 * @property {'secure' | 'external_detected' | 'checking' | 'unreachable'} [status='checking'] - Air-gap security status
 * @property {number} [externalCount] - External connections, THIS APP ONLY (0 = green, >0 = red)
 * @property {NetworkConnection[]} [connections=[]] - Active socket list
 * @property {SystemMetrics} [metrics] - Real-time system resource metrics
 * @property {'bar' | 'full' | 'widget'} [mode='bar'] - Display mode
 * @property {() => void} [onViewFullMonitor] - Handler to navigate to full /monitor route
 * @property {number} [hostExternalCount] - Machine-wide external count (context only, never an alarm input)
 * @property {string} [hostNote] - Clarifying label for the host figure
 */

/**
 * Lightweight runtime validation for NetworkMonitor props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true
  if (props.externalCount !== undefined && typeof props.externalCount !== 'number') {
    console.warn('[Integration: network-monitor] Contract violation: `externalCount` must be a number.', props)
    return false
  }
  if (props.connections && !Array.isArray(props.connections)) {
    console.warn('[Integration: network-monitor] Contract violation: `connections` must be an Array.', props)
    return false
  }
  return true
}