import React, { useState } from 'react'
import { Network, Search, Sparkles, Layers, Info } from 'lucide-react'
import { CANONICAL_GRAPH } from './contract'

const TYPE_COLORS = {
  SOP: '#3b82f6',
  Equipment: '#f59e0b',
  Valve: '#ef4444',
  Report: '#10b981',
  Pipeline: '#8b5cf6',
  Person: '#6b7280',
  Date: '#9ca3af',
}

/**
 * Placeholder for GraphExplorer component.
 * Owner: Netal (FRONTEND.md §3.6)
 *
 * @param {import('./contract').GraphExplorerProps} props
 */
export default function Placeholder({
  entities = CANONICAL_GRAPH.entities,
  relationships = CANONICAL_GRAPH.relationships,
  onNodeSelect,
  onSubgraphHighlight,
  searchQuery = '',
}) {
  const [selectedId, setSelectedId] = useState(null)
  const [query, setQuery] = useState(searchQuery)

  const handleSelect = (entity) => {
    setSelectedId(entity.id)
    if (onNodeSelect) onNodeSelect(entity.id, entity)
  }

  const handleDemoSubgraph = () => {
    const targetIds = ['valve-v204', 'pipe-hcu-3a', 'sop-hcu-01']
    if (onSubgraphHighlight) onSubgraphHighlight(targetIds)
    setSelectedId('valve-v204')
  }

  const filteredEntities = entities.filter((e) =>
    e.label.toLowerCase().includes(query.toLowerCase())
  )

  const selectedEntity = entities.find((e) => e.id === selectedId)

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Top Header & Integration Handoff Banner ─────────────────────── */}
      <div
        className="px-6 py-4 border-b flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        style={{
          background: 'var(--color-card-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-accent)',
            }}
          >
            <Network size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Knowledge Graph Explorer
              </h2>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                Integration pending — owned by Netal
              </span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Interactive Neo4j entity-relationship canvas · FRONTEND.md §3.6
            </p>
          </div>
        </div>

        {/* Demo Signature Query Action */}
        <button
          type="button"
          onClick={handleDemoSubgraph}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors hover:shadow-xs"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-accent-border)',
            color: 'var(--color-accent)',
          }}
        >
          <Sparkles size={13} />
          <span>Demo: Highlight HCU Segment Subgraph</span>
        </button>
      </div>

      {/* ── Search Bar & Legend ─────────────────────────────────────────── */}
      <div
        className="px-6 py-2.5 border-b flex flex-wrap items-center justify-between gap-3 text-xs"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="relative flex-1 max-w-sm">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-muted)' }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entity (e.g. V-204, HCU, SOP)..."
            className="w-full pl-8 pr-3 py-1.5 rounded-md border text-xs focus:outline-none focus:ring-1"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        {/* Node Type Legend */}
        <div className="flex items-center gap-3 text-[11px]">
          {Object.entries(TYPE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
              <span style={{ color: 'var(--color-text-muted)' }}>{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Visual Graph Simulation Frame & Details Split ───────────────── */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Interactive Node Matrix / Canvas Frame */}
        <div
          className="flex-1 p-6 relative flex flex-col items-center justify-center overflow-auto"
          style={{
            background: 'radial-gradient(circle at 50% 50%, var(--color-surface) 0%, var(--color-bg) 100%)',
          }}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full max-w-3xl">
            {filteredEntities.map((entity) => {
              const isSelected = entity.id === selectedId
              const color = TYPE_COLORS[entity.type] || '#6b7280'
              return (
                <div
                  key={entity.id}
                  onClick={() => handleSelect(entity)}
                  className="p-4 rounded-xl border cursor-pointer transition-all duration-150 hover:-translate-y-0.5"
                  style={{
                    background: isSelected ? 'var(--color-surface)' : 'var(--color-card-bg)',
                    borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-card-border)',
                    boxShadow: isSelected ? '0 0 0 2px var(--color-accent)' : 'none',
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                      style={{
                        background: `${color}20`,
                        color: color,
                      }}
                    >
                      {entity.type}
                    </span>
                    <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                      {entity.id}
                    </span>
                  </div>
                  <h4 className="text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                    {entity.label}
                  </h4>
                  {entity.properties && (
                    <div className="mt-2 text-[10px] font-mono space-y-0.5" style={{ color: 'var(--color-text-muted)' }}>
                      {Object.entries(entity.properties).map(([k, v]) => (
                        <div key={k}>
                          {k}: <strong style={{ color: 'var(--color-text)' }}>{String(v)}</strong>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <p className="absolute bottom-4 text-[11px] font-mono text-center" style={{ color: 'var(--color-text-muted)' }}>
            Tip: Click any entity to trigger `onNodeSelect` callback and filter Sources panel.
          </p>
        </div>

        {/* Node Relationship Drawer */}
        <div
          className="w-full md:w-80 border-t md:border-t-0 md:border-l p-5 flex flex-col gap-4 overflow-y-auto"
          style={{
            background: 'var(--color-card-bg)',
            borderColor: 'var(--color-border)',
          }}
        >
          <div className="flex items-center gap-2">
            <Info size={16} style={{ color: 'var(--color-accent)' }} />
            <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
              Entity Inspector
            </h3>
          </div>

          {selectedEntity ? (
            <div className="flex flex-col gap-3 text-xs">
              <div
                className="p-3 rounded-lg border"
                style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
              >
                <span className="text-[10px] font-mono uppercase" style={{ color: 'var(--color-text-muted)' }}>
                  Selected Node
                </span>
                <p className="font-bold text-sm mt-0.5" style={{ color: 'var(--color-text)' }}>
                  {selectedEntity.label}
                </p>
                <p className="text-[11px] font-mono text-amber-500">{selectedEntity.type}</p>
              </div>

              <div>
                <p className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--color-text)' }}>
                  Connected Relationships:
                </p>
                <div className="space-y-1.5">
                  {relationships
                    .filter((r) => r.source === selectedEntity.id || r.target === selectedEntity.id)
                    .map((rel) => (
                      <div
                        key={rel.id}
                        className="p-2 rounded border text-[11px] font-mono"
                        style={{
                          background: 'var(--color-card-bg)',
                          borderColor: 'var(--color-border)',
                          color: 'var(--color-text)',
                        }}
                      >
                        <span style={{ color: 'var(--color-accent)' }}>{rel.type}</span>
                        <div className="text-[10px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                          {rel.source} ➔ {rel.target}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6" style={{ color: 'var(--color-text-muted)' }}>
              <Layers size={28} className="opacity-40 mb-2" />
              <p className="text-xs font-medium">Select a node from the canvas to inspect its relationships</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
