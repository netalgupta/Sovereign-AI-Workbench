/**
 * contract.js — Defect / Annotation Overlay Viewer shape contract for the integration boundary.
 *
 * Owner: Sahil (CARD 10 / FRONTEND.md §3.14)
 *
 * Real DefectOverlay component MUST accept exactly this shape:
 * {
 *   imageUrl: string,             // Inspection photo source
 *   detections: DefectDetection[], // YOLOv8 bounding box coordinates & confidence
 *   selectedDetectionId?: string, // Highlighted box
 *   onSelectBox?: (detectionId: string) => void,
 *   findings?: Array<{ id: string, description: string, detectionId: string }>,
 *   showLabels?: boolean,
 * }
 *
 * Visual requirement per §3.14:
 * Renders the original image with bounding boxes overlaid (canvas or SVG overlay on top of <img>),
 * each box labeled with the detected class and confidence. Clicking a box highlights the corresponding
 * finding.
 *
 * @typedef {Object} BoundingBox
 * @property {number} xmin - Left coordinate (0 to 1 normalized, or pixel value)
 * @property {number} ymin - Top coordinate (0 to 1 normalized, or pixel value)
 * @property {number} xmax - Right coordinate (0 to 1 normalized, or pixel value)
 * @property {number} ymax - Bottom coordinate (0 to 1 normalized, or pixel value)
 *
 * @typedef {Object} DefectDetection
 * @property {string} id - Unique detection ID (e.g. "det-flange-01")
 * @property {string} label - Detected defect class (e.g. "Flange Corrosion", "Thermal Leak")
 * @property {number} confidence - YOLOv8 confidence score (0.0 to 1.0)
 * @property {BoundingBox} box - Box coordinates
 * @property {'low'|'medium'|'high'|'critical'} [severity='medium'] - Severity rating
 *
 * @typedef {Object} DefectOverlayProps
 * @property {string} imageUrl - Photo URL
 * @property {DefectDetection[]} detections - YOLOv8 detection boxes
 * @property {string} [selectedDetectionId] - Active detection
 * @property {(detectionId: string) => void} [onSelectBox] - Box click handler
 * @property {Array<{ id: string, description: string, detectionId: string }>} [findings] - Linked finding descriptions
 * @property {boolean} [showLabels=true] - Toggle display of class/confidence tags
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
