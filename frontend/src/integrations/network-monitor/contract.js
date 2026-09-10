/**
 * contract.js — Network Monitor shape contract for the integration boundary.
 *
 * Owner: Sahil (CARD 07 / FRONTEND.md §3.9)
 *
 * Real NetworkMonitor component MUST accept exactly this shape:
 * {
 *   status?: 'secure' | 'warning' | 'external_detected' | 'checking',
 *   externalCount?: number,     // 0 = green dot, >0 = RED immediately
 *   connections?: NetworkConnection[],
 *   metrics?: SystemMetrics,
 *   mode?: 'bar' | 'full' | 'widget', // 'bar' for chat footer, 'full' for /monitor route
 *   onViewFullMonitor?: () => void,
 * }
 *
 * Anti-hallucination note from CARD 07:
 * This must NEVER be a static/hardcoded display — wire it directly to CARD 07's
 * live websocket feed.
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
 * @property {'secure' | 'warning' | 'external_detected' | 'checking'} [status='secure'] - Air-gap security status
 * @property {number} [externalCount=0] - Number of external connections (0 = green, >0 = red)
 * @property {NetworkConnection[]} [connections=[]] - Active socket list
 * @property {SystemMetrics} [metrics] - Real-time system resource metrics
 * @property {'bar' | 'full' | 'widget'} [mode='bar'] - Display mode
 * @property {() => void} [onViewFullMonitor] - Handler to navigate to full /monitor route
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

export const CANONICAL_NETWORK_STATE = {
  status: 'secure',
  externalCount: 0,
  metrics: {
    cpuPercent: 14,
    memoryGb: 3.8,
    networkRate: '0.0 MB/s',
  },
  connections: [
    {
      id: 'conn-1',
      local_addr: '127.0.0.1:5173',
      remote_addr: '127.0.0.1:54320',
      status: 'ESTABLISHED',
      is_external: false,
      process: 'vite',
      timestamp: '2026-09-10 14:30:00',
    },
    {
      id: 'conn-2',
      local_addr: '127.0.0.1:8000',
      remote_addr: '127.0.0.1:54321',
      status: 'LISTEN',
      is_external: false,
      process: 'uvicorn (fastapi)',
      timestamp: '2026-09-10 14:30:00',
    },
    {
      id: 'conn-3',
      local_addr: '127.0.0.1:11434',
      remote_addr: '127.0.0.1:54322',
      status: 'LISTEN',
      is_external: false,
      process: 'ollama-runner',
      timestamp: '2026-09-10 14:30:00',
    },
    {
      id: 'conn-4',
      local_addr: '127.0.0.1:19530',
      remote_addr: '127.0.0.1:54323',
      status: 'ESTABLISHED',
      is_external: false,
      process: 'milvus-standalone',
      timestamp: '2026-09-10 14:30:00',
    },
  ],
}
