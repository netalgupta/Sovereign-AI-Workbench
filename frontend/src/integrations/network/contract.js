/**
 * contract.js — Network Monitor shape contract for the CARD 07 integration boundary.
 *
 * This file is the single source of truth for the Network Monitor component props.
 * Owner: Sahil (CARD 07 / FRONTEND.md §3.9)
 *
 * Sahil: When wiring your live WebSocket feed, feed the parsed events directly into
 * this component's props without touching the layout code in ChatPane.jsx.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * Connection Event shape:
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
 * @property {'secure' | 'warning' | 'external_detected' | 'checking'} [status='secure'] - Air-gap security status
 * @property {number} [externalCount=0] - Number of external connections (0 = green, >0 = red)
 * @property {NetworkConnection[]} [connections=[]] - Active socket list
 * @property {SystemMetrics} [metrics] - Real-time system resource metrics
 * @property {() => void} [onViewFullMonitor] - Handler to navigate to full /monitor route
 * ─────────────────────────────────────────────────────────────────────────────
 */

/**
 * Validates whether a connection item matches the expected contract.
 * @param {unknown} item
 * @returns {boolean}
 */
export function isValidConnection(item) {
  return (
    item !== null &&
    typeof item === 'object' &&
    typeof item.id === 'string' &&
    typeof item.remote_addr === 'string' &&
    typeof item.is_external === 'boolean'
  )
}

/**
 * Canonical default metrics for air-gapped baseline.
 * @type {SystemMetrics}
 */
export const DEFAULT_METRICS = {
  cpuPercent: 14,
  memoryGb: 3.8,
  networkRate: '0.0 MB/s',
}
