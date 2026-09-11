import { SourcesPage } from '../../pages/SourcesPage'
const Component = SourcesPage

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for SourcesPanel.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').SourcesPanelProps} props
 */
export function SourcesPanel(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default SourcesPanel
