/**
 * Design tokens and helpers for the Neo4j Knowledge Graph.
 *
 * Distinct curated palettes ensure immediate visual differentiation between
 * entity types (Equipment, PipelineSegment, Document, Incident, Person)
 * in both light and dark themes while maintaining industrial UI elegance.
 */

export const LIGHT_LABEL_COLORS = {
  Equipment: '#C26A10',        // amber / bronze — refinery units, vessels, reactors
  PipelineSegment: '#12798C',  // deep teal / cyan — pipeline corridors & pumping stations
  Document: '#5B5F9E',         // slate indigo / blue — SOPs, P&IDs, QA logs, reports
  Incident: '#A63927',         // deep coral / crimson — safety incidents & alarms
  Person: '#2F7A52',           // forest emerald — engineers & operators
}

export const DARK_LABEL_COLORS = {
  Equipment: '#F59E0B',        // warm golden amber
  PipelineSegment: '#06B6D4',  // electric cyan / aqua
  Document: '#818CF8',         // periwinkle / soft indigo
  Incident: '#F43F5E',         // vivid coral / rose red
  Person: '#10B981',           // vibrant emerald green
}

export const DEFAULT_LABEL_COLORS = DARK_LABEL_COLORS

export const LABEL_COLOR_VARS = {
  Equipment: '--graph-equipment',
  PipelineSegment: '--graph-segment',
  Document: '--graph-document',
  Incident: '--graph-incident',
  Person: '--graph-person',
}

/**
 * Returns a robust hex/rgb color for an entity node based on its primary label,
 * inspecting CSS variables with full fallback to curated theme palettes.
 */
export function getNodeColor(node, cssVar = null) {
  if (!node) return '#94A3B8'
  const label = Array.isArray(node.labels) ? node.labels[0] : (node.label || '')

  if (label && LABEL_COLOR_VARS[label]) {
    const varName = LABEL_COLOR_VARS[label]
    if (typeof cssVar === 'function') {
      const val = cssVar(varName)
      if (val && val !== '#888' && val !== '#808080' && val !== '') {
        return val
      }
    }
    const isDark =
      typeof document !== 'undefined' &&
      (document.documentElement.getAttribute('data-theme') === 'dark' ||
        document.documentElement.classList.contains('dark') ||
        (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches))
    const palette = isDark ? DARK_LABEL_COLORS : LIGHT_LABEL_COLORS
    return palette[label] || DEFAULT_LABEL_COLORS[label] || '#A855F7'
  }

  return '#94A3B8'
}

/**
 * Neo4j stores a different key property per label (GRAPH_SPEC §4.1), so
 * there is no single "name" field to read.
 */
export function nodeName(node) {
  if (!node) return ''
  const p = node.properties || {}
  return (
    p.tag ||
    p.segment_name ||
    p.name ||
    p.summary ||
    p.title ||
    p.filename ||
    `${(node.labels && node.labels[0]) || 'Node'} ${String(node.id || '').split(':').pop()}`
  )
}
