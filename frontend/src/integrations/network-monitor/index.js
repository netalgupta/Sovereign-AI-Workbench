import React from 'react'
import Component from './NetworkMonitor'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for NetworkMonitor.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').NetworkMonitorProps} props
 */
export function NetworkMonitor(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

/**
 * Convenience export for persistent chat footer widget.
 */
export function NetworkMonitorBar(props) {
  return React.createElement(NetworkMonitor, { ...props, mode: 'bar' })
}

export default NetworkMonitor
