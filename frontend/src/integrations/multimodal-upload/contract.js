/**
 * contract.js — Multimodal Upload shape contract for the integration boundary.
 *
 * Owner: Sahil (CARD 09 / FRONTEND.md §3.13)
 *
 * Real MultimodalUpload component MUST accept exactly this shape:
 * {
 *   onUpload: (files: File[]) => void | Promise<void>,
 *   onRemove?: (fileId: string) => void,
 *   pendingFiles?: UploadedFileItem[],
 *   acceptedTypes?: string[],
 *   maxSizeBytes?: number,
 *   isCompact?: boolean,      // true for composer paperclip icon button, false for dropzone modal
 *   disabled?: boolean,
 * }
 *
 * Features per §3.13:
 * - Drag-and-drop or paperclip-icon upload directly in the chat composer
 * - Shows thumbnail preview in message / composer tray before processing
 * - Extracted OCR/vision feeds as tool events
 *
 * @typedef {Object} UploadedFileItem
 * @property {string} id - Unique file key
 * @property {File} [file] - Native browser File instance
 * @property {string} name - Human-readable filename
 * @property {number} size - File size in bytes
 * @property {string} [previewUrl] - Object URL or base64 data preview
 * @property {'queued'|'uploading'|'processing'|'ready'|'error'} [status='ready'] - File state
 * @property {number} [progress=100] - Upload progress (0-100)
 *
 * @typedef {Object} MultimodalUploadProps
 * @property {(files: File[]) => void | Promise<void>} onUpload - Files selected callback
 * @property {(fileId: string) => void} [onRemove] - File removal callback
 * @property {UploadedFileItem[]} [pendingFiles=[]] - Currently queued files
 * @property {string[]} [acceptedTypes=['.pdf','.png','.jpg','.jpeg','.tiff']] - Supported MIME/extensions
 * @property {number} [maxSizeBytes=52428800] - Maximum file limit (default 50MB)
 * @property {boolean} [isCompact=true] - Display mode (compact button vs expanded modal)
 * @property {boolean} [disabled=false] - Disable user interactions
 */

/**
 * Lightweight runtime validation for MultimodalUpload props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true
  if (props.onUpload && typeof props.onUpload !== 'function') {
    console.warn('[Integration: multimodal-upload] Contract violation: `onUpload` must be a function.', props)
    return false
  }
  if (props.pendingFiles && !Array.isArray(props.pendingFiles)) {
    console.warn('[Integration: multimodal-upload] Contract violation: `pendingFiles` must be an Array.', props)
    return false
  }
  return true
}

export const CANONICAL_UPLOAD_SAMPLE = [
  {
    id: 'sample-scan-1',
    name: 'refinery_flange_leak_scan.png',
    size: 2450000,
    previewUrl: '',
    status: 'ready',
    progress: 100,
  },
]
