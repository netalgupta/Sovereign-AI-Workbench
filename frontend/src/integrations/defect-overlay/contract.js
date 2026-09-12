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

export const CANONICAL_DEFECT_SAMPLE = {
  imageUrl: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=80',
  detections: [
    {
      id: 'det-01',
      label: 'Pipe Flange Corrosion',
      confidence: 0.94,
      severity: 'high',
      box: { xmin: 0.25, ymin: 0.3, xmax: 0.55, ymax: 0.65 },
    },
    {
      id: 'det-02',
      label: 'Insulation Degradation',
      confidence: 0.88,
      severity: 'medium',
      box: { xmin: 0.62, ymin: 0.45, xmax: 0.85, ymax: 0.75 },
    },
  ],
  findings: [
    {
      id: 'find-01',
      detectionId: 'det-01',
      description: 'Severe pitting corrosion noted along the weld neck flange of line HCU-FL-102.',
    },
    {
      id: 'find-02',
      detectionId: 'det-02',
      description: 'Moisture ingress behind mineral wool jacketing, potential CUI risk.',
    },
  ],
}
