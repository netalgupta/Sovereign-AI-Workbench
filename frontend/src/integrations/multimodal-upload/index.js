import React from 'react'
import Component from './MultimodalUpload'

import { validateProps } from './contract'
export * from './contract'

/**
 * Adapter wrapper for MultimodalUpload.
 * Performs lightweight dev-time contract validation before delegating to implementation.
 *
 * @param {import('./contract').MultimodalUploadProps} props
 */
export function MultimodalUpload(props) {
  if (process.env.NODE_ENV !== 'production') {
    validateProps(props)
  }
  return React.createElement(Component, props)
}

export default MultimodalUpload
