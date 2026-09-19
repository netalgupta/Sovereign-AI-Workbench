import React from 'react'
// Teammate swap: change the import below to:
import Component from './CalcTraceCard'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for CalcTraceCard.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').CalcTraceProps} props
 */
export function CalcTraceCard(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default CalcTraceCard
