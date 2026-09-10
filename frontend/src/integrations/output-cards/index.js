import React from 'react'
// Teammate swap: change the import below to:
// import Component from './OutputCards'
import Component from './Placeholder'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for OutputCards.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').OutputCardsProps} props
 */
export function OutputCards(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default OutputCards
