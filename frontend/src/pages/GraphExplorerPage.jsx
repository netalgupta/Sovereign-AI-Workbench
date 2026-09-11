import { useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minimize2, RefreshCw, Search } from 'lucide-react'
import { ForceGraph, nodeName } from '../components/graph/ForceGraph'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import { Network } from 'lucide-react'

/**
 * GraphExplorerPage — the knowledge graph explorer (FRONTEND.md §2, /graph).
 *
 * Replaces GraphStubPage with a working viewer over the real Neo4j graph
 * built by backend/graph/. The graph answers questions plain retrieval
 * cannot ("which documents touch this pipeline segment?"), and GRAPH_SPEC
 * §8 draws a hard line between REFERENCES (merely mentioned) and APPLIES_TO
 * (explicitly in scope) — so the inspector shows the edge TYPE prominently
 * rather than just drawing an anonymous line. Reading an APPLIES_TO as a
 * REFERENCES, or the reverse, is the difference between "this SOP covers
 * this equipment" and "this SOP happens to name it".
 *
 * Data source: /pipeline/graph.json, a snapshot exported by
 * backend/evaluation/export_inspection_data.py. This is deliberately a
 * static asset for now rather than a live query — the backend graph
 * endpoint does not exist yet, and shipping a working explorer against a
 * real exported graph beats shipping a stub that waits for an API. Swap
 * the fetch URL when the endpoint lands; nothing else here changes.
 */
export function GraphExplorerPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [labelFilter, setLabelFilter] = useState('')
  const [query, setQuery] = useState('')
  const [focusId, setFocusId] = useState(null)
  const [fullPage, setFullPage] = useState(false)
  const [reheat, setReheat] = useState(0)
  const containerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    fetch('/pipeline/graph.json')
      .then((r) => {
        if (!r.ok) throw new Error(`graph.json returned ${r.status}`)
        return r.json()
      })
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setFullPage(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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

  const attachedEdges = useMemo(() => {
    if (!data || !selected) return []
    return data.relationships
      .filter((r) => r.source === selected.id || r.target === selected.id)
      .map((r) => {
        const otherId = r.source === selected.id ? r.target : r.source
        const other = data.nodes.find((n) => n.id === otherId)
        return {
          type: r.type,
          outgoing: r.source === selected.id,
          name: other ? nodeName(other) : otherId,
        }
      })
  }, [data, selected])

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

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <EmptyState
          icon={Network}
          title="Graph snapshot unavailable"
          description={`Could not load /pipeline/graph.json (${error}). Export it with: python -m backend.evaluation.export_inspection_data`}
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
      ref={containerRef}
      className={fullPage ? 'fixed inset-0 z-50 flex flex-col' : 'flex-1 flex flex-col min-h-0'}
      style={{ background: 'var(--color-bg)' }}
    >
      <header className="flex items-center gap-3 flex-wrap px-5 py-3 border-b"
              style={{ borderColor: 'var(--color-border)' }}>
        <div className="mr-auto">
          <h1 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            Knowledge graph
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {data.nodes.length} nodes · {data.relationships.length} relationships ·
            {' '}drag to move, scroll to zoom, click to inspect
          </p>
        </div>

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

      <div className="flex-1 relative min-h-0">
        <ForceGraph
          nodes={data.nodes}
          relationships={data.relationships}
          height={fullPage ? window.innerHeight - 64 : 600}
          labelFilter={labelFilter}
          selectedId={selected?.id ?? null}
          onSelect={(body) => {
            setSelected(data.nodes.find((n) => n.id === body.id) || null)
          }}
          reheatToken={reheat}
          focusId={focusId}
        />

        <aside
          className="absolute top-3 right-3 w-72 max-h-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border p-3.5 text-sm"
          style={{
            background: 'var(--color-bg-elevated, var(--color-bg))',
            borderColor: 'var(--color-border)',
          }}
        >
          {!selected ? (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              Click any node to see its labels, everything stored on it, and each
              relationship attached to it.
            </p>
          ) : (
            <>
              <span
                className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold text-white"
                style={{ background: `var(--graph-${selected.labels[0].toLowerCase()}, #888)` }}
              >
                {selected.labels.join(' · ')}
              </span>
              <h2 className="mt-2 font-semibold break-words" style={{ color: 'var(--color-text)' }}>
                {nodeName(selected)}
              </h2>

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
                  <div key={i} className="font-mono text-[11px] py-1 border-b"
                       style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
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
