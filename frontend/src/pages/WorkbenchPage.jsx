import { useState, useEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FolderSearch,
  MessageSquare,
  Network,
  ShieldCheck,
  Plus,
  Filter,
  RefreshCw,
  Search,
  SlidersHorizontal,
  ExternalLink,
  PanelLeftClose,
  FileText,
  Image as ImageIcon,
  Database,
  X,
} from 'lucide-react'
import { WorkspaceCanvas } from '../components/spatial/WorkspaceCanvas'
import { WorkspacePanel } from '../components/spatial/WorkspacePanel'
import { ChatPane } from '../components/workbench/ChatPane'
import { SourceFileTree } from '../components/workbench/SourceFileTree'
import { MinimalistCollapsedSourcesRail } from '../components/workbench/MinimalistCollapsedSourcesRail'
import { AddSourceDirectoryModal } from '../components/workbench/AddSourceDirectoryModal'
import { ApprovalModal } from '../components/workbench/ApprovalModal'
import { ForceGraph } from '../components/graph/ForceGraph'
import { NetworkMonitor } from '../integrations/network-monitor'
import { useChatStore } from '../store/chatStore'
import { usePreviewStore } from '../store/previewStore'
import { useWorkspaceStore } from '../store/workspaceStore'
import { showToast } from '../store/toastStore'

