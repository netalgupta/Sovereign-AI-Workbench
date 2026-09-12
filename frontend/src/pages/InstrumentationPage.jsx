import { useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, CheckCircle2, FolderSearch, GitMerge,
  Image as ImageIcon, Layers, Network, Radio, Scatter3D, Upload, Wifi, WifiOff,
} from 'lucide-react'
import { api } from '../lib/pipelineApi'
import { ForceGraph } from '../components/graph/ForceGraph'
import { nodeName, getNodeColor } from '../components/graph/graphTheme'
import { VectorScatter, SimilarityHeatmap } from '../components/graph/VectorViews'
import { Spinner } from '../components/ui/Spinner'
import { AgentStreamView } from '../components/stream/AgentStreamView'
import { useAgentStream } from '../components/stream/useAgentStream'

/**
 * InstrumentationPage — everything happening inside the pipeline, in one place.
 *
 * Named for the refinery sense of the word: the panel an operator reads
 * to see what the process is actually doing, rather than what it was
 * supposed to do. The tabs answer the questions an engineer asks when an
 * answer looks wrong, in the order they usually ask them:
 *
 *   Overview — is anything measurably broken right now?
 *   Graph    — what entities and relationships exist, and of what TYPE?
 *   Vectors  — do these chunks sit where I would expect in embedding space?
 *   Chunks   — what text did the retriever actually see?
 *   Images   — what did we understand from each picture, and can I trust it?
 *   Sources  — where did all of this come from, and what is still queued?
 *
 * Every panel states its own provenance (live API vs exported snapshot).
 * A dashboard that presents a stale export as current data is the same
 * failure as a citation pointing at a document that has since changed.
 */

const TABS = [
  ['overview', 'Overview', Activity],
  ['graph', 'Graph', Network],
  ['vectors', 'Vectors', Scatter3D],
  ['chunks', 'Chunks', Layers],
  ['images', 'Images', ImageIcon],
  ['sources', 'Sources', FolderSearch],
  ['stream', 'Agent Stream', Radio],
  ['retrieval', 'Retrieval Trace', GitMerge],
  ['ingestion', 'Ingestion', Upload],
]

function Stat({ label, value, sub, tone }) {
  const toneColor =
    tone === 'bad' ? 'var(--color-danger, #a63927)'
      : tone === 'warn' ? 'var(--color-warning, #a8760f)'
      : tone === 'good' ? 'var(--color-success, #2f7a52)'
      : 'var(--color-text)'
  return (
    <div className="p-3" style={{ background: 'var(--color-bg)' }}>
      <div className="text-[10px] uppercase tracking-wider font-semibold"
           style={{ color: 'var(--color-text-muted)' }}>{label}</div>
      <div className="font-mono text-xl font-semibold tabular-nums mt-0.5" style={{ color: toneColor }}>
        {value}
        {sub && <span className="text-[11px] font-medium ml-1"
                      style={{ color: 'var(--color-text-muted)' }}>{sub}</span>}
      </div>
    </div>
  )
}

function StatStrip({ children }) {
  return (
    <div className="grid gap-px rounded-lg overflow-hidden border mb-5"
         style={{
           background: 'var(--color-border)',
           borderColor: 'var(--color-border)',
           gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
         }}>
      {children}
    </div>
  )
}

function Provenance({ source, warning }) {
  const live = source === 'live' || source === 'api'
  return (
    <div className="flex items-center gap-2 text-[11px] mb-3"
         style={{ color: 'var(--color-text-muted)' }}>
      {live ? <Wifi size={12} /> : <WifiOff size={12} />}
      <span>
        {live ? 'Live from the backend' :
         source === 'snapshot' ? 'Exported snapshot — backend not reachable, or no live data' :
         'Unavailable'}
      </span>
      {warning && (
        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded"
              style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-warning, #a8760f)' }}>
          <AlertTriangle size={11} /> {warning}
        </span>
      )}
    </div>
  )
}

