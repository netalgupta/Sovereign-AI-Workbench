import React from 'react'
// Teammate swap: change the import below to:
// import Component from './CitationCard'
import Component from './Placeholder'

import { validateProps } from './contract'
export { SourcesUsedList } from './SourcesUsedList.jsx'
export * from './contract'

/**
 * Adapter wrapper for CitationCard.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').CitationCardProps} props
 */
export function CitationCard(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default CitationCard
