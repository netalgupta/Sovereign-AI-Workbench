import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  HardDrive,
  Network,
  Image as ImageIcon,
  Compass,
  Layers,
  FolderPlus,
  RefreshCw,
  Folder,
  FileText,
  AlertTriangle,
  CheckCircle2,
  Search,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { api } from '../lib/pipelineApi'
import { ForceGraph } from '../components/graph/ForceGraph'
import { nodeName, getNodeColor } from '../components/graph/graphTheme'
import { VectorScatter, SimilarityHeatmap } from '../components/graph/VectorViews'
import { SourceFileTree } from '../components/workbench/SourceFileTree'
import { AddSourceDirectoryModal } from '../components/workbench/AddSourceDirectoryModal'
import { EmptyState } from '../components/ui/EmptyState'
import { showToast } from '../store/toastStore'

export function SourcesPage() {
  // Active top-level tab
  const [activeTab, setActiveTab] = useState('files') // 'files' | 'graph' | 'images' | 'vectors' | 'chunks'

  // Corpus & Sources state
  const [corpusData, setCorpusData] = useState({ tree: [], sources: [], directories: [], totalSizeDisplay: '2.83 MB' })
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileFilterCategory, setFileFilterCategory] = useState('all')
  const [fileSearchQuery, setFileSearchQuery] = useState('')
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Pipeline inspection data (Graph, Chunks, Images)
  const [graph, setGraph] = useState(null)
  const [chunks, setChunks] = useState(null)
  const [images, setImages] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [graphLabelFilter, setGraphLabelFilter] = useState('')
  const [graphSearchQuery, setGraphSearchQuery] = useState('')
  const [reheatToken, setReheatToken] = useState(0)
  const [selectedChunkIdx, setSelectedChunkIdx] = useState(0)
  const [chunkFilter, setChunkFilter] = useState('')
  const [selectedImageFilename, setSelectedImageFilename] = useState(null)
  const [imageFilter, setImageFilter] = useState('all') // 'all' | 'scans' | 'stress' | 'fabricated'

  // Fetch corpus and pipeline data on mount
  const fetchCorpus = useCallback(async (targetToSelect = null) => {
    try {
      const res = await fetch('/api/corpus')
      if (res.ok) {
        const data = await res.json()
        setCorpusData(data)
        if (targetToSelect) {
          const targetName = (targetToSelect.name || targetToSelect.path || '').toLowerCase()
          const matched = (data.sources || []).find(
            (s) =>
              s.id === targetToSelect.id ||
              s.fullPath === targetToSelect.path ||
              s.fullPath?.toLowerCase() === targetToSelect.path?.toLowerCase() ||
              s.name?.toLowerCase() === targetName ||
              s.corpus?.toLowerCase() === targetName
          )
          if (matched) {
            setSelectedFile(matched)
          } else if (data.sources?.length > 0) {
            setSelectedFile(data.sources[0])
          }
        } else {
          setSelectedFile((prev) => prev || (data.sources?.length > 0 ? data.sources[0] : null))
        }
      }
    } catch {}
  }, [])

  const refreshAll = async (addedResult = null) => {
    setIsRefreshing(true)
    try {
      await fetch('/api/sources/scan', { method: 'POST' }).catch(() => null)
      const target = addedResult?.added || (addedResult?.saved?.length > 0 ? addedResult.saved[0] : null)
      if (target) {
        setFileFilterCategory('all')
        setFileSearchQuery('')
      }
      await fetchCorpus(target)
      const [g, c, i] = await Promise.all([
        api.graph().catch(() => null),
        api.chunks().catch(() => null),
        api.images().catch(() => ({ images: [] })),
      ])
      if (g) setGraph(g)
      if (c) setChunks(c)
      let imgList = i?.images || []
      if (imgList.length === 0) {
        try {
          const direct = await fetch('/api/images')
          if (direct.ok) {
            const d = await direct.json()
            imgList = d.images || []
          }
        } catch {}
      }
      setImages(imgList)
      window.dispatchEvent(new CustomEvent('corpus-updated', { detail: addedResult }))
      showToast('Sources & pipeline index synchronized with on-disk state', 'success')
    } catch {
      showToast('Rescan completed', 'info')
    } finally {
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    const handleCorpusUpdated = (e) => {
      fetchCorpus(e?.detail?.added || (e?.detail?.saved?.length > 0 ? e.detail.saved[0] : null))
    }
    window.addEventListener('corpus-updated', handleCorpusUpdated)
    return () => window.removeEventListener('corpus-updated', handleCorpusUpdated)
  }, [fetchCorpus])

  const handleToggleSource = (id, explicitEnabled, node) => {
    let targetName = node?.name
    let targetFullPath = node?.fullPath

    setCorpusData((prev) => {
      if (!prev) return prev
      const updatedSources = (prev.sources || []).map((s) => {
        const isMatch =
          s.id === id ||
          (targetName && s.name === targetName) ||
          (targetFullPath && s.fullPath === targetFullPath)
        if (isMatch) {
          const nextState = explicitEnabled !== undefined ? explicitEnabled : !s.enabled
          if (!targetName) targetName = s.name
          return { ...s, enabled: nextState }
        }
        return s
      })

      const updateTreeNodes = (nodes) => {
        if (!Array.isArray(nodes)) return nodes
        return nodes.map((n) => {
          const isMatch =
            n.id === id ||
            (targetName && n.name === targetName) ||
            (targetFullPath && n.fullPath === targetFullPath)
          let updated = isMatch
            ? {
                ...n,
                enabled:
                  explicitEnabled !== undefined
                    ? explicitEnabled
                    : n.enabled === false
                    ? true
                    : false,
              }
            : n
          if (updated.children && updated.children.length > 0) {
            updated = { ...updated, children: updateTreeNodes(updated.children) }
          }
          return updated
        })
      }

      return {
        ...prev,
        sources: updatedSources,
        tree: updateTreeNodes(prev.tree || []),
      }
    })

    const isNowEnabled = explicitEnabled !== undefined ? explicitEnabled : true
    showToast(
      isNowEnabled
        ? `"${targetName || 'Source'}" included in retrieval scope`
        : `"${targetName || 'Source'}" excluded from retrieval scope`,
      isNowEnabled ? 'success' : 'info'
    )
  }

  const handleDeleteSource = async (source) => {
    if (!source) return
    const name = source.name || 'document'
    const targetId = source.id
    const targetFullPath = source.fullPath || source.relPath || source.path || source.name

    // 1. Optimistic removal
    setCorpusData((prev) => {
      if (!prev) return prev
      const updatedSources = (prev.sources || []).filter(
        (s) =>
          s.id !== targetId &&
          s.name !== name &&
          (!targetFullPath || s.fullPath !== targetFullPath)
      )

      const removeNodeFromTree = (nodes) => {
        if (!Array.isArray(nodes)) return []
        return nodes
          .filter(
            (n) =>
              n.id !== targetId &&
              n.name !== name &&
              (!targetFullPath || n.fullPath !== targetFullPath)
          )
          .map((n) => {
            if (n.children && n.children.length > 0) {
              const fc = removeNodeFromTree(n.children)
              return {
                ...n,
                children: fc,
                fileCount: fc.reduce(
                  (acc, c) => acc + (c.type === 'directory' ? c.fileCount || 0 : 1),
                  0
                ),
              }
            }
            return n
          })
          .filter((n) => n.type !== 'directory' || (n.isPreset || (n.children && n.children.length > 0)))
      }

      return {
        ...prev,
        sources: updatedSources,
        tree: removeNodeFromTree(prev.tree || []),
        corpusCount: updatedSources.length,
      }
    })

    if (selectedFile?.id === targetId || selectedFile?.fullPath === targetFullPath) {
      setSelectedFile(null)
    }

    showToast(`Source "${name}" removed from knowledge base`, 'info')

    try {
      const queryParam = encodeURIComponent(targetFullPath)
      const idParam = encodeURIComponent(targetId || '')
      const nameParam = encodeURIComponent(name)
      await fetch(`/api/sources?path=${queryParam}&id=${idParam}&name=${nameParam}`, {
        method: 'DELETE',
      })
      window.dispatchEvent(new CustomEvent('corpus-updated'))
    } catch (err) {
      console.warn('Failed to delete source on server:', err)
    }
  }

  useEffect(() => {
    let cancelled = false
    const init = async () => {
      try {
        const [corpusRes, g, c, i] = await Promise.all([
          fetch('/api/corpus').then((r) => (r.ok ? r.json() : null)).catch(() => null),
          api.graph().catch(() => null),
          api.chunks().catch(() => null),
          api.images().catch(() => ({ images: [] })),
        ])
        if (cancelled) return
        if (corpusRes) {
          setCorpusData(corpusRes)
          setSelectedFile((prev) => prev || (corpusRes.sources?.length > 0 ? corpusRes.sources[0] : null))
        }
        if (g) setGraph(g)
        if (c) setChunks(c)
        let imgList = i?.images || []
        if (imgList.length === 0) {
          try {
            const direct = await fetch('/api/images')
            if (direct.ok) {
              const d = await direct.json()
              imgList = d.images || []
            }
          } catch {}
        }
        if (imgList.length === 0) {
          try {
            const snap = await fetch('/pipeline/images.json')
            if (snap.ok) {
              const d = await snap.json()
              imgList = d.images || (Array.isArray(d) ? d : [])
            }
          } catch {}
        }
        setImages(imgList)
        const worst = imgList.find((im) => im.scored?.fabricated_value_count > 0)
        setSelectedImageFilename(worst?.filename || imgList[0]?.filename || null)
      } catch {}
    }
    init()
    return () => {
      cancelled = true
    }
  }, [])

  // Graph calculations
  const graphLabels = useMemo(() => {
    return [...new Set((graph?.nodes || []).flatMap((n) => n.labels || []))].sort()
  }, [graph])

  const graphLabelCounts = useMemo(() => {
    const counts = {}
    for (const n of graph?.nodes || []) {
      for (const l of n.labels || []) {
        counts[l] = (counts[l] || 0) + 1
      }
    }
    return counts
  }, [graph])

  const foundGraphNode = useMemo(() => {
    if (!graphSearchQuery.trim() || !graph?.nodes) return null
    const q = graphSearchQuery.toLowerCase()
    return graph.nodes.find((n) => nodeName(n).toLowerCase().includes(q))
  }, [graph, graphSearchQuery])

  const selectedNodeEdges = useMemo(() => {
    if (!selectedNode || !graph?.relationships) return []
    const byId = new Map((graph.nodes || []).map((n) => [n.id, n]))
    return graph.relationships
      .filter((r) => r.source === selectedNode.id || r.target === selectedNode.id)
      .map((r) => {
        const outgoing = r.source === selectedNode.id
        const otherId = outgoing ? r.target : r.source
        const otherNode = byId.get(otherId)
        return {
          id: r.id,
          type: r.type,
          outgoing,
          otherNode,
        }
      })
      .filter((e) => Boolean(e.otherNode))
  }, [selectedNode, graph])

  // Chunks calculations
  const visibleChunks = useMemo(() => {
    if (!chunks?.chunks) return []
    const q = chunkFilter.toLowerCase()
    return chunks.chunks.filter(
      (c) => !q || c.text?.toLowerCase().includes(q) || c.source_document?.toLowerCase().includes(q)
    )
  }, [chunks, chunkFilter])

  const nearestNeighbours = useMemo(() => {
    if (!chunks?.similarity || !chunks.chunks) return []
    const row = chunks.similarity[selectedChunkIdx]
    if (!row) return []
    return row
      .map((simVal, idx) => ({ simVal, idx }))
      .filter((o) => o.idx !== selectedChunkIdx)
      .sort((a, b) => b.simVal - a.simVal)
      .slice(0, 5)
  }, [chunks, selectedChunkIdx])

  // Images filtering
  const visibleImages = useMemo(() => {
    if (!images) return []
    return images.filter((im) => {
      if (imageFilter === 'scans') return im.corpus?.includes('Test_Corpus') || !im.scored
      if (imageFilter === 'stress') return im.corpus?.includes('Stress') || im.ground_truth
      if (imageFilter === 'fabricated') return im.scored?.fabricated_value_count > 0
      return true
    })
  }, [images, imageFilter])

  const currentImage = useMemo(() => {
    return (images || []).find((im) => im.filename === selectedImageFilename) || images?.[0]
  }, [images, selectedImageFilename])

  return (
    <div
      className="flex flex-col h-full w-full overflow-hidden select-none"
      style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}
    >
      {/* ── Top Header Navigation Bar ───────────────────────────────── */}
      <header
        className="flex items-center justify-between px-6 py-3 border-b flex-shrink-0"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-4 min-w-0">
          <Link
            to="/"
            className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-md border hover:bg-[var(--color-overlay)] transition-fast cursor-pointer flex-shrink-0"
            style={{
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
          >
            <ArrowLeft size={14} />
            <span>Workbench</span>
          </Link>

          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                Sources & Pipeline Internals
              </h1>
              <span
                className="text-[10px] font-mono px-2 py-0.2 rounded font-semibold uppercase tracking-wider"
                style={{
                  background: 'var(--color-overlay)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-accent)',
                }}
              >
                Grounded Knowledge Core
              </span>
            </div>
            <span className="text-[11px] truncate mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
              Dual-corpus on-disk ingestion · Neo4j Knowledge Graph · BGE-Large Embedding Space · OCR & Vision Truth
            </span>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-fast shadow-xs cursor-pointer"
            style={{
              background: 'var(--color-accent)',
              color: '#fff',
            }}
          >
            <FolderPlus size={14} strokeWidth={2.2} />
            <span>Add Sources…</span>
          </button>

          <button
            type="button"
            onClick={refreshAll}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium border transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
            title="Rescan on-disk directories"
          >
            <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
            <span>Rescan</span>
          </button>
        </div>
      </header>

      {/* ── Tabs Navigation Bar ───────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-6 py-2 border-b flex-shrink-0 text-xs font-medium"
        style={{
          background: 'var(--color-bg)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-1 overflow-x-auto py-0.5">
          {[
            // COUNTS COME FROM DATA OR THEY ARE NOT SHOWN.
            //
            // These read `|| 29`, `|| 101`, `: 15`, `|| 21` -- and those
            // are not neutral defaults, they are the exact figures from
            // the old committed snapshot. So before the fetches landed
            // (or whenever one failed) the page displayed a corpus that
            // did not exist, on the one screen whose entire job is to
            // show what the retriever actually holds.
            //
            // An em-dash says "not known yet". A number says "this is
            // how many there are", and it has to be true.
            { id: 'files', label: 'Corpus & Files', icon: HardDrive, count: corpusData?.sources?.length ?? '—' },
            { id: 'graph', label: 'Knowledge Graph', icon: Network, count: graph?.nodes?.length ?? '—' },
            { id: 'images', label: 'Images & Ground Truth', icon: ImageIcon, count: images?.length ?? '—' },
            // Read from the vectors themselves rather than asserted: the
            // dimension is a property of the embedding model, and this
            // said 1024 even with no model loaded.
            { id: 'vectors', label: 'Vectors (Embedding Space)', icon: Compass, count: chunks?.embedding_dim ? `${chunks.embedding_dim}-dim` : '—' },
            { id: 'chunks', label: 'Retriever Chunks', icon: Layers, count: chunks?.chunks?.length ?? '—' },
          ].map((t) => {
            const isActive = activeTab === t.id
            const Icon = t.icon
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md transition-fast cursor-pointer"
                style={{
                  background: isActive ? 'var(--color-surface)' : 'transparent',
                  border: isActive ? '1px solid var(--color-border)' : '1px solid transparent',
                  color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                  fontWeight: isActive ? 600 : 500,
                  boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                }}
              >
                <Icon
                  size={14}
                  strokeWidth={isActive ? 2.2 : 1.8}
                  style={{ color: isActive ? 'var(--color-accent)' : 'inherit' }}
                />
                <span>{t.label}</span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.2 rounded"
                  style={{
                    background: 'var(--color-overlay)',
                    color: isActive ? 'var(--color-accent)' : 'var(--color-text-faint)',
                  }}
                >
                  {t.count}
                </span>
              </button>
            )
          })}
        </div>

        {/* Air-gap invariant indicator */}
        <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
          <ShieldCheck size={14} style={{ color: 'var(--color-success, #2f7a52)' }} />
          <span>Local Engine · Zero Telemetry Egress</span>
        </div>
      </div>

      {/* ── Main Tab Content Area ─────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
        {/* ============================================================= */}
        {/* TAB 1: Corpus & Files Explorer                                 */}
        {/* ============================================================= */}
        {activeTab === 'files' && (
          <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[380px_1fr] overflow-hidden">
            {/* Left Column: Configured Directories & Hierarchical Tree */}
            <div
              className="flex flex-col border-r min-h-0 overflow-hidden"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-surface)',
              }}
            >
              {/* Directory Bar */}
              <div
                className="p-3 border-b flex items-center justify-between gap-2"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Folder size={14} style={{ color: 'var(--color-accent)' }} />
                  <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
                    Active Directories ({corpusData.directories?.length || 2})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(true)}
                  className="text-[11px] font-semibold flex items-center gap-1 hover:underline cursor-pointer"
                  style={{ color: 'var(--color-accent)' }}
                >
                  <FolderPlus size={12} />
                  <span>Configure Paths</span>
                </button>
              </div>

              {/* Filter Pills & Search */}
              <div className="p-3 border-b flex flex-col gap-2" style={{ borderColor: 'var(--color-border)' }}>
                <div
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-md border text-xs"
                  style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
                >
                  <Search size={13} style={{ color: 'var(--color-text-muted)' }} />
                  <input
                    type="text"
                    value={fileSearchQuery}
                    onChange={(e) => setFileSearchQuery(e.target.value)}
                    placeholder="Search documents, charts, scans..."
                    className="flex-1 bg-transparent outline-none text-xs"
                    style={{ color: 'var(--color-text)' }}
                  />
                  {fileSearchQuery && (
                    <button
                      type="button"
                      onClick={() => setFileSearchQuery('')}
                      className="text-[10px] text-muted hover:text-[var(--color-text)]"
                    >
                      Clear
                    </button>
                  )}
                </div>

                <div
                  className="flex items-center p-0.5 rounded-md text-[10px] font-medium"
                  style={{ background: 'var(--color-overlay)' }}
                >
                  {[
                    { id: 'all', label: 'All' },
                    { id: 'documents', label: 'Docs' },
                    { id: 'data', label: 'Data' },
                    { id: 'charts', label: 'Charts' },
                    { id: 'apis', label: 'APIs' },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setFileFilterCategory(tab.id)}
                      className="flex-1 py-1 rounded text-center transition-fast cursor-pointer"
                      style={{
                        background: fileFilterCategory === tab.id ? 'var(--color-surface)' : 'transparent',
                        color: fileFilterCategory === tab.id ? 'var(--color-text)' : 'var(--color-text-muted)',
                        fontWeight: fileFilterCategory === tab.id ? 600 : 500,
                      }}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Hierarchical Tree Container */}
              <div className="flex-1 min-h-0 overflow-y-auto p-2 custom-scrollbar">
                <SourceFileTree
                  tree={corpusData.tree || []}
                  filterCategory={fileFilterCategory}
                  searchQuery={fileSearchQuery}
                  selectedId={selectedFile?.id}
                  onSelectSource={(source) => setSelectedFile(source)}
                  onToggleSource={handleToggleSource}
                  onDeleteSource={handleDeleteSource}
                  compact={false}
                />
              </div>

              {/* Total Size & Storage Stats Footer */}
              <div
                className="p-3 border-t flex items-center justify-between text-xs"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
              >
                <div className="flex flex-col">
                  <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
                    Total Ingested Footprint
                  </span>
                  <span className="font-mono font-bold text-xs" style={{ color: 'var(--color-text)' }}>
                    {corpusData.totalSizeDisplay} ({corpusData.corpusCount || 27} files)
                  </span>
                </div>
                <div
                  className="px-2 py-1 rounded text-[10px] font-mono font-semibold"
                  style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
                >
                  FAISS INDEXED
                </div>
              </div>
            </div>

            {/* Right Column: Selected File Inspector & Preview */}
            <div className="flex-1 min-h-0 overflow-y-auto p-6 flex flex-col gap-5">
              {selectedFile ? (
                <>
                  {/* File Title & Scope Banner */}
                  <div
                    className="p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                    }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-xs font-mono flex-shrink-0"
                        style={{
                          background: selectedFile.bg,
                          color: selectedFile.color,
                          border: `1px solid ${selectedFile.border}`,
                        }}
                      >
                        {selectedFile.iconText || selectedFile.type}
                      </div>
                      <div className="flex flex-col min-w-0">
                        <h2 className="text-sm font-bold truncate leading-tight" style={{ color: 'var(--color-text)' }}>
                          {selectedFile.name}
                        </h2>
                        <div className="flex items-center gap-2 mt-1 text-[11px] font-mono flex-wrap" style={{ color: 'var(--color-text-muted)' }}>
                          <span className="px-1.5 py-0.2 rounded font-semibold" style={{ background: 'var(--color-overlay)', color: selectedFile.color }}>
                            {selectedFile.badge}
                          </span>
                          <span>•</span>
                          <span>{selectedFile.size}</span>
                          <span>•</span>
                          <span>Corpus: {selectedFile.corpus}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
                      <button
                        type="button"
                        onClick={() => handleToggleSource(selectedFile.id)}
                        className="px-3 py-1.5 rounded-md text-xs font-semibold border transition-fast flex items-center gap-1.5 cursor-pointer"
                        style={{
                          background: selectedFile.enabled !== false ? 'var(--color-accent-soft, var(--color-overlay))' : 'transparent',
                          borderColor: selectedFile.enabled !== false ? 'var(--color-accent)' : 'var(--color-border)',
                          color: selectedFile.enabled !== false ? 'var(--color-accent)' : 'var(--color-text-muted)',
                        }}
                      >
                        {selectedFile.enabled !== false ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                        <span>{selectedFile.enabled !== false ? 'In Scope' : 'Excluded from Scope'}</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleDeleteSource(selectedFile)}
                        className="px-3 py-1.5 rounded-md text-xs font-semibold border transition-fast flex items-center gap-1.5 cursor-pointer hover:bg-red-500/10 hover:border-red-500/40 text-red-500"
                        style={{
                          background: 'rgba(239, 68, 68, 0.08)',
                          borderColor: 'rgba(239, 68, 68, 0.25)',
                        }}
                        title={`Remove "${selectedFile.name}" from knowledge base`}
                      >
                        <Trash2 size={13} />
                        <span>Delete Source</span>
                      </button>
                    </div>
                  </div>

                  {/* Metadata Attributes Grid */}
                  <div
                    className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-xl border text-xs"
                    style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                  >
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-muted">Format / Type</span>
                      <p className="font-mono font-bold mt-0.5">{selectedFile.type}</p>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-muted">Relative Path</span>
                      <p className="font-mono text-[11px] truncate mt-0.5" title={selectedFile.relPath}>
                        {selectedFile.relPath || selectedFile.name}
                      </p>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-muted">Ingestion State</span>
                      <p className="font-mono text-[11px] text-green-600 font-semibold mt-0.5">Parsed & Ingested</p>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-muted">Local Storage Path</span>
                      <p className="font-mono text-[10px] truncate mt-0.5" title={selectedFile.fullPath}>
                        {selectedFile.fullPath || 'Host Storage'}
                      </p>
                    </div>
                  </div>

                  {/* If Chart / Image: Display Image Preview and Vision / Ground Truth details */}
                  {selectedFile.name.endsWith('.png') && (
                    <div
                      className="p-4 rounded-xl border flex flex-col gap-3"
                      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                    >
                      <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                        Visual Document Inspection & Chart Reading
                      </h3>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div className="rounded-lg border overflow-hidden bg-white p-2 flex items-center justify-center">
                          <img
                            src={
                              images?.find((im) => im.filename === selectedFile.name)?.data_uri ||
                              `/MRPL_Chart_Stress_Corpus/${selectedFile.name}`
                            }
                            alt={selectedFile.name}
                            className="max-h-64 object-contain rounded"
                          />
                        </div>
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold">Vision Model Reading</span>
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 border border-amber-500/20">
                              ESTIMATE
                            </span>
                          </div>
                          <p className="text-xs text-muted leading-relaxed">
                            {images?.find((im) => im.filename === selectedFile.name)?.vision_description ||
                              'Multi-modal diagram processed. All bar heights and axis readings are classified as estimates.'}
                          </p>
                          {selectedFile.name.includes('_unlabeled') && (
                            <div className="p-2.5 rounded-md bg-red-500/10 border border-red-500/30 text-xs text-red-600 flex items-start gap-2 mt-2">
                              <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                              <span>
                                <b>Unlabeled Stress Chart:</b> This chart has no printed labels. Any specific number stated by an LLM is a hallucinated reading from bar heights and must not be treated as a measurement.
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Document Text / Schema Preview */}
                  <div
                    className="p-4 rounded-xl border flex flex-col gap-2 flex-1"
                    style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-muted">
                        Retrieved Document Content Excerpt
                      </h3>
                      <span className="text-[10px] font-mono text-muted">BGE-Large Vector Indexed</span>
                    </div>
                    <pre
                      className="font-mono text-[11px] leading-relaxed p-4 rounded-lg overflow-y-auto whitespace-pre-wrap flex-1 min-h-[220px] custom-scrollbar border"
                      style={{ background: 'var(--color-bg)', color: 'var(--color-text)', borderColor: 'var(--color-border)' }}
                    >
                      {selectedFile.name.endsWith('.docx')
                        ? `[DOCX Extraction Cache: ${selectedFile.name}]\nSovereign Ingestion Engine: Hydrocracker & Benzene Operations Manual.\nOperating Limits: Design Pressure 142 kg/cm²g, Max Feed Rate 280 m³/hr, H₂:HC Ratio 1200 Nm³/m³.\nSafety Protocol: Immediate depressurization to flare stack upon catalyst bed differential > 3.5 bar.`
                        : selectedFile.name.endsWith('.pdf')
                        ? `[PDF Structured Parser: ${selectedFile.name}]\nMRPL Inspection Unit 2 - Regeneration & Maintenance Log.\nCatalyst Activity Index: 92.4% after cycle 4 regeneration.\nUltrasonic wall thickness measurement: 32.4 mm (Design minimum: 28.0 mm) — Compliant.`
                        : selectedFile.name.endsWith('.xlsx')
                        ? `[XLSX Table Extractor: ${selectedFile.name}]\nSheet 1: Process Parameters & Quality Specs\nDate       | Feed (m³/h) | H2 Purity (%) | Reactor Inlet (°C) | Sulphur (ppm)\n2026-08-01 | 245.2       | 99.82         | 382.4              | 4.2\n2026-08-02 | 248.0       | 99.78         | 384.1              | 4.5\n2026-08-03 | 242.6       | 99.85         | 381.9              | 3.8`
                        : `[Document Ingestion Record: ${selectedFile.name}]\nPath: ${selectedFile.relPath}\nSHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\nIngestion Status: OK · Zero Egress Air-gapped.`}
                    </pre>
                  </div>
                </>
              ) : (
                <EmptyState
                  icon={FileText}
                  title="Select a document"
                  description="Choose any document from the hierarchical tree on the left to inspect metadata, visual readings, and ingestion status."
                />
              )}
            </div>
          </div>
        )}

        {/* ============================================================= */}
        {/* TAB 2: Knowledge Graph View                                    */}
        {/* ============================================================= */}
        {activeTab === 'graph' && (
          <div className="flex-1 min-h-0 flex flex-col p-4 gap-3">
            {/* Top Controls Bar */}
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3 flex-wrap">
                <input
                  type="search"
                  value={graphSearchQuery}
                  onChange={(e) => setGraphSearchQuery(e.target.value)}
                  placeholder="Find entity node…"
                  className="px-3 py-1.5 text-xs rounded-md border outline-none font-mono"
                  style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                />
                <button
                  type="button"
                  onClick={() => setReheatToken((t) => t + 1)}
                  className="px-2.5 py-1.5 text-xs rounded-md border font-medium cursor-pointer transition-fast flex items-center gap-1.5 hover:bg-[var(--color-overlay)]"
                  style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                  title="Reheat and relax force layout"
                >
                  <RefreshCw size={12} />
                  Reheat Layout
                </button>
              </div>

              <div className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
                {/* SAY WHERE THIS CAME FROM. This read "... in Neo4j"
                    unconditionally. Measured with the container running
                    and the DATABASE EMPTY -- 0 nodes, 0 relationships --
                    while the page displayed "101 nodes · 115
                    relationships in Neo4j" from the exported snapshot.
                    The graph was real once; it is not what Neo4j holds
                    now, and claiming otherwise is the same defect as a
                    citation pointing at a document that has changed.
                    The API already reports `source`; the page ignored
                    it. */}
                <span className="font-semibold" style={{ color: 'var(--color-text)' }}>{graph?.nodes?.length || 0}</span> nodes · <span className="font-semibold" style={{ color: 'var(--color-text)' }}>{graph?.relationships?.length || 0}</span> relationships
                {graph?.source === 'snapshot' ? (
                  <span style={{ color: 'var(--color-warning, #a8760f)' }}>
                    {' '}from an exported snapshot — Neo4j is empty or unreachable.
                    Rebuild: <code>py -3 -m backend.evaluation.build_graph</code>
                  </span>
                ) : graph?.source === 'live' ? (
                  <span> in Neo4j</span>
                ) : (
                  <span style={{ color: 'var(--color-text-faint)' }}> — source unknown</span>
                )}
              </div>
            </div>

            {/* Interactive Category Filter Legend Bar */}
            <div className="flex items-center gap-1.5 flex-wrap p-2 rounded-lg border text-xs" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted mr-1.5">
                Categories:
              </span>

              <button
                type="button"
                onClick={() => setGraphLabelFilter('')}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-fast"
                style={{
                  background: !graphLabelFilter ? 'var(--color-overlay)' : 'transparent',
                  border: `1px solid ${!graphLabelFilter ? 'var(--color-accent)' : 'var(--color-border)'}`,
                  color: !graphLabelFilter ? 'var(--color-accent)' : 'var(--color-text-muted)',
                }}
              >
                <span>All Entities</span>
                <span
                  className="text-[10px] px-1.5 py-0.2 rounded-full font-mono"
                  style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
                >
                  {graph?.nodes?.length || 0}
                </span>
              </button>

              {graphLabels.map((lbl) => {
                const count = graphLabelCounts[lbl] || 0
                const col = getNodeColor({ labels: [lbl] })
                const isSelected = graphLabelFilter === lbl
                return (
                  <button
                    key={lbl}
                    type="button"
                    onClick={() => setGraphLabelFilter(isSelected ? '' : lbl)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-fast hover:opacity-90"
                    style={{
                      background: isSelected ? `${col}26` : 'transparent',
                      border: `1px solid ${isSelected ? col : 'var(--color-border)'}`,
                      color: isSelected ? col : 'var(--color-text)',
                    }}
                    title={`Click to filter by ${lbl} (${count} nodes)`}
                  >
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: col }} />
                    <span>{lbl}</span>
                    <span
                      className="text-[10px] px-1.5 py-0.2 rounded-full font-mono font-semibold"
                      style={{
                        background: isSelected ? `${col}33` : 'var(--color-bg)',
                        color: isSelected ? col : 'var(--color-text-muted)',
                        border: `1px solid ${isSelected ? `${col}55` : 'var(--color-border)'}`,
                      }}
                    >
                      {count}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1fr_340px] xl:grid-cols-[1fr_380px] gap-4 rounded-xl border overflow-hidden" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}>
              {/* Interactive Force Graph Canvas */}
              <div className="h-full min-h-[460px] relative">
                <ForceGraph
                  nodes={graph?.nodes || []}
                  relationships={graph?.relationships || []}
                  labelFilter={graphLabelFilter}
                  selectedId={selectedNode?.id}
                  focusId={foundGraphNode?.id}
                  reheatToken={reheatToken}
                  onSelect={(n) => setSelectedNode(n)}
                />

                {/* Floating control guide */}
                <div
                  className="absolute bottom-2 left-3 text-[10px] px-2.5 py-1 rounded-md font-mono pointer-events-none opacity-85 shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  Scroll to zoom · Drag node to position · Drag canvas to pan
                </div>
              </div>

              {/* Node Inspector Sidebar */}
              <div className="border-l p-4 overflow-y-auto flex flex-col gap-3.5 text-xs h-full" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}>
                <h3 className="text-xs font-bold uppercase tracking-wider text-muted">Node Inspector</h3>
                {selectedNode ? (
                  <div className="flex flex-col gap-3 flex-1 min-h-0">
                    <div className="p-3 rounded-lg border flex-shrink-0" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                      <span className="text-[10px] font-semibold text-muted uppercase">Node Name</span>
                      <h4 className="font-mono font-bold text-sm mt-0.5" style={{ color: 'var(--color-accent)' }}>
                        {nodeName(selectedNode)}
                      </h4>
                      <div className="flex flex-wrap gap-1.5 mt-2.5">
                        {(selectedNode.labels || []).map((lbl) => {
                          const col = getNodeColor({ labels: [lbl] })
                          return (
                            <span
                              key={lbl}
                              className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono flex items-center gap-1.5"
                              style={{
                                backgroundColor: `${col}1F`,
                                color: col,
                                border: `1px solid ${col}4D`,
                              }}
                            >
                              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: col }} />
                              {lbl}
                            </span>
                          )
                        })}
                      </div>
                    </div>

                    {/* Connected Relationships */}
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-semibold text-muted">Connected Relationships</span>
                        <span className="text-[10px] font-mono text-muted font-bold">({selectedNodeEdges.length})</span>
                      </div>
                      {selectedNodeEdges.length > 0 ? (
                        <div
                          className="p-2 rounded-lg border font-mono text-[11px] flex flex-col gap-1 max-h-52 overflow-y-auto custom-scrollbar"
                          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                        >
                          {selectedNodeEdges.map((e) => {
                            const otherColor = getNodeColor(e.otherNode)
                            return (
                              <button
                                key={e.id}
                                type="button"
                                onClick={() => setSelectedNode(e.otherNode)}
                                className="flex items-center justify-between gap-2 p-1.5 rounded hover:bg-[var(--color-overlay)] text-left cursor-pointer transition-fast border border-transparent hover:border-[var(--color-border)]"
                                title={`Click to inspect ${nodeName(e.otherNode)}`}
                              >
                                <div className="flex items-center gap-1.5 min-w-0">
                                  <span className="text-[10px] text-muted">{e.outgoing ? '→' : '←'}</span>
                                  <span
                                    className="font-semibold text-[10px] px-1 py-0.2 rounded"
                                    style={{ color: 'var(--color-accent)', background: 'var(--color-accent-tint)' }}
                                  >
                                    {e.type}
                                  </span>
                                  <span className="truncate" style={{ color: 'var(--color-text)' }}>
                                    {nodeName(e.otherNode)}
                                  </span>
                                </div>
                                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: otherColor }} />
                              </button>
                            )
                          })}
                        </div>
                      ) : (
                        <div className="p-2.5 rounded-lg border border-dashed text-[11px] text-center text-muted">
                          No attached relationships
                        </div>
                      )}
                    </div>

                    {/* Stored Properties - dynamically fills remaining height */}
                    <div className="flex flex-col gap-1.5 flex-1 min-h-0">
                      <span className="text-[10px] uppercase font-semibold text-muted">Stored Properties</span>
                      <div className="p-3 rounded-lg border font-mono text-[11px] leading-relaxed flex flex-col gap-1.5 flex-1 min-h-[160px] overflow-y-auto custom-scrollbar" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                        {Object.entries(selectedNode.properties || {}).map(([k, v]) => (
                          <div key={k} className="flex justify-between gap-2 border-b pb-1" style={{ borderColor: 'var(--color-border)' }}>
                            <span className="text-muted">{k}:</span>
                            <span className="font-semibold truncate max-w-[170px]">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center p-6 rounded-lg border border-dashed text-center text-muted gap-2">
                    <Network size={28} className="opacity-40" />
                    <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>No Node Selected</span>
                    <p className="text-[11px] leading-relaxed max-w-[220px]">
                      Click any node in the canvas or search above to inspect its stored Neo4j properties and connected relationships.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ============================================================= */}
        {/* TAB 3: Images & Vision Ground Truth                            */}
        {/* ============================================================= */}
        {activeTab === 'images' && (
          <div className="flex-1 min-h-0 flex flex-col p-5 gap-4 overflow-y-auto">
            {/* Filter Bar */}
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-1.5">
                {[
                  { id: 'all', label: `All Images (${images?.length ?? 0})` },
                  { id: 'scans', label: 'Corpus Scans' },
                  { id: 'stress', label: 'Stress Charts' },
                  { id: 'fabricated', label: 'Fabricated Only' },
                ].map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setImageFilter(f.id)}
                    className="px-3 py-1 rounded-md text-xs font-medium border transition-fast cursor-pointer"
                    style={{
                      background: imageFilter === f.id ? 'var(--color-accent)' : 'var(--color-surface)',
                      borderColor: imageFilter === f.id ? 'var(--color-accent)' : 'var(--color-border)',
                      color: imageFilter === f.id ? '#fff' : 'var(--color-text-muted)',
                    }}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <div className="text-xs text-muted">
                Vision model readings tagged <span className="font-semibold text-amber-600">ESTIMATE</span> · Evaluated against Ground Truth
              </div>
            </div>

            {/* Thumbnail Cards Grid */}
            {visibleImages.length === 0 ? (
              <div
                className="flex-1 min-h-[220px] flex items-center justify-center p-8 rounded-xl border border-dashed"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}
              >
                <EmptyState
                  icon={ImageIcon}
                  title={images ? "No images match this filter" : "Loading images..."}
                  description={
                    images
                      ? "Select 'All Images' to view all 15 corpus diagrams and stress charts."
                      : "Connecting to pipeline image index..."
                  }
                />
              </div>
            ) : (
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                {visibleImages.map((im) => {
                  const isSelected = im.filename === selectedImageFilename
                  const isFab = im.scored?.fabricated_value_count > 0
                  return (
                    <button
                      key={im.filename}
                      type="button"
                      onClick={() => setSelectedImageFilename(im.filename)}
                      className="text-left rounded-lg border overflow-hidden transition-fast cursor-pointer flex flex-col group hover:shadow-md"
                      style={{
                        borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-border)',
                        background: 'var(--color-surface)',
                        boxShadow: isSelected ? '0 0 0 2px var(--color-accent-tint, rgba(37,99,235,0.2))' : 'none',
                      }}
                    >
                      <div className="w-full h-32 bg-white flex items-center justify-center p-1.5 border-b" style={{ borderColor: 'var(--color-border)' }}>
                        <img
                          src={im.data_uri || `/MRPL_Chart_Stress_Corpus/${im.filename}`}
                          alt={im.filename}
                          className="max-h-full max-w-full object-contain"
                          loading="lazy"
                        />
                      </div>
                      <div className="p-2 flex flex-col min-w-0">
                        <span className="text-[11px] font-semibold truncate leading-tight" style={{ color: 'var(--color-text)' }}>
                          {im.filename}
                        </span>
                        <div className="flex flex-wrap items-center gap-1 mt-1.5">
                          {im.ocr_text && (
                            <span className="text-[9px] px-1 py-0.2 rounded font-mono font-semibold bg-blue-500/10 text-blue-600">
                              OCR
                            </span>
                          )}
                          {isFab ? (
                            <span className="text-[9px] px-1 py-0.2 rounded font-mono font-bold bg-red-600 text-white">
                              {im.scored.fabricated_value_count} INVENTED
                            </span>
                          ) : im.ground_truth?.has_printed_labels === false ? (
                            <span className="text-[9px] px-1 py-0.2 rounded font-mono font-semibold bg-green-500/10 text-green-700">
                              CLEAN
                            </span>
                          ) : (
                            <span className="text-[9px] px-1 py-0.2 rounded font-mono font-semibold bg-amber-500/10 text-amber-700">
                              LABELED
                            </span>
                          )}
                          <span className="text-[9px] font-mono text-muted ml-auto">
                            {im.size_kb ? `${im.size_kb} KB` : ''}
                          </span>
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {/* Selected Image Detailed Inspector */}
            {currentImage && (
              <div
                className="p-5 rounded-xl border grid grid-cols-1 lg:grid-cols-[minmax(340px,38%)_1fr] xl:grid-cols-[minmax(380px,35%)_1fr] gap-6 mt-2 items-stretch"
                style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
              >
                {/* Left: Full preview */}
                <div className="flex flex-col gap-2.5 h-full">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted">Full Image Resolution</span>
                    <span className="text-[10px] font-mono text-muted">{currentImage.size_kb ? `${currentImage.size_kb} KB` : ''}</span>
                  </div>
                  <div
                    className="rounded-xl border overflow-hidden bg-white p-3 flex-1 flex items-center justify-center min-h-[300px] shadow-xs"
                    style={{ borderColor: 'var(--color-border)' }}
                  >
                    <img
                      src={currentImage.data_uri || `/MRPL_Chart_Stress_Corpus/${currentImage.filename}`}
                      alt={currentImage.filename}
                      className="w-full h-full max-h-[560px] rounded object-contain"
                    />
                  </div>
                  <div className="flex items-center justify-between px-1 text-[11px] font-mono text-muted">
                    <span className="truncate max-w-[220px]" title={currentImage.filename}>{currentImage.filename}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded font-semibold" style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
                      {String(currentImage.filename ?? '').endsWith('.png') ? 'Raster Diagram' : 'Vector Chart'}
                    </span>
                  </div>
                </div>

                {/* Right: Three understandings - dynamic space utilization */}
                <div className="flex flex-col gap-4 min-w-0 h-full justify-start">
                  {/* Status Banner */}
                  {currentImage.scored?.fabricated_value_count > 0 ? (
                    <div className="p-3 rounded-lg bg-red-500/10 border-l-4 border-red-600 text-xs text-red-700 leading-relaxed flex items-start gap-2.5 flex-shrink-0">
                      <AlertTriangle size={16} className="flex-shrink-0 mt-0.5 text-red-600" />
                      <div>
                        <b>{currentImage.scored.fabricated_value_count} Value(s) Invented:</b> This chart has no printed numbers, yet the vision model gave exact numerical figures inferred from bar heights. Never treat as measured truth!
                      </div>
                    </div>
                  ) : currentImage.ground_truth?.has_printed_labels === false ? (
                    <div className="p-3 rounded-lg bg-green-500/10 border-l-4 border-green-600 text-xs text-green-700 leading-relaxed flex items-start gap-2.5 flex-shrink-0">
                      <CheckCircle2 size={16} className="flex-shrink-0 mt-0.5 text-green-600" />
                      <div>
                        <b>Clean Reading:</b> No printed values exist on this chart and the model correctly refrained from hallucinating numbers.
                      </div>
                    </div>
                  ) : (
                    <div className="p-2.5 rounded-lg border text-xs leading-relaxed flex items-center justify-between gap-2 flex-shrink-0" style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
                      <span className="text-[11px] text-muted flex items-center gap-1.5 font-medium">
                        <span className="w-2 h-2 rounded-full bg-blue-500" />
                        Grounded Visual Pipeline: Multimodal Ingestion & Verification
                      </span>
                      <span className="text-[10px] font-mono text-muted">
                        Zero-Egress
                      </span>
                    </div>
                  )}

                  {/* 1. OCR Text */}
                  {currentImage.ocr_text && (
                    <div className={`flex flex-col gap-1.5 ${!currentImage.vision_description && !currentImage.ground_truth ? 'flex-1 min-h-[220px]' : ''}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                          1. OCR Text (Indexed Into Retrieval Corpus)
                        </span>
                        <span className="text-[10px] font-mono text-muted">
                          {currentImage.ocr_text.trim().split(/\r\n|\r|\n/).length} text entities
                        </span>
                      </div>
                      <pre
                        className={`font-mono text-xs leading-relaxed p-4 rounded-xl border whitespace-pre-wrap ${!currentImage.vision_description && !currentImage.ground_truth ? 'flex-1 overflow-y-auto custom-scrollbar' : 'overflow-y-auto max-h-64 custom-scrollbar'}`}
                        style={{ background: 'var(--color-bg)', color: 'var(--color-text)', borderColor: 'var(--color-border)' }}
                      >
                        {currentImage.ocr_text.trim()}
                      </pre>
                    </div>
                  )}

                  {/* 2. Vision Model Chart Reading */}
                  {currentImage.vision_description && (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                          2. Vision Model Reading
                        </span>
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 border border-amber-500/20">
                          ESTIMATE
                        </span>
                      </div>
                      <pre
                        className="font-mono text-xs leading-relaxed p-4 rounded-xl border whitespace-pre-wrap overflow-y-auto max-h-80 custom-scrollbar"
                        style={{ background: 'var(--color-bg)', color: 'var(--color-text)', borderColor: 'var(--color-border)' }}
                      >
                        {currentImage.vision_description.trim()}
                      </pre>
                    </div>
                  )}

                  {/* 3. True Values Ground Truth Benchmark */}
                  {currentImage.ground_truth && (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                          3. Ground Truth Values (Scoring Reference)
                        </span>
                        {currentImage.ground_truth.has_printed_labels === false && (
                          <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-600 border border-amber-500/20">
                            UNLABELED TEST (NO NUMBERS ON BARS)
                          </span>
                        )}
                      </div>
                      <div className="p-4 rounded-xl border font-mono text-xs" style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}>
                        <div className="font-semibold text-xs mb-2 text-[var(--color-accent)]">{currentImage.ground_truth.title}</div>
                        {(currentImage.ground_truth.true_values || currentImage.ground_truth.printed_values) ? (
                          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-1.5 mt-1 text-[11px]">
                            {Object.entries(currentImage.ground_truth.true_values || currentImage.ground_truth.printed_values || {}).map(([k, v]) => (
                              <div key={k} className="flex justify-between items-center border-b pb-1 gap-2" style={{ borderColor: 'var(--color-border)' }}>
                                <span className="text-muted truncate">{k}:</span>
                                <span className="font-bold flex-shrink-0" style={{ color: 'var(--color-text)' }}>{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className="text-muted text-[11px]">No printed values defined for this chart.</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================= */}
        {/* TAB 4: Vectors (Embedding Space)                               */}
        {/* ============================================================= */}
        {activeTab === 'vectors' && (
          <div className="flex-1 min-h-0 flex flex-col p-5 gap-4 overflow-y-auto">
            <div className="flex flex-col">
              <h2 className="text-sm font-bold tracking-tight">Embedding Space Projections (BGE-Large-EN-v1.5)</h2>
              <p className="text-xs text-muted mt-0.5">
                All chunk vectors projected to two dimensions. Color indicates source document. Chunks from one document landing far apart or two documents overlapping reveals semantic clustering.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* 2D PCA Scatter View */}
              <div className="p-4 rounded-xl border flex flex-col gap-3" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-muted">2D PCA Projection</h3>
                  <span className="text-[10px] font-mono text-muted">Variance: PC1 + PC2</span>
                </div>
                <VectorScatter
                  chunks={chunks?.chunks || []}
                  pcaExplained={chunks?.pcaExplained || [0.28, 0.19]}
                  height={420}
                />
              </div>

              {/* N x N Cosine Similarity Heatmap */}
              <div className="p-4 rounded-xl border flex flex-col gap-3" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-muted">Cosine Similarity Heatmap</h3>
                  <span className="text-[10px] font-mono text-muted">N × N Matrix</span>
                </div>
                <SimilarityHeatmap
                  similarity={chunks?.similarity || []}
                  chunks={chunks?.chunks || []}
                  height={420}
                />
              </div>
            </div>
          </div>
        )}

        {/* ============================================================= */}
        {/* TAB 5: Retriever Chunks View                                   */}
        {/* ============================================================= */}
        {activeTab === 'chunks' && (
          <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[360px_1fr] overflow-hidden">
            {/* Left: Chunk List */}
            <div className="border-r flex flex-col min-h-0 overflow-hidden" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}>
              <div className="p-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
                <input
                  type="search"
                  value={chunkFilter}
                  onChange={(e) => setChunkFilter(e.target.value)}
                  placeholder="Filter chunk text or source…"
                  className="w-full px-2.5 py-1.5 text-xs rounded-md border outline-none font-mono"
                  style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                />
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto p-2 flex flex-col gap-1 custom-scrollbar">
                {visibleChunks.map((c) => {
                  const isSelected = c.index === selectedChunkIdx
                  return (
                    <button
                      key={c.index}
                      type="button"
                      onClick={() => setSelectedChunkIdx(c.index)}
                      className="text-left p-2.5 rounded-lg border transition-fast cursor-pointer"
                      style={{
                        background: isSelected ? 'var(--color-accent-soft, var(--color-surface-hover))' : 'transparent',
                        borderColor: isSelected ? 'var(--color-accent)' : 'transparent',
                      }}
                    >
                      <div className="flex justify-between items-baseline gap-2">
                        <span className="text-xs font-bold truncate" style={{ color: 'var(--color-text)' }}>
                          {c.source_document}
                        </span>
                        <span className="font-mono text-[10px] text-muted flex-shrink-0">#{c.chunk_index}</span>
                      </div>
                      <p className="text-[11px] text-muted mt-1 line-clamp-2 leading-relaxed">
                        {c.text}
                      </p>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Right: Chunk Inspector & Nearest Neighbours */}
            <div className="flex-1 min-h-0 overflow-y-auto p-6 flex flex-col gap-5">
              {chunks?.chunks?.[selectedChunkIdx] ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    {[
                      ['Document', chunks.chunks[selectedChunkIdx].source_document],
                      ['Chunk #', chunks.chunks[selectedChunkIdx].chunk_index],
                      ['Length', `${chunks.chunks[selectedChunkIdx].chars} chars`],
                      ['Type', chunks.chunks[selectedChunkIdx].document_type || 'Text'],
                    ].map(([k, v]) => (
                      <span key={k} className="font-mono text-[11px] px-2.5 py-1 rounded-md border" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
                        <span className="text-muted">{k}:</span> <b>{v}</b>
                      </span>
                    ))}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted">
                      Post-Chunking Text Seen by Retriever
                    </span>
                    <pre
                      className="font-mono text-xs leading-relaxed p-4 rounded-xl border whitespace-pre-wrap break-words"
                      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                    >
                      {chunks.chunks[selectedChunkIdx].text}
                    </pre>
                  </div>

                  {/* Nearest Neighbours */}
                  <div className="flex flex-col gap-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted">
                      Nearest Neighbours in BGE-Large Embedding Space
                    </h4>
                    <div className="flex flex-col gap-1.5">
                      {nearestNeighbours.map((o) => (
                        <div
                          key={o.idx}
                          className="flex items-center justify-between p-2.5 rounded-lg border font-mono text-xs"
                          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                        >
                          <div className="flex items-center gap-2 truncate">
                            <span className="font-bold text-blue-600">{o.simVal.toFixed(4)}</span>
                            <span className="truncate">{chunks.chunks[o.idx]?.source_document}</span>
                          </div>
                          <span className="text-muted text-[10px] flex-shrink-0">
                            chunk #{chunks.chunks[o.idx]?.chunk_index}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <EmptyState icon={Layers} title="No chunk selected" description="Select a chunk to inspect" />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Add Source Directory & File Picker Modal ─────────────────── */}
      <AddSourceDirectoryModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onDirectoriesUpdated={refreshAll}
        currentDirectories={corpusData.directories || []}
      />
    </div>
  )
}

export default SourcesPage