export function InstrumentationPage() {
  const [tab, setTab] = useState('overview')
  const [graph, setGraph] = useState(null)
  const [chunks, setChunks] = useState(null)
  const [images, setImages] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [sources, setSources] = useState(null)
  const [health, setHealth] = useState(null)

  const [selectedNode, setSelectedNode] = useState(null)
  const [labelFilter, setLabelFilter] = useState('')
  const [selectedChunk, setSelectedChunk] = useState(0)
  const [selectedImage, setSelectedImage] = useState(null)
  const [chunkFilter, setChunkFilter] = useState('')
  const [newSourcePath, setNewSourcePath] = useState('')
  const [scanResult, setScanResult] = useState(null)

  // Agent Stream tab state
  const stream = useAgentStream()
  const [streamMessage, setStreamMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.graph(), api.chunks(), api.images(), api.metrics(), api.sources(), api.health(),
    ]).then(([g, c, i, m, s, h]) => {
      if (cancelled) return
      setGraph(g); setChunks(c); setImages(i); setMetrics(m); setSources(s); setHealth(h)
      const worst = i.images?.find((im) => im.scored?.fabricated_value_count > 0)
      setSelectedImage(worst?.filename ?? i.images?.[0]?.filename ?? i.images?.[0]?.image_id ?? null)
    })
    return () => { cancelled = true }
  }, [])

  const loading = !graph || !chunks || !images

  // Pull the headline numbers out of whichever harness produced them.
  const headline = useMemo(() => {
    const rm = metrics?.retrieval_metrics?.data
    const ceiling = metrics?.precision_ceiling?.data?.[0]
    const chart = metrics?.chart_stress?.data
    const refusal = metrics?.refusal?.data
    const relTotal = graph?.relationships?.length ?? 0
    return {
      mrr: rm?.MRR, map: rm?.MAP, recall: rm?.recall_at_k,
      rankedFirst: rm?.questions_ranked_first, questions: rm?.questions_scored,
      precision: ceiling?.raw_precision_at_k_fused,
      ceilingPct: ceiling?.fraction_of_achievable_fused,
      fabricated: chart?.total_fabricated_values,
      fabricatedCharts: chart?.unlabeled_charts_fabricating_values,
      unlabeledCharts: chart?.unlabeled_charts_total,
      refusedIn: refusal?.by_group?.in_scope?.refused,
      refusedInTotal: refusal?.by_group?.in_scope?.n,
      refusedOut:
        (refusal?.by_group?.off_domain?.refused ?? 0) + (refusal?.by_group?.unrelated?.refused ?? 0),
      refusedOutTotal:
        (refusal?.by_group?.off_domain?.n ?? 0) + (refusal?.by_group?.unrelated?.n ?? 0),
      nodes: graph?.nodes?.length ?? 0,
      relationships: relTotal,
      measuredAt: metrics?.retrieval_metrics?.measured_at,
    }
  }, [metrics, graph])

  const labels = useMemo(
    () => [...new Set((graph?.nodes ?? []).flatMap((n) => n.labels))].sort(),
    [graph],
  )

  const visibleChunks = useMemo(() => {
    const f = chunkFilter.toLowerCase()
    return (chunks?.chunks ?? []).filter(
      (c) => !f || c.text.toLowerCase().includes(f) || c.source_document.toLowerCase().includes(f),
    )
  }, [chunks, chunkFilter])

  const attachedEdges = useMemo(() => {
    if (!graph || !selectedNode) return []
    return graph.relationships
      .filter((r) => r.source === selectedNode.id || r.target === selectedNode.id)
      .map((r) => {
        const otherId = r.source === selectedNode.id ? r.target : r.source
        const other = graph.nodes.find((n) => n.id === otherId)
        return { type: r.type, outgoing: r.source === selectedNode.id,
                 name: other ? nodeName(other) : otherId }
      })
  }, [graph, selectedNode])

  const image = (images?.images ?? []).find(
    (i) => (i.filename ?? i.image_id) === selectedImage,
  )

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
        <Spinner />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0" style={{ background: 'var(--color-bg)' }}>
      <header className="px-5 pt-4 pb-0 border-b" style={{ borderColor: 'var(--color-border)' }}>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            Instrumentation
          </h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            What the pipeline is actually doing — every figure here was measured, not asserted.
          </p>
          {health && (
            <span className="ml-auto text-[11px] font-mono flex items-center gap-1.5"
                  style={{ color: health.graph_available ? 'var(--color-success, #2f7a52)' : 'var(--color-warning, #a8760f)' }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'currentColor' }} />
              backend up · graph {health.graph_available ? 'connected' : 'down'}
            </span>
          )}
        </div>
        <nav className="flex gap-1 mt-3 -mb-px overflow-x-auto">
          {TABS.map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap"
              style={{
                color: tab === id ? 'var(--color-accent)' : 'var(--color-text-muted)',
                borderBottom: `2px solid ${tab === id ? 'var(--color-accent)' : 'transparent'}`,
              }}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex-1 overflow-y-auto p-5 min-h-0">
        {tab === 'overview' && (
          <>
            <Provenance source={graph.source} />
            <StatStrip>
              <Stat label="MRR" value={headline.mrr?.toFixed(3) ?? '—'}
                    sub={`${headline.rankedFirst ?? '?'}/${headline.questions ?? '?'} first`}
                    tone={headline.mrr >= 0.9 ? 'good' : 'warn'} />
              <Stat label="MAP" value={headline.map?.toFixed(3) ?? '—'} tone="warn" />
              <Stat label="Recall@5" value={headline.recall?.toFixed(3) ?? '—'} sub="saturated" tone="good" />
              <Stat label="Precision@5" value={headline.precision?.toFixed(3) ?? '—'}
                    sub={headline.ceilingPct ? `${(headline.ceilingPct * 100).toFixed(0)}% of ceiling` : ''}
                    tone="good" />
              <Stat label="Fabricated values" value={headline.fabricated ?? '—'}
                    sub={`in ${headline.fabricatedCharts ?? 0}/${headline.unlabeledCharts ?? 0} charts`}
                    tone={headline.fabricated > 0 ? 'bad' : 'good'} />
              <Stat label="Graph" value={headline.nodes} sub={`${headline.relationships} edges`} />
            </StatStrip>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="rounded-lg border p-4" style={{ borderColor: 'var(--color-border)' }}>
                <h2 className="text-xs font-semibold uppercase tracking-wider mb-2"
                    style={{ color: 'var(--color-text-muted)' }}>Grounding (NFR-4)</h2>
                <p className="text-xs leading-relaxed mb-3" style={{ color: 'var(--color-text)' }}>
                  The confidence gate refuses questions the corpus cannot answer. It was
                  measured refusing <b>0 of 16</b> before being fixed — every question passed,
                  including ones about Pride and Prejudice.
                </p>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider"
                         style={{ color: 'var(--color-text-muted)' }}>False refusals</div>
                    <div className="font-mono text-lg font-semibold"
                         style={{ color: 'var(--color-success, #2f7a52)' }}>
                      {headline.refusedIn ?? '—'}/{headline.refusedInTotal ?? '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider"
                         style={{ color: 'var(--color-text-muted)' }}>Out-of-scope refused</div>
                    <div className="font-mono text-lg font-semibold"
                         style={{ color: 'var(--color-success, #2f7a52)' }}>
                      {headline.refusedOut ?? '—'}/{headline.refusedOutTotal ?? '—'}
                    </div>
                  </div>
                </div>
              </section>

              <section className="rounded-lg border p-4" style={{ borderColor: 'var(--color-border)' }}>
                <h2 className="text-xs font-semibold uppercase tracking-wider mb-2"
                    style={{ color: 'var(--color-text-muted)' }}>Chart reading (hard constraint #3)</h2>
                {headline.fabricated > 0 ? (
                  <p className="flex gap-2 text-xs leading-relaxed p-2.5 rounded-r"
                     style={{ borderLeft: '3px solid var(--color-danger, #a63927)',
                              background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                    <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                    <span>
                      <b>{headline.fabricated} invented values</b> across {headline.fabricatedCharts} of{' '}
                      {headline.unlabeledCharts} charts carrying no printed numbers. The model stated
                      figures and described them as "printed as text on the chart". Every chart reading
                      in this system is an estimate and is labelled as one.
                    </span>
                  </p>
                ) : (
                  <p className="flex gap-2 text-xs" style={{ color: 'var(--color-text)' }}>
                    <CheckCircle2 size={15} /> No invented values measured.
                  </p>
                )}
              </section>
            </div>

            {headline.measuredAt && (
              <p className="text-[11px] mt-4" style={{ color: 'var(--color-text-muted)' }}>
                Retrieval metrics measured {headline.measuredAt}. Figures are read from the
                evaluation harnesses on every load, so a superseded number is never shown.
              </p>
            )}
          </>
        )}

        {tab === 'graph' && (
          <>
            <Provenance source={graph.source} warning={graph.warning} />
            <div className="flex gap-2 mb-3 flex-wrap">
              <select value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)}
                      aria-label="Filter by label"
                      className="px-2 py-1.5 text-xs rounded-md border outline-none"
                      style={{ background: 'var(--color-bg-subtle)', borderColor: 'var(--color-border)',
                               color: 'var(--color-text)' }}>
                <option value="">All labels ({graph.nodes.length})</option>
                {labels.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </div>
            <div className="grid gap-4 lg:grid-cols-[1fr_300px] items-start">
              <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
                <ForceGraph nodes={graph.nodes} relationships={graph.relationships} height={520}
                            labelFilter={labelFilter} selectedId={selectedNode?.id ?? null}
                            onSelect={(b) => setSelectedNode(graph.nodes.find((n) => n.id === b.id) ?? null)} />
              </div>
              <aside className="rounded-lg border p-3.5 text-sm" style={{ borderColor: 'var(--color-border)' }}>
                {!selectedNode ? (
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    Click a node to see everything stored on it and every relationship attached,
                    with its TYPE — GRAPH_SPEC §8 separates REFERENCES (mentioned) from
                    APPLIES_TO (in scope), and that difference is invisible on an unlabelled line.
                  </p>
                ) : (
                  <>
                    <div className="font-semibold break-words" style={{ color: 'var(--color-text)' }}>
                      {nodeName(selectedNode)}
                    </div>
                    <div className="flex flex-wrap gap-1.5 my-2">
                      {selectedNode.labels.map((lbl) => {
                        const col = getNodeColor({ labels: [lbl] })
                        return (
                          <span
                            key={lbl}
                            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold font-mono"
                            style={{
                              background: `${col}20`,
                              color: col,
                              border: `1px solid ${col}55`,
                            }}
                          >
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: col }} />
                            {lbl}
                          </span>
                        )
                      })}
                    </div>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                      {Object.entries(selectedNode.properties ?? {})
                        .filter(([, v]) => v && v !== 'None')
                        .map(([k, v]) => (
                          <div key={k} className="contents">
                            <dt style={{ color: 'var(--color-text-muted)' }}>{k}</dt>
                            <dd className="font-mono break-words" style={{ color: 'var(--color-text)' }}>{v}</dd>
                          </div>
                        ))}
                    </dl>
                    <h3 className="text-[10px] uppercase tracking-wider mt-3 mb-1"
                        style={{ color: 'var(--color-text-muted)' }}>
                      Relationships ({attachedEdges.length})
                    </h3>
                    {attachedEdges.map((e, i) => (
                      <div key={i} className="font-mono text-[11px] py-1 border-b"
                           style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                        {e.outgoing ? '→ ' : '← '}
                        <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>{e.type}</span>{' '}
                        {e.name}
                      </div>
                    ))}
                  </>
                )}
              </aside>
            </div>
          </>
        )}

        {tab === 'vectors' && (
          <>
            <Provenance source={chunks.source} />
            <StatStrip>
              <Stat label="Vectors" value={chunks.chunks.length} />
              <Stat label="Dimensions" value={chunks.embeddingDim ?? '—'} />
              <Stat label="PCA variance"
                    value={`${((chunks.pcaExplained ?? []).reduce((a, b) => a + b, 0) * 100).toFixed(1)}%`}
                    sub="in 2D" />
              <Stat label="Metric" value="cosine" />
            </StatStrip>
            <div className="grid gap-4 lg:grid-cols-2 items-start">
              <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)' }}>
                <h3 className="text-[10px] uppercase tracking-wider mb-2"
                    style={{ color: 'var(--color-text-muted)' }}>PCA projection</h3>
                <VectorScatter chunks={chunks.chunks} pcaExplained={chunks.pcaExplained} />
              </div>
              <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)' }}>
                <h3 className="text-[10px] uppercase tracking-wider mb-2"
                    style={{ color: 'var(--color-text-muted)' }}>Cosine similarity</h3>
                <SimilarityHeatmap similarity={chunks.similarity} chunks={chunks.chunks} />
              </div>
            </div>
          </>
        )}

        {tab === 'chunks' && (
          <>
            <Provenance source={chunks.source} />
            <StatStrip>
              <Stat label="Chunks" value={chunks.chunks.length} />
              <Stat label="Documents"
                    value={new Set(chunks.chunks.map((c) => c.source_document)).size} />
              <Stat label="Chunk size" value={chunks.chunking?.chunk_size_tokens ?? '—'} sub="tok" />
              <Stat label="Overlap" value={chunks.chunking?.chunk_overlap_tokens ?? '—'} sub="tok" />
            </StatStrip>
            <input type="search" value={chunkFilter} onChange={(e) => setChunkFilter(e.target.value)}
                   placeholder="Filter chunks…" aria-label="Filter chunks"
                   className="w-full max-w-sm mb-3 px-2.5 py-1.5 text-xs rounded-md border outline-none"
                   style={{ background: 'var(--color-bg-subtle)', borderColor: 'var(--color-border)',
                            color: 'var(--color-text)' }} />
            <div className="grid gap-4 lg:grid-cols-[300px_1fr] items-start">
              <ul className="rounded-lg border p-2 max-h-[480px] overflow-y-auto space-y-1"
                  style={{ borderColor: 'var(--color-border)' }}>
                {visibleChunks.map((c) => (
                  <li key={c.index}>
                    <button type="button" onClick={() => setSelectedChunk(c.index)}
                            className="w-full text-left px-2.5 py-2 rounded-md border"
                            style={{
                              background: c.index === selectedChunk
                                ? 'var(--color-accent-soft, var(--color-bg-subtle))' : 'transparent',
                              borderColor: c.index === selectedChunk ? 'var(--color-accent)' : 'transparent',
                            }}>
                      <div className="flex justify-between gap-2 items-baseline">
                        <span className="text-xs font-semibold truncate"
                              style={{ color: 'var(--color-text)' }}>{c.source_document}</span>
                        <span className="font-mono text-[10px]"
                              style={{ color: 'var(--color-text-muted)' }}>#{c.chunk_index}</span>
                      </div>
                      <p className="text-[11px] mt-1 line-clamp-2"
                         style={{ color: 'var(--color-text-muted)' }}>{c.text.slice(0, 110)}</p>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="rounded-lg border p-4" style={{ borderColor: 'var(--color-border)' }}>
                <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words p-3 rounded max-h-80 overflow-y-auto"
                     style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                  {chunks.chunks[selectedChunk]?.text}
                </pre>
                <h3 className="text-[10px] uppercase tracking-wider mt-4 mb-1"
                    style={{ color: 'var(--color-text-muted)' }}>Nearest neighbours</h3>
                {(chunks.similarity[selectedChunk] ?? [])
                  .map((v, i) => ({ v, i })).filter((o) => o.i !== selectedChunk)
                  .sort((a, b) => b.v - a.v).slice(0, 5)
                  .map((o) => (
                    <div key={o.i} className="font-mono text-[11px] py-1 border-b"
                         style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                      <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
                        {o.v.toFixed(3)}
                      </span>{' '}
                      {chunks.chunks[o.i]?.source_document} · #{chunks.chunks[o.i]?.chunk_index}
                    </div>
                  ))}
              </div>
            </div>
          </>
        )}

        {tab === 'images' && (
          <>
            <Provenance source={images.source} />
            <StatStrip>
              <Stat label="Images" value={images.images.length} />
              <Stat label="With OCR" value={images.images.filter((i) => i.ocr_text).length} />
              <Stat label="With reading"
                    value={images.images.filter((i) => i.description || i.vision_description).length} />
              <Stat label="Invented values"
                    value={images.images.reduce((a, i) => a + (i.scored?.fabricated_value_count ?? 0), 0)}
                    tone="bad" />
            </StatStrip>
            <div className="grid gap-3 mb-5"
                 style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
              {images.images.map((im) => {
                const key = im.filename ?? im.image_id
                return (
                  <button key={key} type="button" onClick={() => setSelectedImage(key)}
                          className="text-left rounded-lg border overflow-hidden"
                          style={{ borderColor: key === selectedImage
                                     ? 'var(--color-accent)' : 'var(--color-border)',
                                   background: 'var(--color-bg-subtle)' }}>
                    <img src={api.imageSrc(im)} alt={key} loading="lazy"
                         className="w-full h-24 object-cover object-top bg-white" />
                    <div className="p-2">
                      <p className="text-[11px] font-semibold truncate"
                         style={{ color: 'var(--color-text)' }}>{key}</p>
                      {im.scored?.fabricated_value_count > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold text-white mt-1 inline-block"
                              style={{ background: 'var(--color-danger, #a63927)' }}>
                          {im.scored.fabricated_value_count} INVENTED
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
            {image && (
              <div className="rounded-lg border p-4 grid gap-5 lg:grid-cols-2"
                   style={{ borderColor: 'var(--color-border)' }}>
                <img src={api.imageSrc(image)} alt={selectedImage}
                     className="w-full rounded border bg-white" style={{ borderColor: 'var(--color-border)' }} />
                <div className="min-w-0">
                  {(image.description ?? image.vision_description) && (
                    <>
                      <h3 className="text-[10px] uppercase tracking-wider mb-1.5 flex items-center gap-2"
                          style={{ color: 'var(--color-text-muted)' }}>
                        Chart reading
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold"
                              style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-accent)' }}>
                          ESTIMATE
                        </span>
                      </h3>
                      <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded max-h-56 overflow-y-auto mb-4"
                           style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                        {(image.description ?? image.vision_description).trim()}
                      </pre>
                    </>
                  )}
                  {image.ocr_text && (
                    <>
                      <h3 className="text-[10px] uppercase tracking-wider mb-1.5"
                          style={{ color: 'var(--color-text-muted)' }}>
                        OCR text — indexed into the corpus
                      </h3>
                      <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded max-h-56 overflow-y-auto"
                           style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                        {image.ocr_text.trim()}
                      </pre>
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {tab === 'sources' && (
          <>
            <Provenance source={sources ? 'live' : 'unavailable'} />
            <StatStrip>
              <Stat label="Watched folders" value={sources?.watched?.length ?? 0} />
              <Stat label="Documents" value={sources?.documents?.length ?? 0} />
              <Stat label="Queued" value={sources?.queue?.pending ?? 0} />
              <Stat label="Failed" value={sources?.queue?.failed ?? 0}
                    tone={sources?.queue?.failed ? 'bad' : 'good'} />
            </StatStrip>

            <div className="rounded-lg border p-4 mb-4" style={{ borderColor: 'var(--color-border)' }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-1"
                  style={{ color: 'var(--color-text-muted)' }}>Watch a folder</h3>
              <p className="text-xs mb-3" style={{ color: 'var(--color-text-muted)' }}>
                Your files stay where they are — only the path is recorded. Anything ingestible
                that appears there is picked up, newest first.
              </p>
              <div className="flex gap-2 flex-wrap">
                <input value={newSourcePath} onChange={(e) => setNewSourcePath(e.target.value)}
                       placeholder="C:\Users\you\Downloads" aria-label="Folder to watch"
                       className="flex-1 min-w-56 px-2.5 py-1.5 text-xs font-mono rounded-md border outline-none"
                       style={{ background: 'var(--color-bg-subtle)', borderColor: 'var(--color-border)',
                                color: 'var(--color-text)' }} />
                <button type="button"
                        onClick={() => api.addSource(newSourcePath)
                          .then(() => api.sources()).then(setSources).catch(() => {})}
                        className="px-3 py-1.5 text-xs font-medium rounded-md border"
                        style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)' }}>
                  Watch
                </button>
                <button type="button"
                        onClick={() => api.scanSources().then((r) => {
                          setScanResult(r); return api.sources()
                        }).then(setSources).catch(() => {})}
                        className="px-3 py-1.5 text-xs font-medium rounded-md border"
                        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                  Scan now
                </button>
              </div>
              {scanResult && (
                <p className="text-xs mt-2" style={{ color: 'var(--color-text)' }}>
                  Found {scanResult.found}, queued {scanResult.queued}.
                </p>
              )}
            </div>

            <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    {['Document', 'Pages', 'Size', 'Registered'].map((h) => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold"
                          style={{ color: 'var(--color-text-muted)',
                                   borderBottom: '1px solid var(--color-border)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(sources?.documents ?? []).slice(0, 40).map((d) => (
                    <tr key={d.document_id}>
                      <td className="px-3 py-1.5 font-mono truncate max-w-xs"
                          style={{ color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)' }}
                          title={d.source_path}>{d.original_name}</td>
                      <td className="px-3 py-1.5 font-mono tabular-nums"
                          style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                        {d.page_count ?? '—'}
                      </td>
                      <td className="px-3 py-1.5 font-mono tabular-nums"
                          style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                         {(d.byte_size / 1024).toFixed(0)} KB
                       </td>
                       <td className="px-3 py-1.5 font-mono"
                           style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                         {d.registered_on}
                       </td>
                     </tr>
                   ))}
                 </tbody>
               </table>
             </div>
           </>
         )}

        {tab === 'stream' && (
          <div className="flex flex-col min-h-0" style={{ height: 'calc(100vh - 160px)' }}>
            <Provenance source="live" warning="Requires backend at /api/chat/stream" />
            <p className="text-xs mb-3 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              Send a message to watch the agent reason token-by-token, see every tool call
              with its <b style={{ color: 'var(--color-text)' }}>exact arguments</b> (a safety
              control — shown before execution so you can catch a wrong input), and
              understand which retrieval path the router chose and why.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (streamMessage.trim()) {
                  stream.reset()
                  stream.start(streamMessage.trim())
                }
              }}
              className="flex gap-2 mb-4"
            >
              <input
                value={streamMessage}
                onChange={(e) => setStreamMessage(e.target.value)}
                placeholder="Ask anything grounded in the corpus…"
                className="flex-1 px-3 py-2 text-sm rounded-md border outline-none"
                style={{
                  background: 'var(--color-bg-subtle)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
              <button
                type="submit"
                disabled={stream.status === 'streaming' || !streamMessage.trim()}
                className="px-4 py-2 text-sm font-medium rounded-md border"
                style={{
                  background: 'var(--color-accent-soft, #f5ede8)',
                  borderColor: 'var(--color-accent)',
                  color: 'var(--color-accent)',
                  opacity: stream.status === 'streaming' || !streamMessage.trim() ? 0.6 : 1,
                }}
              >
                {stream.status === 'streaming' ? 'Working…' : 'Stream →'}
              </button>
              {stream.status !== 'idle' && (
                <button
                  type="button"
                 style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
              {images.images.map((im) => {
                const key = im.filename ?? im.image_id
                return (
                  <button key={key} type="button" onClick={() => setSelectedImage(key)}
                          className="text-left rounded-lg border overflow-hidden"
                          style={{ borderColor: key === selectedImage
                                     ? 'var(--color-accent)' : 'var(--color-border)',
                                   background: 'var(--color-bg-subtle)' }}>
                    <img src={api.imageSrc(im)} alt={key} loading="lazy"
                         className="w-full h-24 object-cover object-top bg-white" />
                    <div className="p-2">
                      <p className="text-[11px] font-semibold truncate"
                         style={{ color: 'var(--color-text)' }}>{key}</p>
                      {im.scored?.fabricated_value_count > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold text-white mt-1 inline-block"
                              style={{ background: 'var(--color-danger, #a63927)' }}>
                          {im.scored.fabricated_value_count} INVENTED
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
            {image && (
              <div className="rounded-lg border p-4 grid gap-5 lg:grid-cols-2"
                   style={{ borderColor: 'var(--color-border)' }}>
                <img src={api.imageSrc(image)} alt={selectedImage}
                     className="w-full rounded border bg-white" style={{ borderColor: 'var(--color-border)' }} />
                <div className="min-w-0">
                  {(image.description ?? image.vision_description) && (
                    <>
                      <h3 className="text-[10px] uppercase tracking-wider mb-1.5 flex items-center gap-2"
                          style={{ color: 'var(--color-text-muted)' }}>
                        Chart reading
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold"
                              style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-accent)' }}>
                          ESTIMATE
                        </span>
                      </h3>
                      <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded max-h-56 overflow-y-auto mb-4"
                           style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                        {(image.description ?? image.vision_description).trim()}
                      </pre>
                    </>
                  )}
                  {image.ocr_text && (
                    <>
                      <h3 className="text-[10px] uppercase tracking-wider mb-1.5"
                          style={{ color: 'var(--color-text-muted)' }}>
                        OCR text — indexed into the corpus
                      </h3>
                      <pre className="font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-words p-3 rounded max-h-56 overflow-y-auto"
                           style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
                        {image.ocr_text.trim()}
                      </pre>
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {tab === 'sources' && (
          <>
            <Provenance source={sources ? 'live' : 'unavailable'} />
            <StatStrip>
              <Stat label="Watched folders" value={sources?.watched?.length ?? 0} />
              <Stat label="Documents" value={sources?.documents?.length ?? 0} />
              <Stat label="Queued" value={sources?.queue?.pending ?? 0} />
              <Stat label="Failed" value={sources?.queue?.failed ?? 0}
                    tone={sources?.queue?.failed ? 'bad' : 'good'} />
            </StatStrip>

            <div className="rounded-lg border p-4 mb-4" style={{ borderColor: 'var(--color-border)' }}>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-1"
                  style={{ color: 'var(--color-text-muted)' }}>Watch a folder</h3>
              <p className="text-xs mb-3" style={{ color: 'var(--color-text-muted)' }}>
                Your files stay where they are — only the path is recorded. Anything ingestible
                that appears there is picked up, newest first.
              </p>
              <div className="flex gap-2 flex-wrap">
                <input value={newSourcePath} onChange={(e) => setNewSourcePath(e.target.value)}
                       placeholder="C:\Users\you\Downloads" aria-label="Folder to watch"
                       className="flex-1 min-w-56 px-2.5 py-1.5 text-xs font-mono rounded-md border outline-none"
                       style={{ background: 'var(--color-bg-subtle)', borderColor: 'var(--color-border)',
                                color: 'var(--color-text)' }} />
                <button type="button"
                        onClick={() => api.addSource(newSourcePath)
                          .then(() => api.sources()).then(setSources).catch(() => {})}
                        className="px-3 py-1.5 text-xs font-medium rounded-md border"
                        style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)' }}>
                  Watch
                </button>
                <button type="button"
                        onClick={() => api.scanSources().then((r) => {
                          setScanResult(r); return api.sources()
                        }).then(setSources).catch(() => {})}
                        className="px-3 py-1.5 text-xs font-medium rounded-md border"
                        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                  Scan now
                </button>
              </div>
              {scanResult && (
                <p className="text-xs mt-2" style={{ color: 'var(--color-text)' }}>
                  Found {scanResult.found}, queued {scanResult.queued}.
                </p>
              )}
            </div>

            <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    {['Document', 'Pages', 'Size', 'Registered'].map((h) => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold"
                          style={{ color: 'var(--color-text-muted)',
                                   borderBottom: '1px solid var(--color-border)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(sources?.documents ?? []).slice(0, 40).map((d) => (
                    <tr key={d.document_id}>
                      <td className="px-3 py-1.5 font-mono truncate max-w-xs"
                          style={{ color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)' }}
                          title={d.source_path}>{d.original_name}</td>
                      <td className="px-3 py-1.5 font-mono tabular-nums"
                          style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                        {d.page_count ?? '—'}
                      </td>
                      <td className="px-3 py-1.5 font-mono tabular-nums"
                          style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                         {(d.byte_size / 1024).toFixed(0)} KB
                       </td>
                       <td className="px-3 py-1.5 font-mono"
                           style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                         {d.registered_on}
                       </td>
                     </tr>
                   ))}
                 </tbody>
               </table>
             </div>
           </>
         )}

        {tab === 'stream' && (
          <div className="flex flex-col min-h-0" style={{ height: 'calc(100vh - 160px)' }}>
            <Provenance source="live" warning="Requires backend at /api/chat/stream" />
            <p className="text-xs mb-3 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              Send a message to watch the agent reason token-by-token, see every tool call
              with its <b style={{ color: 'var(--color-text)' }}>exact arguments</b> (a safety
              control — shown before execution so you can catch a wrong input), and
              understand which retrieval path the router chose and why.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (streamMessage.trim()) {
                  stream.reset()
                  stream.start(streamMessage.trim())
                }
              }}
              className="flex gap-2 mb-4"
            >
              <input
                value={streamMessage}
                onChange={(e) => setStreamMessage(e.target.value)}
                placeholder="Ask anything grounded in the corpus…"
                className="flex-1 px-3 py-2 text-sm rounded-md border outline-none"
                style={{
                  background: 'var(--color-bg-subtle)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }}
              />
              <button
                type="submit"
                disabled={stream.status === 'streaming' || !streamMessage.trim()}
                className="px-4 py-2 text-sm font-medium rounded-md border"
                style={{
                  background: 'var(--color-accent-soft, #f5ede8)',
                  borderColor: 'var(--color-accent)',
                  color: 'var(--color-accent)',
                  opacity: stream.status === 'streaming' || !streamMessage.trim() ? 0.6 : 1,
                }}
              >
                {stream.status === 'streaming' ? 'Working…' : 'Stream →'}
              </button>
              {stream.status !== 'idle' && (
                <button
                  type="button"
                  onClick={stream.reset}
                  className="px-3 py-2 text-sm rounded-md border"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
                >
                  Clear
                </button>
              )}
            </form>
            <div
              className="flex-1 rounded-lg border overflow-hidden min-h-0"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <AgentStreamView
                events={stream.events}
                narration={stream.narration}
                route={stream.route}
                status={stream.status}
                error={stream.error}
              />
            </div>
          </div>
        )}

        {/* ── Retrieval Trace Tab ── */}
        {tab === 'retrieval' && (
          <RetrievalTraceTab />
        )}

        {/* ── Ingestion Progress Tab ── */}
        {tab === 'ingestion' && (
          <IngestionTab sources={sources} onRefresh={() => api.sources().then(setSources).catch(() => {})} />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RetrievalTraceTab — shows per-query retrieval trace from /api/retrieval/trace
// ---------------------------------------------------------------------------
function RetrievalTraceTab() {
  const [query, setQuery] = useState('')
  const [trace, setTrace] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runTrace = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setTrace(null)
    try {
      const res = await fetch(`/api/retrieval/trace?q=${encodeURIComponent(query.trim())}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setTrace(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <Provenance source="live" warning="Requires backend at /api/retrieval/trace" />
      <p className="text-xs mb-3 leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
        Run a retrieval query and see the exact scores — dense (FAISS cosine), sparse (BM25),
        and fused (RRF k=60) — for every candidate chunk. Explains why a particular chunk
        ranked first, and shows whether the confidence gate would accept or refuse the result.
      </p>
      <form onSubmit={runTrace} className="flex gap-2 mb-5">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What is the WABT end-of-run trigger?"
          className="flex-1 px-3 py-2 text-sm rounded-md border outline-none"
          style={{
            background: 'var(--color-bg-subtle)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text)',
          }}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-4 py-2 text-sm font-medium rounded-md border"
          style={{
            background: 'var(--color-accent-soft, #f5ede8)',
            borderColor: 'var(--color-accent)',
            color: 'var(--color-accent)',
            opacity: loading || !query.trim() ? 0.6 : 1,
          }}
        >
          {loading ? 'Tracing…' : 'Trace →'}
        </button>
      </form>

      {error && (
        <div
          className="text-sm p-3 rounded-lg mb-4"
          style={{ borderLeft: '3px solid var(--color-danger, #a63927)', background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}
        >
          {error} — backend may not be running or /api/retrieval/trace may not exist yet.
        </div>
      )}

      {trace && (
        <>
          <div className="flex gap-3 mb-4 flex-wrap text-xs">
            {[
              ['Route', trace.route],
              ['Top score', trace.top_score?.toFixed(3)],
              ['Gate', trace.gate_passed ? '✓ passed' : '✗ refused'],
              ['Candidates', trace.candidates?.length],
            ].map(([k, v]) => v != null && (
              <span
                key={k}
                className="font-mono px-2 py-0.5 rounded border"
                style={{
                  background: 'var(--color-bg-subtle)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {k}: <b style={{ color: 'var(--color-text)' }}>{v}</b>
              </span>
            ))}
          </div>

          {trace.route_reason && (
            <div className="text-xs mb-4 p-2.5 rounded-lg flex items-start gap-2"
                 style={{ background: 'var(--color-bg-subtle)', color: 'var(--color-text)' }}>
              <GitMerge size={12} style={{ flexShrink: 0, marginTop: 1, color: 'var(--color-accent)' }} />
              <span>Route reason: {trace.route_reason}</span>
            </div>
          )}

          <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
            <table className="w-full text-xs">
              <thead>
                <tr>
                  {['Rank', 'Document', 'Chunk', 'Dense', 'Sparse', 'Fused'].map((h) => (
                    <th
                      key={h}
                      className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold"
                      style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(trace.candidates ?? []).map((c, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-mono tabular-nums"
                        style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                      {i + 1}
                    </td>
                    <td className="px-3 py-2 max-w-[200px] truncate"
                        style={{ color: 'var(--color-text)', borderBottom: '1px solid var(--color-border)' }}
                        title={c.source_document}>
                      {c.source_document}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums"
                        style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                      #{c.chunk_index}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums"
                        style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                      {c.dense_score?.toFixed(3) ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums"
                        style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
                      {c.sparse_score?.toFixed(3) ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums font-semibold"
                        style={{
                          color: i === 0 ? 'var(--color-accent)' : 'var(--color-text)',
                          borderBottom: '1px solid var(--color-border)',
                        }}>
                      {c.fused_score?.toFixed(3) ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// IngestionTab — live ingestion queue with auto-refresh
// ---------------------------------------------------------------------------
function IngestionTab({ sources, onRefresh }) {
  const [ingestionLog, setIngestionLog] = useState(null)
  const [loadingLog, setLoadingLog] = useState(false)

  const fetchLog = async () => {
    setLoadingLog(true)
    try {
      const res = await fetch('/api/ingestion/log')
      if (res.ok) setIngestionLog(await res.json())
    } catch {
      // endpoint may not exist yet — that's ok
    } finally {
      setLoadingLog(false)
    }
  }

  const statusColor = (s) =>
    s === 'done' ? 'var(--color-success, #2f7a52)'
      : s === 'failed' ? 'var(--color-danger, #a63927)'
      : s === 'processing' ? 'var(--color-accent)'
      : 'var(--color-text-muted)'

  return (
    <div>
      <Provenance source={sources ? 'live' : 'unavailable'} />
      <StatStrip>
        <Stat label="Watched folders" value={sources?.watched?.length ?? 0} />
        <Stat label="Documents" value={sources?.documents?.length ?? 0} />
        <Stat label="Queued" value={sources?.queue?.pending ?? 0} />
        <Stat label="Processing" value={sources?.queue?.processing ?? 0} tone={sources?.queue?.processing > 0 ? 'warn' : undefined} />
        <Stat label="Failed" value={sources?.queue?.failed ?? 0} tone={sources?.queue?.failed ? 'bad' : 'good'} />
      </StatStrip>

      <div className="flex gap-2 mb-5">
        <button
          type="button"
          onClick={onRefresh}
          className="px-3 py-1.5 text-xs font-medium rounded-md border"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
        >
          <Upload size={12} className="inline mr-1" />
          Refresh queue
        </button>
        <button
          type="button"
          onClick={fetchLog}
          disabled={loadingLog}
          className="px-3 py-1.5 text-xs font-medium rounded-md border"
          style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)', opacity: loadingLog ? 0.6 : 1 }}
        >
          {loadingLog ? 'Loading…' : 'Load ingestion log'}
        </button>
      </div>

      {/* Queue table from /api/sources */}
      {sources?.queue?.items?.length > 0 && (
        <div className="rounded-lg border overflow-hidden mb-5" style={{ borderColor: 'var(--color-border)' }}>
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider font-semibold"
               style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
            Queue
          </div>
          {sources.queue.items.map((item, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-3 py-2 border-b text-xs"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: statusColor(item.status) }}
              />
              <span className="flex-1 font-mono truncate" style={{ color: 'var(--color-text)' }}>
                {item.filename ?? item.path ?? item.document_id}
              </span>
              <span className="font-mono text-[10px]" style={{ color: statusColor(item.status) }}>
                {item.status}
              </span>
              {item.error && (
                <span className="text-[10px] max-w-xs truncate"
                      style={{ color: 'var(--color-danger, #a63927)' }}
                      title={item.error}>
                  {item.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Ingestion log from /api/ingestion/log */}
      {ingestionLog && (
        <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider font-semibold"
               style={{ color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>
            Ingestion log ({ingestionLog.entries?.length ?? 0} entries)
          </div>
          {(ingestionLog.entries ?? []).slice(0, 50).map((entry, i) => (
            <div
              key={i}
              className="flex items-baseline gap-3 px-3 py-1.5 border-b font-mono text-[11px]"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <span style={{ color: 'var(--color-text-muted)', flexShrink: 0 }}>
                {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '—'}
              </span>
              <span
                className="font-semibold"
                style={{ color: statusColor(entry.status), flexShrink: 0 }}
              >
                {entry.status ?? entry.event}
              </span>
              <span className="truncate" style={{ color: 'var(--color-text)' }}>
                {entry.filename ?? entry.message ?? ''}
              </span>
              {entry.chunks_created != null && (
                <span style={{ color: 'var(--color-text-muted)', flexShrink: 0 }}>
                  +{entry.chunks_created} chunks
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {!ingestionLog && !sources?.queue?.items?.length && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          No items in queue. Add a source folder in the Sources tab to start ingesting.
        </p>
      )}
    </div>
  )
}
