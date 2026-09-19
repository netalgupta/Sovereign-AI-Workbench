import React, { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

/**
 * InlineMiniGraph — Compact node/edge SVG visualization inside the thinking tree.
 * Monochromatic minimal styling matching the thinking block (plain lines & dots).
 */
export function InlineMiniGraph({
  nodes = [],
  relationships = [],
  target = '',
  title = 'Graph Traversal',
}) {
  // If no nodes provided, render nothing
  if (!nodes || nodes.length === 0) return null

  // Layout 2 to 7 nodes in a compact viewbox (width 280, height 100)
  const layout = useMemo(() => {
    const W = 280
    const H = 100
    const pad = 24
    const count = nodes.length

    const nodePositions = new Map()

    if (count === 1) {
      nodePositions.set(nodes[0].id || nodes[0].name, { x: W / 2, y: H / 2, ...nodes[0] })
    } else if (count === 2) {
      nodePositions.set(nodes[0].id || nodes[0].name, { x: W * 0.28, y: H / 2, ...nodes[0] })
      nodePositions.set(nodes[1].id || nodes[1].name, { x: W * 0.72, y: H / 2, ...nodes[1] })
    } else {
      // Find central or target node
      const centerNode = nodes.find((n) => n.is_target || n.name === target) || nodes[0]
      const otherNodes = nodes.filter((n) => n !== centerNode)

      nodePositions.set(centerNode.id || centerNode.name, {
        x: W / 2,
        y: H / 2,
        isCenter: true,
        ...centerNode,
      })

      const radiusX = Math.min((W - 2 * pad) / 2, 95)
      const radiusY = Math.min((H - 2 * pad) / 2, 34)

      otherNodes.forEach((n, idx) => {
        const angle = (2 * Math.PI * idx) / otherNodes.length - Math.PI / 2
        const x = W / 2 + radiusX * Math.cos(angle)
        const y = H / 2 + radiusY * Math.sin(angle)
        nodePositions.set(n.id || n.name, { x, y, isCenter: false, ...n })
      })
    }

    const positionedNodes = Array.from(nodePositions.values())

    // Map relationships to lines
    const links = []
    if (relationships && relationships.length > 0) {
      relationships.forEach((r, i) => {
        const src = nodePositions.get(r.source) || positionedNodes.find((p) => p.name === r.source)
        const tgt = nodePositions.get(r.target) || positionedNodes.find((p) => p.name === r.target)
        if (src && tgt) {
          links.push({
            id: r.id || `rel-${i}`,
            type: r.type || 'RELATED',
            x1: src.x,
            y1: src.y,
            x2: tgt.x,
            y2: tgt.y,
          })
        }
      })
    } else if (positionedNodes.length > 1) {
      // Create spokes to center
      const center = positionedNodes[0]
      for (let i = 1; i < positionedNodes.length; i++) {
        links.push({
          id: `spoke-${i}`,
          type: 'RELATED',
          x1: center.x,
          y1: center.y,
          x2: positionedNodes[i].x,
          y2: positionedNodes[i].y,
        })
      }
    }

    return { nodes: positionedNodes, links }
  }, [nodes, relationships, target])

  return (
    <div
      className="my-1.5 p-2 rounded-lg border flex flex-col gap-1 select-none max-w-[340px] text-xs"
      style={{
        background: 'var(--color-bg)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div className="flex items-center justify-between px-1 text-[10px] font-mono text-muted">
        <span className="truncate">{title} ({layout.nodes.length} nodes)</span>
        <Link
          to="/sources"
          className="flex items-center gap-1 hover:underline hover:text-[var(--color-text)] transition-fast cursor-pointer"
          title="Open in Knowledge Graph inspector"
        >
          <span>Explore graph</span>
          <ExternalLink size={9} />
        </Link>
      </div>

      <div className="w-full h-[95px] relative rounded overflow-hidden bg-white/5 border border-dashed border-[var(--color-border)]">
        <svg
          viewBox="0 0 280 100"
          className="w-full h-full"
          style={{ overflow: 'visible' }}
        >
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 6 6"
              refX="11"
              refY="3"
              markerWidth="4"
              markerHeight="4"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 5 3 L 0 5 z" fill="var(--color-text-muted)" opacity="0.6" />
            </marker>
          </defs>

          {/* Links */}
          {layout.links.map((link) => (
            <g key={link.id}>
              <line
                x1={link.x1}
                y1={link.y1}
                x2={link.x2}
                y2={link.y2}
                stroke="var(--color-border-strong)"
                strokeWidth="1.2"
                strokeDasharray="3 2"
                markerEnd="url(#arrow)"
                opacity="0.75"
              />
              {link.type && (
                <text
                  x={(link.x1 + link.x2) / 2}
                  y={(link.y1 + link.y2) / 2 - 3}
                  textAnchor="middle"
                  className="font-mono"
                  style={{
                    fontSize: '8px',
                    fill: 'var(--color-text-faint)',
                    letterSpacing: '0.02em',
                  }}
                >
                  {link.type.length > 14 ? `${link.type.slice(0, 13)}…` : link.type}
                </text>
              )}
            </g>
          ))}

          {/* Nodes */}
          {layout.nodes.map((node) => {
            const isTarget = node.isCenter || node.is_target || node.name === target
            const label = node.name || node.id || 'Node'
            const shortLabel = label.length > 12 ? `${label.slice(0, 11)}…` : label

            return (
              <g key={node.id || node.name} className="cursor-default group">
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isTarget ? 6 : 4.5}
                  fill={isTarget ? 'var(--color-accent)' : 'var(--color-surface)'}
                  stroke={isTarget ? 'var(--color-accent-border)' : 'var(--color-border-strong)'}
                  strokeWidth={isTarget ? 2 : 1.5}
                />
                <text
                  x={node.x}
                  y={node.y + 12}
                  textAnchor="middle"
                  className="font-mono font-medium"
                  style={{
                    fontSize: '9px',
                    fill: isTarget ? 'var(--color-text)' : 'var(--color-text-muted)',
                  }}
                >
                  {shortLabel}
                </text>
                <title>{`${label} ${node.labels ? `(${node.labels.join(', ')})` : ''}`}</title>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

export default InlineMiniGraph
