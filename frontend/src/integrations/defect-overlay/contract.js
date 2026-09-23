/**
 * contract.js — OCR Text-Region Overlay shape contract for the integration boundary.
 *
 * Owner: Sahil (TOOLS.md row 7 — descoped: text-region overlay only, NOT
 * defect/anomaly detection)
 *
 * Real overlay component MUST accept exactly this shape:
 * {
 *   imageUrl: string,             // Image source
 *   detections: TextRegion[],     // OCR text-region boxes & confidence
 *   selectedDetectionId?: string, // Highlighted box
 *   onSelectBox?: (detectionId: string) => void,
 *   findings?: Array<{ id: string, description: string, detectionId: string }>,
 *   showLabels?: boolean,
 * }
 *
 * Visual requirement per §3.14:
 * Renders the original image with bounding boxes overlaid (canvas or SVG overlay on top of <img>),
 * each box labeled with the recognized text and confidence. Clicking a box highlights the corresponding
 * region.
 *
 * @typedef {Object} BoundingBox
 * @property {number} xmin - Left coordinate (0 to 1 normalized, or pixel value)
 * @property {number} ymin - Top coordinate (0 to 1 normalized, or pixel value)
 * @property {number} xmax - Right coordinate (0 to 1 normalized, or pixel value)
 * @property {number} ymax - Bottom coordinate (0 to 1 normalized, or pixel value)
 *
 * @typedef {Object} TextRegion
 * @property {string} id - Unique region ID (e.g. "det-ocr-000")
 * @property {string} label - Recognized text of the OCR text region (never a defect class)
 * @property {number} confidence - OCR transcription confidence (0.0 to 1.0)
 * @property {BoundingBox} box - Box coordinates
 * @property {'low'|'medium'|'high'|'critical'} [severity='low'] - Always "low" for text regions; a future real detector may raise it
 * @property {string} [kind='text_region'] - Always "text_region" for OCR-output boxes
 *
 * @typedef {Object} DefectOverlayProps
 * @property {string} imageUrl - Image URL
 * @property {TextRegion[]} detections - OCR text-region boxes
 * @property {string} [selectedDetectionId] - Active box
 * @property {(detectionId: string) => void} [onSelectBox] - Box click handler
 * @property {Array<{ id: string, description: string, detectionId: string }>} [findings] - Linked region descriptions
 * @property {boolean} [showLabels=true] - Toggle display of text/confidence tags
 */

/**
 * Lightweight runtime validation for DefectOverlay props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) {
    console.warn('[Integration: defect-overlay] Missing props: DefectOverlay requires props object.')
    return false
  }
  const missing = []
  if (!props.imageUrl) missing.push('imageUrl')
  if (!props.detections || !Array.isArray(props.detections)) missing.push('detections (Array)')

  if (missing.length > 0) {
    console.warn(
      `[Integration: defect-overlay] Contract violation in DefectOverlay: missing required field(s): ${missing.join(
        ', '
      )}. Required shape: { imageUrl, detections }`,
      props
    )
    return false
  }
  return true
}