export function WorkbenchPage() {
  const [searchParams] = useSearchParams()
  const plan = useChatStore((s) => s.plan) || []
  const setActiveDocuments = useChatStore((s) => s.setActiveDocuments)
  const sourcesEnabled = useChatStore((s) => s.sourcesEnabled)
  const toggleSourcesEnabled = useChatStore((s) => s.toggleSourcesEnabled)
  const openPreview = usePreviewStore((s) => s.openPreview)
  const panels = useWorkspaceStore((s) => s.panels)
  const { openPanel, focusPanel, toggleCollapse } = useWorkspaceStore()

  // Sources state
  const [tree, setTree] = useState([])
  const [sources, setSources] = useState([])
  const [directories, setDirectories] = useState([])
  const [totalSizeDisplay, setTotalSizeDisplay] = useState(null)
  const [sourcesCategory, setSourcesCategory] = useState('all')
  const [sourcesSearch, setSourcesSearch] = useState('')
  const [isAddDirModalOpen, setIsAddDirModalOpen] = useState(false)
  const [isRefreshingSources, setIsRefreshingSources] = useState(false)
  const [isFilterOpen, setIsFilterOpen] = useState(false)
  const filterMenuRef = useRef(null)

  // Knowledge graph floating state
  const [graphData, setGraphData] = useState(null)
  const [isGraphLoading, setIsGraphLoading] = useState(false)

  // Fetch corpus sources on mount
  const fetchCorpus = async () => {
    setIsRefreshingSources(true)
    try {
      const res = await fetch('/api/corpus')
      if (res.ok) {
        const data = await res.json()
        const fetchedSources = data.sources || []
        setTree(data.tree || [])
        setSources(fetchedSources)
        setDirectories(data.directories || [])
        setTotalSizeDisplay(data.totalSizeDisplay || null)
      }
    } catch (e) {
      console.warn('Corpus fetch error:', e)
    } finally {
      setIsRefreshingSources(false)
    }
  }

  // ── Authoritative sync: whenever sources changes, push enabled names to chatStore ──
  // This is the ONLY place setActiveDocuments is called, avoiding the anti-pattern
  // of calling it inside a setState updater (which React skips or double-calls).
  useEffect(() => {
    if (sources.length === 0) return
    const enabled = sources
      .filter((s) => s.enabled !== false)
      .map((s) => s.name || s.corpus || s.id || '')
      .filter(Boolean)
    setActiveDocuments(enabled)
  }, [sources]) // eslint-disable-line react-hooks/exhaustive-deps

  // Per-file / per-folder On/Off toggle
  const handleToggleSource = (id, explicitEnabled, node) => {
    const targetName = node?.name
    const targetFullPath = node?.fullPath
    const isDir = node?.type === 'directory'

    // Collect all descendant file names for a directory toggle
    const collectChildNames = (n) => {
      const names = new Set()
      const walk = (children) => {
        if (!Array.isArray(children)) return
        children.forEach((c) => {
          if (c.type !== 'directory') names.add(c.name)
          if (c.children) walk(c.children)
        })
      }
      walk(n?.children || [])
      return names
    }
    const childNames = isDir ? collectChildNames(node) : new Set()

    // ── Update sources flat list ──
    setSources((prev) =>
      prev.map((s) => {
        const isDirectMatch =
          s.id === id ||
          (targetName && s.name === targetName) ||
          (targetFullPath && s.fullPath === targetFullPath)
        const isChildMatch = isDir && childNames.has(s.name)
        if (isDirectMatch || isChildMatch) {
          const nextEnabled = explicitEnabled !== undefined ? explicitEnabled : !s.enabled
          return { ...s, enabled: nextEnabled }
        }
        return s
      })
    )

    // ── Update tree nodes ──
    const updateNodes = (nodes) => {
      if (!Array.isArray(nodes)) return nodes
      return nodes.map((n) => {
        const isMatch =
          n.id === id ||
          (targetName && n.name === targetName) ||
          (targetFullPath && n.fullPath === targetFullPath)
        const nextEnabled = explicitEnabled !== undefined ? explicitEnabled : !(n.enabled !== false)
        let updated = isMatch ? { ...n, enabled: nextEnabled } : n
        if (isMatch && n.type === 'directory') {
          // Cascade enabled state to all children in tree
          const cascadeTree = (children) => {
            if (!Array.isArray(children)) return children
            return children.map((c) => {
              const c2 = { ...c, enabled: nextEnabled }
              if (c2.children) c2.children = cascadeTree(c2.children)
              return c2
            })
          }
          updated.children = cascadeTree(n.children || [])
        } else if (updated.children) {
          updated = { ...updated, children: updateNodes(updated.children) }
        }
        return updated
      })
    }
    setTree((prev) => updateNodes(prev))
  }

  useEffect(() => {
    fetchCorpus()
  }, [])

  // Fetch graph if floating graph panel is open
  useEffect(() => {
    if (panels.graph?.isOpen && !graphData && !isGraphLoading) {
      setIsGraphLoading(true)
      fetch('/api/graph')
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => setGraphData(d))
        .catch(() => {})
        .finally(() => setIsGraphLoading(false))
    }
  }, [panels.graph?.isOpen, graphData, isGraphLoading])

  // Close filter menu on click outside
  useEffect(() => {
    if (!isFilterOpen) return
    const handleClickOutside = (e) => {
      if (filterMenuRef.current && !filterMenuRef.current.contains(e.target)) {
        setIsFilterOpen(false)
      }
    }
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setIsFilterOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isFilterOpen])

  // Category counts
  const categoryCounts = useMemo(() => {
    let documents = 0, drawings = 0, data = 0
    for (const s of sources) {
      const ext = (s.type || (s.name || '').split('.').pop() || '').toUpperCase()
      if (['PDF', 'DOCX', 'DOC', 'TXT', 'MD', 'MARKDOWN'].includes(ext) || s.category === 'documents') {
        documents++
      } else if (['P&ID', 'PNG', 'JPG', 'JPEG', 'SVG', 'SCAN'].includes(ext) || s.category === 'charts') {
        drawings++
      } else if (['XLSX', 'XLS', 'CSV', 'JSON', 'PARQUET'].includes(ext) || s.category === 'data') {
        data++
      } else {
        documents++
      }
    }
    return { all: sources.length, documents, drawings, data }
  }, [sources])

  // Filter sources
  const filteredSources = useMemo(() => {
    return sources.filter((s) => {
      const ext = (s.type || (s.name || '').split('.').pop() || '').toUpperCase()
      const matchesCategory =
        sourcesCategory === 'all' ||
        (sourcesCategory === 'documents' && (['PDF', 'DOCX', 'DOC', 'TXT', 'MD', 'MARKDOWN'].includes(ext) || s.category === 'documents')) ||
        (sourcesCategory === 'drawings' && (['P&ID', 'PNG', 'JPG', 'JPEG', 'SVG', 'SCAN'].includes(ext) || s.category === 'charts')) ||
        (sourcesCategory === 'data' && (['XLSX', 'XLS', 'CSV', 'JSON', 'PARQUET'].includes(ext) || s.category === 'data'))

      const matchesSearch =
        !sourcesSearch.trim() ||
        (s.name || '').toLowerCase().includes(sourcesSearch.toLowerCase()) ||
        (s.path || '').toLowerCase().includes(sourcesSearch.toLowerCase())

      return matchesCategory && matchesSearch
    })
  }, [sources, sourcesCategory, sourcesSearch])

  const filterCategoryOptions = [
    { id: 'all', label: 'All Sources', icon: FolderSearch, count: categoryCounts.all, color: 'var(--color-text)' },
    { id: 'documents', label: 'Documents', icon: FileText, count: categoryCounts.documents, color: '#60a5fa' },
    { id: 'drawings', label: 'Drawings & P&ID', icon: ImageIcon, count: categoryCounts.drawings, color: '#fbbf24' },
    { id: 'data', label: 'Data & Sheets', icon: Database, count: categoryCounts.data, color: '#34d399' },
  ]

  // ── 1. Sources Panel Content ──────────────────────────────────────────
  const sourcesContent = (
    <WorkspacePanel
      id="sources"
      title="Sources"
      icon={FolderSearch}
      badge={`${sources.length} files`}
      badgeTone="neutral"
      allowClose={false}
      allowFocus={false}
      allowCollapse={false}
      collapsedContent={
        <MinimalistCollapsedSourcesRail
          sources={sources}
          onExpand={() => toggleCollapse('sources')}
          onAddSource={() => setIsAddDirModalOpen(true)}
        />
      }
      headerActions={
        <div className="flex items-center gap-1 relative">
          {/* 1. Filter Button with Popover */}
          <div className="relative" ref={filterMenuRef}>
            <button
              type="button"
              onClick={() => setIsFilterOpen((prev) => !prev)}
              className={`p-1.5 rounded-lg flex items-center gap-1 transition-fast cursor-pointer ${
                sourcesCategory !== 'all' || isFilterOpen
                  ? 'bg-[var(--color-accent-tint)] text-[var(--color-accent)] font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]'
              }`}
              title={`Filter sources (${sourcesCategory})`}
              aria-label="Filter sources by category"
              aria-expanded={isFilterOpen}
            >
              <Filter size={13} strokeWidth={2.2} />
              {sourcesCategory !== 'all' && (
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
              )}
            </button>

            {/* Popover Dropdown */}
            <AnimatePresence>
              {isFilterOpen && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.94, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.94, y: 4 }}
                  transition={{ duration: 0.14 }}
                  className="absolute right-0 top-full mt-1.5 w-44 rounded-xl shadow-2xl border p-1 z-50 select-none backdrop-blur-md"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="px-2 py-1 text-[9.5px] font-mono uppercase tracking-wider text-[var(--color-text-faint)] border-b border-[var(--color-border)] mb-1">
                    Filter Category
                  </div>
                  {filterCategoryOptions.map((opt) => {
                    const Icon = opt.icon
                    const isActive = sourcesCategory === opt.id
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => {
                          setSourcesCategory(opt.id)
                          setIsFilterOpen(false)
                        }}
                        className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-xs transition-fast cursor-pointer ${
                          isActive
                            ? 'bg-[var(--color-overlay)] text-[var(--color-accent)] font-semibold'
                            : 'text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon size={13} strokeWidth={2} style={{ color: opt.color }} />
                          <span className="truncate text-[11.5px]">{opt.label}</span>
                        </div>
                        <span
                          className="text-[9.5px] font-mono px-1.5 py-0.2 rounded font-medium ml-1 border"
                          style={{
                            background: isActive ? 'var(--color-accent-tint)' : 'var(--color-overlay)',
                            borderColor: isActive ? 'var(--color-accent-border)' : 'var(--color-border)',
                            color: isActive ? 'var(--color-accent)' : 'var(--color-text-muted)',
                          }}
                        >
                          {opt.count}
                        </span>
                      </button>
                    )
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* 2. Add local folder "+" button */}
          <button
            type="button"
            onClick={() => setIsAddDirModalOpen(true)}
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
            title="Add local source directory to corpus"
            aria-label="Add local source directory"
          >
            <Plus size={14} strokeWidth={2.2} />
          </button>

          {/* 3. Refresh button */}
          <button
            type="button"
            onClick={fetchCorpus}
            className={`p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer ${
              isRefreshingSources ? 'animate-spin text-[var(--color-accent)]' : ''
            }`}
            title="Rescan watched sources"
            aria-label="Rescan watched sources"
          >
            <RefreshCw size={13} strokeWidth={2} />
          </button>

          {/* 4. Collapse button (docks to rail) */}
          <button
            type="button"
            onClick={() => toggleCollapse('sources')}
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-accent)] hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
            title="Collapse Sources panel (dock to rail)"
            aria-label="Collapse Sources panel"
          >
            <PanelLeftClose size={14} strokeWidth={2.2} />
          </button>
        </div>
      }
    >
      <div className="flex flex-col h-full overflow-hidden select-none">
        {/* Subtle Grounding Trust Indicator & Source On/Off Switch */}
        <div className="px-3 pt-2 pb-1.5 flex items-center justify-between text-[11px] select-none">
          <div className="flex items-center gap-1.5 truncate">
            {sourcesEnabled ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] shrink-0 animate-pulse" />
                <span className="truncate text-[var(--color-text-muted)]">Grounded strictly in local sources</span>
              </>
            ) : (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                <span className="truncate text-amber-400/90 font-medium">Sources OFF · General reasoning</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="font-mono text-[10px] text-[var(--color-text-faint)]">
              {totalSizeDisplay || '—'}
            </span>
            {/* Seamless Toggle Switch */}
            <button
              type="button"
              onClick={toggleSourcesEnabled}
              className={`relative inline-flex h-4 w-7.5 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus:outline-none ${
                sourcesEnabled
                  ? 'bg-emerald-500/85 hover:bg-emerald-500'
                  : 'bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-text-muted)]'
              }`}
              title={
                sourcesEnabled
                  ? 'Sources ON: LLM considers and cites local documents before answering. Click to toggle OFF.'
                  : 'Sources OFF: LLM bypasses local documents and answers from general knowledge. Click to toggle ON.'
              }
              aria-label="Toggle sources consideration"
            >
              <span
                className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform duration-200 shadow-xs ${
                  sourcesEnabled ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Minimalist Notice when sources are switched OFF */}
        {!sourcesEnabled && (
          <div className="mx-3 my-1 px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-between text-[11px] text-amber-300/90 animate-fade-in">
            <span className="truncate">Sources bypassed — LLM uses general knowledge</span>
            <button
              type="button"
              onClick={toggleSourcesEnabled}
              className="text-[10px] font-semibold text-amber-300 hover:text-amber-100 underline shrink-0 ml-2 cursor-pointer"
            >
              Turn ON
            </button>
          </div>
        )}

        {/* Minimalist Search Bar (No Cramped Pill Row) */}
        <div className="px-3 py-1.5">
          <div className="relative flex items-center">
            <Search size={12} className="absolute left-2.5 text-[var(--color-text-muted)] pointer-events-none" />
            <input
              type="text"
              value={sourcesSearch}
              onChange={(e) => setSourcesSearch(e.target.value)}
              placeholder="Filter sources..."
              className="w-full pl-7 pr-7 py-1 text-xs rounded-lg outline-none transition-all placeholder:text-[var(--color-text-faint)]"
              style={{
                background: 'var(--color-overlay)',
                border: '1px solid transparent',
                color: 'var(--color-text)',
              }}
              onFocus={(e) => (e.target.style.borderColor = 'var(--color-accent-border)')}
              onBlur={(e) => (e.target.style.borderColor = 'transparent')}
            />
            {sourcesSearch && (
              <button
                type="button"
                onClick={() => setSourcesSearch('')}
                className="absolute right-2 text-[var(--color-text-faint)] hover:text-[var(--color-text)] transition-colors p-0.5 cursor-pointer"
                title="Clear search"
              >
                <X size={11} />
              </button>
            )}
          </div>

          {sourcesCategory !== 'all' && (
            <div className="flex items-center justify-between mt-1 px-1 text-[10.5px]">
              <span className="text-[var(--color-text-muted)] flex items-center gap-1">
                Category: <span className="font-semibold text-[var(--color-accent)] capitalize">{sourcesCategory}</span>
              </span>
              <button
                type="button"
                onClick={() => setSourcesCategory('all')}
                className="text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] underline cursor-pointer"
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {/* Tree & File List with Preserved Branches & Clean Spacing */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {filteredSources.length === 0 ? (
            <div className="py-12 text-center text-xs text-[var(--color-text-muted)]">
              No matching sources found.
            </div>
          ) : (
            <SourceFileTree
              tree={tree}
              sources={filteredSources}
              directories={directories}
              filterCategory={sourcesCategory}
              searchQuery={sourcesSearch}
              onDirectoryChange={fetchCorpus}
              onSelectSource={(node) => openPreview(node)}
              onToggleSource={handleToggleSource}
            />
          )}
        </div>
      </div>
    </WorkspacePanel>
  )

  // ── 2. Chat Stream Panel Content ───────────────────────────────────────
  const chatContent = (
    <WorkspacePanel
      id="chat"
      title="Intelligence Stream"
      icon={MessageSquare}
      badge="Zero-Egress"
      badgeTone="success"
      showHeader={false}
      allowClose={false}
      allowCollapse={false}
      className="flex-1"
    >
      <ChatPane />
    </WorkspacePanel>
  )

  // ── 3. Floating Knowledge Graph Panel ──────────────────────────────────
  const graphContent = panels.graph?.isOpen && (
    <WorkspacePanel
      id="graph"
      title="Knowledge Graph"
      icon={Network}
      badge={graphData?.nodes ? `${graphData.nodes.length} entities` : 'Connecting...'}
      badgeTone="accent"
      isFloating={true}
      style={{
        left: panels.graph.floatingPos?.x || 380,
        top: panels.graph.floatingPos?.y || 80,
        width: panels.graph.width || 560,
        height: panels.graph.height || 460,
      }}
    >
      <div className="flex-1 h-full w-full relative overflow-hidden flex flex-col">
        {isGraphLoading && !graphData ? (
          <div className="flex-1 flex items-center justify-center text-xs text-[var(--color-text-muted)]">
            Traversing Neo4j knowledge graph...
          </div>
        ) : graphData?.nodes ? (
          <ForceGraph
            nodes={graphData.nodes || []}
            relationships={graphData.relationships || []}
            data={graphData}
            height={
              panels.graph?.isFocused
                ? (typeof window !== 'undefined' ? window.innerHeight - 150 : 700)
                : (panels.graph?.height || 460) - 50
            }
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-xs text-[var(--color-text-muted)]">
            Graph data unavailable.
          </div>
        )}
      </div>
    </WorkspacePanel>
  )

  // ── 4. Floating Network Monitor Panel ──────────────────────────────────
  const monitorContent = panels.monitor?.isOpen && (
    <WorkspacePanel
      id="monitor"
      title="Air-Gap & Socket Monitor"
      icon={ShieldCheck}
      badge="Verified"
      badgeTone="success"
      isFloating={true}
      style={{
        left: panels.monitor.floatingPos?.x || 420,
        top: panels.monitor.floatingPos?.y || 110,
        width: panels.monitor.width || 500,
        height: panels.monitor.height || 440,
      }}
    >
      <div className="flex-1 overflow-y-auto p-4">
        <NetworkMonitor mode={panels.monitor?.isFocused ? 'full' : 'compact'} />
      </div>
    </WorkspacePanel>
  )

  return (
    <div className="flex h-full w-full overflow-hidden relative">
      <WorkspaceCanvas
        sourcesContent={sourcesContent}
        chatContent={chatContent}
        graphContent={graphContent}
        monitorContent={monitorContent}
      />

      {/* Human Approval Gate Modal */}
      <ApprovalModal />

      {/* Add Source Directory Modal */}
      <AddSourceDirectoryModal
        isOpen={isAddDirModalOpen}
        onClose={() => setIsAddDirModalOpen(false)}
        onDirectoriesUpdated={() => { fetchCorpus(); setIsAddDirModalOpen(false) }}
      />
    </div>
  )
}
