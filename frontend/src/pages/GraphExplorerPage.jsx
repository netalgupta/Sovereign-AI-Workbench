import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  GitBranch, Maximize2, Minimize2, RefreshCw, Search, Sparkles, X, Zap,
} from 'lucide-react'
import { ForceGraph } from '../components/graph/ForceGraph'
import { nodeName, getNodeColor } from '../components/graph/graphTheme'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import { Network } from 'lucide-react'
import { fetchFullGraph, fetchNeighbourhood, fetchCentrality } from '../lib/graphApi'

/**
 * GraphExplorerPage — interactive knowledge graph explorer (FRONTEND.md §3.6, /graph).
 *
 * KEY FEATURE: Multi-hop neighbourhood traversal with hop-by-hop reveal animation.
 *
 * When you click a node, pressing "Explore neighbourhood" fetches
 *   GET /api/graph/neighbourhood?node=X&hops=2
 * which returns nodes tagged with their `distance` from the origin.
 * The graph then reveals them sequentially: distance-0 first, then distance-1
 * (after 400ms), then distance-2 (after 800ms). A graph that unfolds is an
 * explanation; a hairball that appears all at once is not.
 *
 * The hop histogram (e.g. "1 hub · 2 near · 5 far") is shown in the inspector
 * so you can see the shape of the subgraph before exploring it further.
 *
 * Signature demo button: "Mangalore-Hassan" pipeline segment, hops=2
 * Expected result per GRAPH_SPEC §6: 8 nodes, 18 edges, {0:1, 1:2, 2:5}
 *
 * Data source: /api/graph (live backend) → /pipeline/graph.json (static fallback).
 * If /api/graph returns 0 nodes, the Neo4j container lost its data; rebuild with:
 *   py -3 -m backend.evaluation.build_graph
 */

const HOP_REVEAL_DELAY_MS = 420   // delay between each hop being revealed
const MAX_HOPS = 3

