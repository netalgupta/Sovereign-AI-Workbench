/**
 * contract.js — Graph Explorer shape contract for the integration boundary.
 *
 * Owner: Netal (CARD 03 / FRONTEND.md §3.6)
 *
 * Real GraphExplorer component MUST accept exactly this shape:
 * {
 *   entities?: GraphEntity[],
 *   relationships?: GraphRelationship[],
 *   onNodeSelect?: (entityId: string, entityData?: GraphEntity) => void,
 *   onSubgraphHighlight?: (subgraphId: string | string[]) => void,
 *   searchQuery?: string,
 * }
 *
 * Interaction requirement:
 * Clicking a graph node must call `onNodeSelect(entityId)` so the Sources panel
 * can filter and highlight referencing documents.
 *
 * @typedef {Object} GraphEntity
 * @property {string} id - Unique entity ID (e.g. "valve-v204", "pipeline-hcu-01")
 * @property {string} label - Human-readable node label (e.g. "V-204 Bypass Valve")
 * @property {'SOP'|'Equipment'|'Valve'|'Report'|'Person'|'Pipeline'|'Date'} type - Entity classification
 * @property {Record<string, any>} [properties] - Custom entity properties (e.g. unit, pressure)
 *
 * @typedef {Object} GraphRelationship
 * @property {string} id - Unique edge ID
 * @property {string} source - Source entity ID
 * @property {string} target - Target entity ID
 * @property {string} type - Relationship predicate (e.g. "REFERENCES", "CONTROLS", "MONITORED_BY")
 * @property {string} [label] - Optional display edge label
 *
 * @typedef {Object} GraphExplorerProps
 * @property {GraphEntity[]} [entities] - Knowledge graph nodes
 * @property {GraphRelationship[]} [relationships] - Knowledge graph edges
 * @property {(entityId: string, entityData?: GraphEntity) => void} [onNodeSelect] - Node selection callback
 * @property {(subgraphId: string | string[]) => void} [onSubgraphHighlight] - Subgraph highlight callback
 * @property {string} [searchQuery] - Search filter query
 */

/**
 * Lightweight runtime validation for GraphExplorer props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) return true
  if (props.entities && !Array.isArray(props.entities)) {
    console.warn('[Integration: graph-explorer] Contract violation: `entities` must be an Array.', props)
    return false
  }
  if (props.relationships && !Array.isArray(props.relationships)) {
    console.warn('[Integration: graph-explorer] Contract violation: `relationships` must be an Array.', props)
    return false
  }
  if (props.onNodeSelect && typeof props.onNodeSelect !== 'function') {
    console.warn('[Integration: graph-explorer] Contract violation: `onNodeSelect` must be a function.', props)
    return false
  }
  return true
}

export const CANONICAL_GRAPH = {
  entities: [
    { id: 'valve-v204', label: 'V-204 Bypass Valve', type: 'Valve', properties: { unit: 'HCU', spec: '150 psi' } },
    { id: 'pipe-hcu-3a', label: 'HCU Feed Line 3A', type: 'Pipeline', properties: { diameter: '12-inch', metallurgy: 'Cr-Mo' } },
    { id: 'sop-hcu-01', label: 'HCU Operations Manual §4.2', type: 'SOP', properties: { docId: 'sop-hcu-01' } },
    { id: 'cat-bed-1', label: 'Reactor Catalyst Bed 1', type: 'Equipment', properties: { maxTemp: '425°C' } },
    { id: 'insp-report-aug', label: 'UT Thickness Survey Aug 2026', type: 'Report', properties: { corrosionRate: '0.12 mm/yr' } },
  ],
  relationships: [
    { id: 'rel-1', source: 'valve-v204', target: 'pipe-hcu-3a', type: 'CONTROLS' },
    { id: 'rel-2', source: 'sop-hcu-01', target: 'valve-v204', type: 'GOVERNS' },
    { id: 'rel-3', source: 'pipe-hcu-3a', target: 'cat-bed-1', type: 'FEEDS' },
    { id: 'rel-4', source: 'insp-report-aug', target: 'pipe-hcu-3a', type: 'INSPECTED' },
  ],
}
