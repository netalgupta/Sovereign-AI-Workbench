/**
 * formatTime.js — Shared timestamp formatting utility.
 *
 * FRONTEND.md §6, rule 5: "All timestamps display in a single consistent
 * format across the app (YYYY-MM-DD HH:mm, local time), defined once in
 * a shared utility, never formatted ad hoc per component."
 *
 * Every component that renders a timestamp MUST import from here.
 * Never use new Date().toLocaleString() or inline formatting in JSX.
 */

/**
 * Format an ISO 8601 string (or Date) to 'YYYY-MM-DD HH:mm' in local time.
 * @param {string | Date} input
 * @returns {string}
 */
export function formatTime(input) {
  const date = input instanceof Date ? input : new Date(input)
  if (isNaN(date.getTime())) return '—'

  const year   = date.getFullYear()
  const month  = String(date.getMonth() + 1).padStart(2, '0')
  const day    = String(date.getDate()).padStart(2, '0')
  const hours  = String(date.getHours()).padStart(2, '0')
  const mins   = String(date.getMinutes()).padStart(2, '0')

  return `${year}-${month}-${day} ${hours}:${mins}`
}

/**
 * Produce an ISO 8601 string for "right now" — used when creating messages.
 * @returns {string}
 */
export function now() {
  return new Date().toISOString()
}