export function GraphExplorerPage() {
  // ── Full graph state ──────────────────────────────────────────────────────
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [dataSource, setDataSource] = useState(null)   // 'live' | 'snapshot'

  // ── UI state ──────────────────────────────────────────────────────────────
  const [selected, setSelected] = useState(null)
  const [labelFilter, setLabelFilter] = useState('')
  const [query, setQuery] = useState('')
  const [focusId, setFocusId] = useState(null)
  const [fullPage, setFullPage] = useState(false)
  const [reheat, setReheat] = useState(0)

  // ── Neighbourhood / hop-reveal state ─────────────────────────────────────
  const [neighbourhood, setNeighbourhood] = useState(null)   // { nodes, edges, by_distance, source }
  const [hopLoading, setHopLoading] = useState(false)
  const [revealedHops, setRevealedHops] = useState(null)     // Set<number> | null
  const [highlightIds, setHighlightIds] = useState(null)     // Set<string>  | null
  const [centrality, setCentrality] = useState({})           // { [nodeId]: { pagerank, ... } }
  const [hopCount, setHopCount] = useState(2)

  const revealTimers = useRef([])

  // ── Load full graph on mount ──────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    fetchFullGraph()
      .then((d) => {
        if (cancelled) return
        setData(d)
        setDataSource(d.source)
      })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [])

  // Escape → exit full-page
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setFullPage(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // ── Derived: labels, counts ───────────────────────────────────────────────
  const labels = useMemo(() => {
    if (!data) return []
    return [...new Set(data.nodes.flatMap((n) => n.labels))].sort()
  }, [data])

  const counts = useMemo(() => {
    if (!data) return {}
    const c = {}
    data.nodes.forEach((n) => n.labels.forEach((l) => { c[l] = (c[l] || 0) + 1 }))
    return c
  }, [data])

  // ── Edges attached to the selected node ──────────────────────────────────
  const attachedEdges = useMemo(() => {
    if (!data || !selected) return []
    const source = neighbourhood
      ? { nodes: neighbourhood.nodes, relationships: neighbourhood.edges }
      : data
    return (source.relationships ?? source.edges ?? [])
      .filter((r) => r.source === selected.id || r.target === selected.id)
      .map((r) => {
        const otherId = r.source === selected.id ? r.target : r.source
        const other = (source.nodes ?? []).find((n) => n.id === otherId)
        return {
          type: r.type,
          outgoing: r.source === selected.id,
          name: other ? nodeName(other) : otherId,
          otherId,
        }
      })
  }, [data, selected, neighbourhood])

  // ── Clear timers helper ───────────────────────────────────────────────────
  const clearRevealTimers = () => {
    revealTimers.current.forEach(clearTimeout)
    revealTimers.current = []
  }

  // ── Start hop-by-hop reveal animation ────────────────────────────────────
  const startReveal = useCallback((byDistance, nodeIds) => {
    clearRevealTimers()
    const maxHop = Math.max(...Object.keys(byDistance).map(Number))
    const hIds = new Set(nodeIds)
    setHighlightIds(hIds)
    setRevealedHops(new Set([0]))   // distance 0 appears immediately

    for (let hop = 1; hop <= maxHop; hop++) {
      const h = hop
      const t = setTimeout(() => {
        setRevealedHops((prev) => {
          const next = new Set(prev)
          next.add(h)
          return next
        })
      }, h * HOP_REVEAL_DELAY_MS)
      revealTimers.current.push(t)
    }
  }, [])

  // ── Fetch neighbourhood for a node ───────────────────────────────────────
  const exploreNeighbourhood = useCallback(async (nodeId, hops = hopCount) => {
    if (!data) return
    setHopLoading(true)
    setNeighbourhood(null)
    setRevealedHops(null)
    setHighlightIds(null)
    clearRevealTimers()

    try {
      const nb = await fetchNeighbourhood(nodeId, hops, data)
      setNeighbourhood(nb)
      startReveal(nb.by_distance, nb.nodes.map((n) => n.id))

      // Fetch centrality scores so inspector can show which nodes matter most
      const cResult = await fetchCentrality(nb.nodes.map((n) => n.id))
      setCentrality(cResult)
    } finally {
      setHopLoading(false)
    }
  }, [data, hopCount, startReveal])

  // ── Clear neighbourhood, back to full graph ───────────────────────────────
  const clearNeighbourhood = useCallback(() => {
    clearRevealTimers()
    setNeighbourhood(null)
    setRevealedHops(null)
    setHighlightIds(null)
    setCentrality({})
  }, [])

  // ── Signature demo: Mangalore-Hassan, hops=2 ─────────────────────────────
  const runSignatureDemo = useCallback(async () => {
    if (!data) return
    // Find the Mangalore-Hassan node
    const seg = data.nodes.find((n) =>
      n.labels.includes('PipelineSegment') &&
      (n.properties?.segment_name === 'Mangalore-Hassan' ||
       nodeName(n).toLowerCase().includes('mangalore'))
    )
    if (seg) {
      setSelected(seg)
      setFocusId(seg.id)
      await exploreNeighbourhood(seg.id, 2)
    } else {
      // Node not in graph yet — show a clear message
      alert(
        'PipelineSegment "Mangalore-Hassan" not found in the current graph.\n' +
        'Run: py -3 -m backend.evaluation.build_graph'
      )
    }
  }, [data, exploreNeighbourhood])

  // ── Search ────────────────────────────────────────────────────────────────
  const runSearch = (value) => {
    setQuery(value)
    if (!value || !data) return
    const hit = data.nodes.find((n) =>
      nodeName(n).toLowerCase().includes(value.toLowerCase()))
    if (hit) {
      setSelected(hit)
      setFocusId(hit.id)
    }
  }

  // ── Nodes + relationships to pass to ForceGraph ───────────────────────────
  // When neighbourhood mode is active, only show neighbourhood nodes+edges.
  // The full graph's nodes that are NOT in the neighbourhood are still rendered
  // but ghosted (revealByDistance handles that).
  const graphNodes = data?.nodes ?? []
  const graphEdges = neighbourhood
    ? neighbourhood.edges
    : (data?.relationships ?? [])

  // ── Hop histogram label ───────────────────────────────────────────────────
  function histogramLabel(byDistance) {
    const entries = Object.entries(byDistance).sort(([a], [b]) => Number(a) - Number(b))
    const labels2 = ['hub', 'near', 'far', 'distant']
    return entries.map(([d, n]) => `${n} ${labels2[Number(d)] ?? `+${d}`}`).join(' · ')
  }

  // ── Render ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <EmptyState
          icon={Network}
          title="Graph unavailable"
          description={error}
        />
      </div>
    )
  }
  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <Spinner />
      </div>
    )
  }

  return (
    <div
      className={fullPage ? 'fixed inset-0 z-50 flex flex-col' : 'flex-1 flex flex-col min-h-0'}
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Header ── */}
      <header
        className="flex items-center gap-3 flex-wrap px-5 py-3 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="mr-auto">
          <h1 className="text-base font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            Knowledge graph
            {neighbourhood && (
              <span
                className="text-[11px] font-normal px-2 py-0.5 rounded-full"
                style={{
                  background: 'var(--color-accent-soft, #f5ede8)',
                  color: 'var(--color-accent)',
                }}
              >
                neighbourhood · {neighbourhood.source}
              </span>
            )}
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {neighbourhood
              ? `${neighbourhood.nodes.length} nodes · ${neighbourhood.edges.length} edges · ${histogramLabel(neighbourhood.by_distance)}`
              : `${data.nodes.length} nodes · ${data.relationships.length} relationships · ${dataSource ?? ''}`
            }
            {' · drag to move, scroll to zoom, click to inspect'}
          </p>
        </div>

        {/* Signature demo button */}
        <button
          type="button"
          onClick={runSignatureDemo}
          disabled={hopLoading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md border font-medium"
          style={{
            background: 'var(--color-accent-soft, #f5ede8)',
            borderColor: 'var(--color-accent)',
            color: 'var(--color-accent)',
            opacity: hopLoading ? 0.6 : 1,
          }}
          title="GRAPH_SPEC §6 signature demo — Mangalore-Hassan pipeline segment, 2 hops"
        >
          <Zap size={13} />
          Demo: Mangalore-Hassan
        </button>

        {/* Clear neighbourhood */}
        {neighbourhood && (
          <button
            type="button"
            onClick={clearNeighbourhood}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md border"
            style={{
              background: 'var(--color-bg-subtle)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
          >
            <X size={13} /> Full graph
          </button>
        )}

        {/* Search */}
        <div className="relative">
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="search"
            value={query}
            onChange={(e) => runSearch(e.target.value)}
            placeholder="Find node…"
            aria-label="Find node"
            className="pl-7 pr-2 py-1.5 text-xs rounded-md border outline-none"
            style={{
              background: 'var(--color-bg-subtle)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        {/* Label filter */}
        <select
          value={labelFilter}
          onChange={(e) => setLabelFilter(e.target.value)}
          aria-label="Filter by label"
          className="px-2 py-1.5 text-xs rounded-md border outline-none"
          style={{
            background: 'var(--color-bg-subtle)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text)',
          }}
        >
          <option value="">All labels ({data.nodes.length})</option>
          {labels.map((l) => <option key={l} value={l}>{l} ({counts[l]})</option>)}
        </select>

        <button
          type="button"
          onClick={() => setReheat((n) => n + 1)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md border"
          style={{
            background: 'var(--color-bg-subtle)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
          }}
        >
          <RefreshCw size={13} /> Re-run layout
        </button>

        <button
          type="button"
          onClick={() => setFullPage((v) => !v)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md border"
          style={{
            background: 'var(--color-bg-subtle)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
          }}
        >
          {fullPage ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          {fullPage ? 'Exit full page' : 'Full page'}
        </button>
      </header>

      {/* ── Canvas + Inspector ── */}
      <div className="flex-1 relative min-h-0">
        <ForceGraph
          nodes={graphNodes}
          relationships={graphEdges}
          height={fullPage ? window.innerHeight - 64 : 600}
          labelFilter={labelFilter}
          selectedId={selected?.id ?? null}
          onSelect={(body) => {
            setSelected(data.nodes.find((n) => n.id === body.id) || null)
          }}
          reheatToken={reheat}
          focusId={focusId}
          revealByDistance={revealedHops}
          highlightIds={highlightIds}
        />

        {/* Loading overlay for hop fetch */}
        {hopLoading && (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.18)' }}
          >
            <div
              className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium"
              style={{
                background: 'var(--color-bg-elevated, var(--color-bg))',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
              }}
            >
              <Spinner size={14} />
              Fetching neighbourhood…
            </div>
          </div>
        )}

        {/* ── Inspector panel ── */}
        <aside
          className="absolute top-3 right-3 w-72 max-h-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border p-3.5 text-sm"
          style={{
            background: 'var(--color-bg-elevated, var(--color-bg))',
            borderColor: 'var(--color-border)',
          }}
        >
          {!selected ? (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              Click any node to inspect it and explore its neighbourhood hop by hop.
            </p>
          ) : (
            <>
              {/* Node label badge */}
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold font-mono"
                style={{
                  background: `${getNodeColor(selected)}20`,
                  color: getNodeColor(selected),
                  border: `1px solid ${getNodeColor(selected)}55`,
                }}
              >
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getNodeColor(selected) }} />
                {selected.labels.join(' · ')}
              </span>

              <h2 className="mt-2 font-semibold break-words" style={{ color: 'var(--color-text)' }}>
                {nodeName(selected)}
              </h2>

              {/* Properties */}
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                {Object.entries(selected.properties || {})
                  .filter(([, v]) => v && v !== 'None')
                  .map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt style={{ color: 'var(--color-text-muted)' }}>{k}</dt>
                      <dd className="font-mono break-words" style={{ color: 'var(--color-text)' }}>{v}</dd>
                    </div>
                  ))}
              </dl>

              {/* Neighbourhood explore controls */}
              <div className="mt-3.5 pt-2.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <label className="text-[10px] uppercase tracking-wider"
                         style={{ color: 'var(--color-text-muted)' }}>
                    Hops
                  </label>
                  {[1, 2, 3].map((h) => (
                    <button
                      key={h}
                      type="button"
                      onClick={() => setHopCount(h)}
                      className="w-6 h-6 text-[11px] font-mono rounded border"
                      style={{
                        background: hopCount === h ? 'var(--color-accent)' : 'var(--color-bg-subtle)',
                        borderColor: hopCount === h ? 'var(--color-accent)' : 'var(--color-border)',
                        color: hopCount === h ? '#fff' : 'var(--color-text-muted)',
                      }}
                    >
                      {h}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => exploreNeighbourhood(selected.id, hopCount)}
                  disabled={hopLoading}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border"
                  style={{
                    background: 'var(--color-accent-soft, #f5ede8)',
                    borderColor: 'var(--color-accent)',
                    color: 'var(--color-accent)',
                    opacity: hopLoading ? 0.6 : 1,
                  }}
                >
                  <GitBranch size={12} />
                  Explore {hopCount}-hop neighbourhood
                </button>
              </div>

              {/* Hop histogram (shown when neighbourhood is loaded) */}
              {neighbourhood && (
                <div className="mt-3 pt-2.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
                  <h3 className="text-[10px] uppercase tracking-wider mb-1.5"
                      style={{ color: 'var(--color-text-muted)' }}>
                    Hop distribution
                  </h3>
                  <div className="flex gap-2 flex-wrap">
                    {Object.entries(neighbourhood.by_distance)
                      .sort(([a], [b]) => Number(a) - Number(b))
                      .map(([d, n]) => {
                        const distNum = Number(d)
                        const revealed = revealedHops?.has(distNum) ?? true
                        return (
                          <span
                            key={d}
                            className="font-mono text-[11px] px-2 py-0.5 rounded border transition-opacity duration-300"
                            style={{
                              background: 'var(--color-bg-subtle)',
                              borderColor: 'var(--color-border)',
                              color: 'var(--color-text-muted)',
                              opacity: revealed ? 1 : 0.3,
                            }}
                          >
                            +{d}: <b style={{ color: 'var(--color-text)' }}>{n}</b>
                          </span>
                        )
                      })}
                  </div>
                  <p className="mt-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                    Source: {neighbourhood.source}
                  </p>
                </div>
              )}

              {/* Centrality (shown when available) */}
              {Object.keys(centrality).length > 0 && selected && centrality[selected.id] && (
                <div className="mt-3 pt-2.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
                  <h3 className="text-[10px] uppercase tracking-wider mb-1.5 flex items-center gap-1.5"
                      style={{ color: 'var(--color-text-muted)' }}>
                    <Sparkles size={10} /> NetworkX centrality
                  </h3>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs font-mono">
                    {Object.entries(centrality[selected.id]).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt style={{ color: 'var(--color-text-muted)' }}>{k}</dt>
                        <dd style={{ color: 'var(--color-text)' }}>
                          {typeof v === 'number' ? v.toFixed(4) : v}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              {/* Relationships */}
              <div className="mt-3.5 pt-2.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
                <h3 className="text-[10px] uppercase tracking-wider mb-1.5"
                    style={{ color: 'var(--color-text-muted)' }}>
                  Relationships ({attachedEdges.length})
                </h3>
                {attachedEdges.length === 0 ? (
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    None — isolated node.
                  </p>
                ) : attachedEdges.map((e, i) => (
                  <div
                    key={i}
                    className="font-mono text-[11px] py-1 border-b"
                    style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
                  >
                    {e.outgoing ? '→ ' : '← '}
                    <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
                      {e.type}
                    </span>{' '}
                    {e.name}
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
