import React from 'react'
import Component from './DefectOverlay'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for DefectOverlay.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').DefectOverlayProps} props
 */
export function DefectOverlay(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default DefectOverlay
