import React from 'react'
// Teammate swap: change the import below to:
// import Component from './GraphExplorer'
import Component from './Placeholder'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for GraphExplorer.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').GraphExplorerProps} props
 */
export function GraphExplorer(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default GraphExplorer
