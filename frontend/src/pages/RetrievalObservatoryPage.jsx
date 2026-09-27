import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Compass,
  Layers,
  Grid3X3,
  Search,
  ArrowRight,
  Database,
  FileText,
  Sparkles,
  BarChart2,
  Sliders,
  CheckCircle2,
} from 'lucide-react'
import { api } from '../lib/pipelineApi'
import { VectorScatter, SimilarityHeatmap } from '../components/graph/VectorViews'
import { springs, buttonTapMotion } from '../lib/motion'

export function RetrievalObservatoryPage() {
  const [activeTab, setActiveTab] = useState('scatter') // 'scatter' | 'heatmap' | 'chunks' | 'tester'
  const [chunksData, setChunksData] = useState(null)
  const [metricsData, setMetricsData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  // Query tester state
  const [testQuery, setTestQuery] = useState('')
  const [testResults, setTestResults] = useState(null)
  const [isSearching, setIsSearching] = useState(false)

  // Selected chunk state
  const [selectedChunk, setSelectedChunk] = useState(null)
  const [chunkFilter, setChunkFilter] = useState('')

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)

    Promise.allSettled([api.chunks(), api.metrics()])
      .then(([chunksRes, metricsRes]) => {
        if (cancelled) return
        if (chunksRes.status === 'fulfilled' && chunksRes.value) {
          setChunksData(chunksRes.value)
          if (chunksRes.value.chunks?.length > 0) {
            setSelectedChunk(chunksRes.value.chunks[0])
          }
        }
        if (metricsRes.status === 'fulfilled') {
          setMetricsData(metricsRes.value)
        }
      })
      .catch((e) => console.warn('Retrieval observatory load error:', e))
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const handleTestSearch = async (e) => {
    e.preventDefault()
    if (!testQuery.trim() || isSearching) return
    setIsSearching(true)
    try {
      const res = await api.search(testQuery.trim(), 5)
      setTestResults(res?.results || res || [])
    } catch (err) {
      console.warn('Search query error:', err)
    } finally {
      setIsSearching(false)
    }
  }

  const chunksList = chunksData?.chunks || []
  const filteredChunks = chunksList.filter((c) => {
    if (!chunkFilter.trim()) return true
    const q = chunkFilter.toLowerCase()
    return (
      (c.source_document || '').toLowerCase().includes(q) ||
      (c.text || '').toLowerCase().includes(q) ||
      String(c.chunk_id || '').includes(q)
    )
  })

  return (
    <div
      className="flex-1 flex flex-col h-full w-full overflow-hidden select-none"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Observatory Header ────────────────────────────────────────── */}
      <header
        className="h-12 px-6 border-b flex items-center justify-between flex-shrink-0"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center border"
            style={{
              background: 'var(--color-accent-tint)',
              borderColor: 'var(--color-accent-border)',
              color: 'var(--color-accent)',
            }}
          >
            <Compass size={14} strokeWidth={2.2} />
          </div>
          <div>
            <h1 className="text-xs font-bold leading-tight uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
              Retrieval Observatory
            </h1>
            <span className="text-[10px] text-[var(--color-text-muted)] font-mono leading-none">
              High-dimensional vector embeddings · PCA projections · RRF hybrid scoring
            </span>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-1 p-0.5 rounded-lg border bg-[var(--color-overlay)] text-xs font-medium" style={{ borderColor: 'var(--color-border)' }}>
          {[
            { id: 'scatter', label: '2D PCA Projection', icon: Grid3X3 },
            { id: 'heatmap', label: 'Similarity Matrix', icon: BarChart2 },
            { id: 'chunks', label: 'Chunk Registry', icon: Layers },
            { id: 'tester', label: 'Live Query Tester', icon: Search },
          ].map((t) => {
            const Icon = t.icon
            const isActive = activeTab === t.id
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-fast cursor-pointer ${
                  isActive
                    ? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow-xs font-semibold'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                <Icon size={12} strokeWidth={2} />
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            )
          })}
        </div>
      </header>

      {/* ── Main Observatory Body ───────────────────────────────────── */}
      <div className="flex-1 flex min-h-0 w-full overflow-hidden p-6">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center text-xs text-[var(--color-text-muted)]">
            Loading embedding space and chunk coordinates...
          </div>
        ) : (
          <div className="flex-1 flex flex-col h-full overflow-hidden max-w-6xl mx-auto w-full gap-4">
            {/* Top Stat Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-shrink-0">
              <div className="p-3.5 rounded-xl border bg-[var(--color-surface)] shadow-xs" style={{ borderColor: 'var(--color-border)' }}>
                <span className="text-[10px] font-mono text-[var(--color-text-muted)] uppercase tracking-wider block">
                  EMBEDDING MODEL
                </span>
                <span className="text-sm font-bold font-mono text-[var(--color-text)] mt-0.5 block truncate">
                  BAAI/bge-large-en-v1.5
                </span>
              </div>

              <div className="p-3.5 rounded-xl border bg-[var(--color-surface)] shadow-xs" style={{ borderColor: 'var(--color-border)' }}>
                <span className="text-[10px] font-mono text-[var(--color-text-muted)] uppercase tracking-wider block">
                  VECTOR DIMENSION
                </span>
                <span className="text-sm font-bold font-mono text-[var(--color-text)] mt-0.5 block">
                  {chunksData?.embeddingDim ? `${chunksData.embeddingDim} dims` : '—'}
                </span>
              </div>

              <div className="p-3.5 rounded-xl border bg-[var(--color-surface)] shadow-xs" style={{ borderColor: 'var(--color-border)' }}>
                <span className="text-[10px] font-mono text-[var(--color-text-muted)] uppercase tracking-wider block">
                  TOTAL CHUNKS
                </span>
                <span className="text-sm font-bold font-mono text-[var(--color-text)] mt-0.5 block">
                  {chunksList.length} indexed
                </span>
              </div>

              <div className="p-3.5 rounded-xl border bg-[var(--color-surface)] shadow-xs" style={{ borderColor: 'var(--color-border)' }}>
                <span className="text-[10px] font-mono text-[var(--color-text-muted)] uppercase tracking-wider block">
                  CHUNK CONFIG
                </span>
                <span className="text-sm font-bold font-mono text-[var(--color-text)] mt-0.5 block">
                  {chunksData?.chunking?.chunk_size_tokens || 512} / {chunksData?.chunking?.chunk_overlap_tokens || 64} tok
                </span>
              </div>
            </div>

            {/* Tab 1: 2D PCA Scatter View */}
            {activeTab === 'scatter' && (
              <div
                className="flex-1 rounded-2xl border p-4 shadow-sm flex flex-col min-h-0 overflow-hidden"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between pb-3 border-b mb-3" style={{ borderColor: 'var(--color-border)' }}>
                  <div>
                    <h3 className="text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                      Principal Component Analysis (PCA) 2D Projection
                    </h3>
                    <p className="text-[11px] text-[var(--color-text-muted)]">
                      Hover over any node to inspect the underlying chunk and source document.
                    </p>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded border bg-[var(--color-overlay)]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}>
                    Cosine Distance Topology
                  </span>
                </div>

                <div className="flex-1 w-full min-h-[360px] relative flex items-center justify-center">
                  <VectorScatter
                    chunks={chunksList}
                    pcaExplained={chunksData?.pcaExplained || []}
                    height={420}
                  />
                </div>
              </div>
            )}

            {/* Tab 2: Similarity Heatmap View */}
            {activeTab === 'heatmap' && (
              <div
                className="flex-1 rounded-2xl border p-4 shadow-sm flex flex-col min-h-0 overflow-hidden"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between pb-3 border-b mb-3" style={{ borderColor: 'var(--color-border)' }}>
                  <div>
                    <h3 className="text-xs font-bold" style={{ color: 'var(--color-text)' }}>
                      Pairwise Cosine Similarity Heatmap (N × N)
                    </h3>
                    <p className="text-[11px] text-[var(--color-text-muted)]">
                      Measures intra-corpus cross-document overlap. Diagonal indicates self-similarity (1.0).
                    </p>
                  </div>
                </div>

                <div className="flex-1 w-full min-h-[360px] relative flex items-center justify-center overflow-auto">
                  {chunksData?.similarity?.length > 0 ? (
                    <SimilarityHeatmap
                      similarity={chunksData.similarity}
                      chunks={chunksList}
                      height={420}
                    />
                  ) : (
                    <div className="text-xs text-[var(--color-text-muted)]">
                      {chunksData?.similarityOmitted
                        ? 'Corpus size exceeds matrix display threshold.'
                        : 'Similarity matrix unavailable.'}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 3: Chunk Registry */}
            {activeTab === 'chunks' && (
              <div className="flex-1 flex min-h-0 gap-4 overflow-hidden">
                {/* Left Chunk List */}
                <div
                  className="w-80 rounded-2xl border flex flex-col flex-shrink-0 overflow-hidden shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="p-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
                    <input
                      type="text"
                      value={chunkFilter}
                      onChange={(e) => setChunkFilter(e.target.value)}
                      placeholder="Filter chunks by doc or text..."
                      className="w-full px-2.5 py-1 text-xs rounded-lg border outline-none bg-[var(--color-input-bg)]"
                      style={{ borderColor: 'var(--color-input-border)', color: 'var(--color-text)' }}
                    />
                  </div>

                  <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
                    {filteredChunks.map((c, idx) => {
                      const isSelected = selectedChunk?.chunk_id === c.chunk_id
                      return (
                        <div
                          key={c.chunk_id || idx}
                          onClick={() => setSelectedChunk(c)}
                          className={`p-2.5 rounded-xl border cursor-pointer transition-fast ${
                            isSelected
                              ? 'bg-[var(--color-overlay)] border-[var(--color-accent-border)] shadow-xs'
                              : 'border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
                              {c.source_document || 'Chunk'}
                            </span>
                            <span className="text-[10px] font-mono text-[var(--color-text-muted)]">
                              #{c.chunk_id ?? idx}
                            </span>
                          </div>
                          <p className="text-[11px] text-[var(--color-text-muted)] line-clamp-2 mt-1 font-mono">
                            {c.text}
                          </p>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Right Chunk Inspector */}
                <div
                  className="flex-1 rounded-2xl border p-5 overflow-y-auto shadow-xs flex flex-col gap-4 select-text"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  {selectedChunk ? (
                    <>
                      <div className="flex items-center justify-between pb-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
                        <div>
                          <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-muted)]">
                            SOURCE DOCUMENT
                          </span>
                          <h3 className="text-sm font-bold mt-0.5" style={{ color: 'var(--color-text)' }}>
                            {selectedChunk.source_document}
                          </h3>
                        </div>
                        <span className="px-2 py-0.5 rounded text-xs font-mono border bg-[var(--color-overlay)]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}>
                          Chunk ID: {selectedChunk.chunk_id}
                        </span>
                      </div>

                      <div>
                        <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">
                          FULL CHUNK RAW TEXT
                        </span>
                        <pre
                          className="p-4 rounded-xl border font-mono text-xs leading-relaxed whitespace-pre-wrap"
                          style={{
                            background: 'var(--color-overlay)',
                            borderColor: 'var(--color-border)',
                            color: 'var(--color-text)',
                          }}
                        >
                          {selectedChunk.text}
                        </pre>
                      </div>
                    </>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-xs text-[var(--color-text-muted)]">
                      Select a chunk from the left panel to inspect its text and vector coordinates.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 4: Live Query Tester */}
            {activeTab === 'tester' && (
              <div
                className="flex-1 rounded-2xl border p-6 shadow-sm flex flex-col min-h-0 overflow-hidden"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <form onSubmit={handleTestSearch} className="flex gap-2 mb-6">
                  <div className="relative flex-1">
                    <Search size={14} className="absolute left-3 top-3 text-[var(--color-text-faint)]" />
                    <input
                      type="text"
                      value={testQuery}
                      onChange={(e) => setTestQuery(e.target.value)}
                      placeholder="Enter a test query to trace hybrid dense/sparse retrieval..."
                      className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border outline-none bg-[var(--color-input-bg)]"
                      style={{ borderColor: 'var(--color-input-border)', color: 'var(--color-text)' }}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!testQuery.trim() || isSearching}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-white transition-all shadow-xs cursor-pointer disabled:opacity-40"
                    style={{ background: 'var(--color-accent)' }}
                  >
                    {isSearching ? 'Retrieving...' : 'Run Hybrid Search'}
                  </button>
                </form>

                <div className="flex-1 overflow-y-auto flex flex-col gap-3">
                  {!testResults ? (
                    <div className="py-12 text-center text-xs text-[var(--color-text-muted)]">
                      Submit an inquiry above to observe which chunks are retrieved, their dense cosine similarity, BM25 rank, and reciprocal rank fusion scores.
                    </div>
                  ) : testResults.length === 0 ? (
                    <div className="py-12 text-center text-xs text-[var(--color-text-muted)]">
                      No chunks satisfied the confidence threshold for this query.
                    </div>
                  ) : (
                    testResults.map((res, i) => (
                      <div
                        key={i}
                        className="p-4 rounded-xl border flex flex-col gap-2 bg-[var(--color-overlay)]"
                        style={{ borderColor: 'var(--color-border)' }}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-[var(--color-text)]">
                            Rank #{i + 1} · {res.document || res.source_document || 'Document'}
                          </span>
                          <span className="text-[11px] font-mono text-[var(--color-accent)] font-semibold">
                            RRF Score: {res.score ? res.score.toFixed(4) : 'Match'}
                          </span>
                        </div>
                        <p className="text-xs text-[var(--color-text-muted)] font-mono leading-relaxed">
                          {res.text || res.passage}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
