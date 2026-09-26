/**
 * Pure derivation of the network monitor's security state — CARD 07 / FR-15.
 *
 * No React, no JSX: this is the exact logic NetworkMonitor.jsx renders
 * with, and the offline `npm test` (node:test) proves derives ALERT on an
 * external connection. The frontend has no JS test runner and no test
 * harness for DOM rendering, so the alarm derivation lives here in a plain
 * ESM module where Node's built-in test runner can exercise it directly.
 *
 * Alarm semantics: the ALARM is driven ONLY by `externalCount` — this
 * application's process tree and the Ollama model server
 * (backend/audit/network_monitor.py). 
 * `hostExternalCount` is the whole machine (browser, IDE, OS) and is
 * shown as clearly-labelled context — it must never drive the alarm.
 */

export const SECURE = '#10b981'
export const DANGER = '#ef4444'
export const UNKNOWN = '#f59e0b'

export function deriveSecurityState({ data, error }) {
  const live = Boolean(data) && data.scope === 'application'
  const extApp = live && typeof data.externalCount === 'number' ? data.externalCount : null
  const hostExt = live && typeof data.hostExternalCount === 'number' ? data.hostExternalCount : null
  const hostNote = live ? data.hostNote || '' : ''

  // Order matters: an errored poll means we can no longer attest to the
  // last successful reading, so stale data is NOT shown as green.
  // The backend reports a socket-read failure as status "error" with
  // externalCount -1 ("must NEVER masquerade as a verified secure state").
  // Only `extApp > 0` was checked, and -1 is not > 0: the bar read
  // "Air-Gap Secure — 0 external connections" exactly when the backend
  // said it could not look.
  const readFailed = live && (data.status === 'error' || (extApp !== null && extApp < 0))
  const security = error
    ? 'unreachable'
    : readFailed
    ? 'unverified'
    : !live || extApp === null
    ? 'checking'
    : extApp > 0
    ? 'external_detected'
    : 'secure'

  const isSecure = security === 'secure'
  const color = isSecure ? SECURE : security === 'external_detected' ? DANGER : UNKNOWN

  const headline =
    security === 'external_detected'
      ? `ALERT: External Traffic — ${extApp} external connection${extApp === 1 ? '' : 's'}`
      : isSecure
      ? 'Air-Gap Secure — 0 external connections'
      : security === 'unreachable'
      ? 'Monitor not connected — backend not running'
      : security === 'unverified'
      ? `Egress NOT verified — ${data.error || 'socket inspection failed'}`
      : 'Checking connection…'

  return {
    live,
    extApp,
    hostExt,
    hostNote,
    security,
    isSecure,
    dotColor: color,
    statusPillColor: color,
    headline,
  }
}