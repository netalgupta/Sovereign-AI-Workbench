import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deriveSecurityState, SECURE, DANGER, UNKNOWN } from './security-state.js'

test('externalCount >= 1 derives the ALERT state (red)', () => {
  const s = deriveSecurityState({
    data: { scope: 'application', externalCount: 1, hostExternalCount: 2 },
    error: false,
  })
  assert.equal(s.security, 'external_detected')
  assert.equal(s.isSecure, false)
  assert.equal(s.dotColor, DANGER)
  assert.equal(s.statusPillColor, DANGER)
  assert.ok(s.headline.startsWith('ALERT: External Traffic'))
})

test('zero external connections derives air-gap secure (green)', () => {
  const s = deriveSecurityState({
    data: { scope: 'application', externalCount: 0, hostExternalCount: 0 },
    error: false,
  })
  assert.equal(s.security, 'secure')
  assert.equal(s.isSecure, true)
  assert.equal(s.dotColor, SECURE)
  assert.equal(s.statusPillColor, SECURE)
  assert.equal(s.extApp, 0)
})

test('host-wide connections alone never drive the alarm', () => {
  const s = deriveSecurityState({
    data: { scope: 'application', externalCount: 0, hostExternalCount: 44 },
    error: false,
  })
  assert.equal(s.security, 'secure')
  assert.equal(s.isSecure, true)
  assert.equal(s.dotColor, SECURE)
  assert.equal(s.hostExt, 44)
})

test('an errored poll never shows green even with stale data', () => {
  const s = deriveSecurityState({
    data: { scope: 'application', externalCount: 0, hostExternalCount: 44 },
    error: true,
  })
  assert.equal(s.security, 'unreachable')
  assert.equal(s.isSecure, false)
  assert.equal(s.dotColor, UNKNOWN)
})

test('no data yet derives checking (never green, never falsely red)', () => {
  const s = deriveSecurityState({ data: null, error: false })
  assert.equal(s.security, 'checking')
  assert.equal(s.isSecure, false)
  assert.equal(s.dotColor, UNKNOWN)
  assert.equal(s.extApp, null)
})

test('a non-application payload counts as no live reading', () => {
  const s = deriveSecurityState({
    data: { scope: 'machine', externalCount: 7, hostExternalCount: 7 },
    error: false,
  })
  assert.equal(s.security, 'checking')
  assert.equal(s.extApp, null)
})
test('a socket-read failure is never shown as secure', () => {
  // The backend's error payload: status "error", externalCount -1.
  const s = deriveSecurityState({
    data: { scope: 'application', status: 'error', externalCount: -1, error: 'Socket inspection permission denied' },
    error: null,
  })
  assert.equal(s.isSecure, false)
  assert.equal(s.security, 'unverified')
  assert.match(s.headline, /NOT verified/)
})
