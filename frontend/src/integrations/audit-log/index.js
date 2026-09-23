import React from 'react'
// Teammate swap: change the import below to:
import Component from './AuditLog'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for AuditLog.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').AuditLogProps} props
 */
export function AuditLog(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default AuditLog
