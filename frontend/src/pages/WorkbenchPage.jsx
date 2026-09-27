import { useState, useEffect, useMemo, useRef } from 'react'
import { useSearchParams, useParams } from 'react-router-dom'
import { CHAT_TABS } from '../lib/nav'
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
import { PlanGraphView } from '../components/plan/PlanGraphView'
import { AgentMapContent } from '../integrations/agent-map/AgentMap'
import { Link } from 'react-router-dom'
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

  // THE URL SAYS WHICH CHAT AND WHICH TAB (lib/nav.js). Back, forward and
  // refresh change the URL; the store follows it -- never the reverse.
  const { sessionId: routeSessionId } = useParams()
  const openSession = useChatStore((s) => s.openSession)
  const setActiveTab = useChatStore((s) => s.setActiveTab)
  const routeTab = searchParams.get('tab')
  useEffect(() => {
    if (routeSessionId) openSession(routeSessionId)
  }, [routeSessionId, openSession])
  useEffect(() => {
    setActiveTab(CHAT_TABS.includes(routeTab) ? routeTab : 'chat')
  }, [routeTab, setActiveTab])
  const plan = useChatStore((s) => s.plan) || []
  const setActiveDocuments = useChatStore((s) => s.setActiveDocuments)
  const sourcesEnabled = useChatStore((s) => s.sourcesEnabled)
  const toggleSourcesEnabled = useChatStore((s) => s.toggleSourcesEnabled)
  const openPreview = usePreviewStore((s) => s.openPreview)
  const panels = useWorkspaceStore((s) => s.panels)
  const { openPanel, focusPanel, toggleCollapse } = useWorkspaceStore()

  // Sources state. The corpus as the backend lists it; which files are ON
  // is this chat's own selection (chatStore.disabledSources), applied below.
  const [corpusTree, setTree] = useState([])
  const [corpusSources, setSources] = useState([])
  const disabledSources = useChatStore((s) => s.disabledSources)
  const setDisabledSources = useChatStore((s) => s.setDisabledSources)
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

  // ── This chat's attachments: sources of this chat only ──────────────────
  // Listed at the top of the tree for the chat that owns them and nowhere
  // else; they switch on and off like any source (per chat, by full path).
  const chatSessionId = useChatStore((s) => s.sessionId)
  const [chatAttachments, setChatAttachments] = useState([])
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`/api/chat-attachments?session_id=${encodeURIComponent(chatSessionId)}`)
        .then((r) => (r.ok ? r.json() : { attachments: [] }))
        .then((d) => alive && setChatAttachments(d.attachments || []))
        .catch(() => alive && setChatAttachments([]))
    load()
    window.addEventListener('chat-attachments-changed', load)
    return () => {
      alive = false
      window.removeEventListener('chat-attachments-changed', load)
    }
  }, [chatSessionId])
  const attachmentItems = useMemo(
    () =>
      chatAttachments.map((a) => ({
        ...a,
        corpus: 'This chat',
        folder: 'Attached in this chat',
        relPath: a.name,
        category: 'documents',
        subcategory: 'attachments',
        isFile: true,
      })),
    [chatAttachments],
  )

  // A file's identity is its full path: two files may share a name (and the
  // toggle used to flip every file of the same name at once).
  const keyOf = (n) => n?.fullPath || n?.id || ''

  // This chat's selection applied to the corpus: the list and the tree the
  // panel shows, re-derived when the chat changes or the corpus reloads.
  const { sources, tree } = useMemo(() => {
    const off = new Set(disabledSources)
    const sourcesOut = [...attachmentItems, ...corpusSources].map((s) => ({ ...s, enabled: !off.has(keyOf(s)) }))
    const mark = (nodes) =>
      (nodes || []).map((n) => {
        if (n.type === 'directory') {
          const children = mark(n.children)
          const files = children.filter((c) => c.type !== 'directory' || c.children?.length)
          // a folder is ON while anything in it is on
          return { ...n, children, enabled: files.length === 0 || children.some((c) => c.enabled !== false) }
        }
        return { ...n, enabled: !off.has(keyOf(n)) }
      })
    const attachmentsRoot = attachmentItems.length
      ? [{
          id: 'chat_attachments_root',
          name: 'Attached in this chat',
          fullPath: 'This chat only',
          type: 'directory',
          isRoot: true,
          isPreset: false,
          fileCount: attachmentItems.length,
          children: attachmentItems,
        }]
      : []
    return { sources: sourcesOut, tree: mark([...attachmentsRoot, ...corpusTree]) }
  }, [corpusSources, corpusTree, disabledSources, attachmentItems]) // eslint-disable-line react-hooks/exhaustive-deps

  // What the next question may search. null = no filter (every file on:
  // nothing to confine, and the backend skips the filtering work); a list =
  // only these. setActiveDocuments is called only here.
  useEffect(() => {
    if (corpusSources.length === 0 && attachmentItems.length === 0) return
    if (disabledSources.length === 0) {
      setActiveDocuments(null)
      return
    }
    const enabled = sources.filter((s) => s.enabled).map((s) => s.name).filter(Boolean)
    setActiveDocuments(Array.from(new Set(enabled)))
  }, [sources]) // eslint-disable-line react-hooks/exhaustive-deps

  // Per-file / per-folder On/Off switch: updates THIS chat's selection, which
  // is saved with the chat at once.
  const handleToggleSource = (id, explicitEnabled, node) => {
    const target = node || corpusSources.find((s) => s.id === id)
    if (!target) return
    const keys = []
    const collect = (n) => {
      if (n.type === 'directory') (n.children || []).forEach(collect)
      else keys.push(keyOf(n))
    }
    collect(target)
    const off = new Set(disabledSources)
    const turnOn = explicitEnabled !== undefined ? explicitEnabled : keys.some((k) => off.has(k))
    keys.forEach((k) => (turnOn ? off.delete(k) : off.add(k)))
    setDisabledSources([...off])
  }

  useEffect(() => {
    fetchCorpus()
  }, [])

  // The chat's paperclip menu ("Add source directory") sends this event.
  // Only the old Sidebar -- no longer rendered -- listened for it, so the
  // menu item did nothing.
  useEffect(() => {
    const open = () => setIsAddDirModalOpen(true)
    window.addEventListener('open-add-source-modal', open)
    return () => window.removeEventListener('open-add-source-modal', open)
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

  // ── Plan & Agents: the Plan DAG and the agent map in one floating panel ──
  // Draggable by its header, beside the chat. The plan shown is the running
  // turn's, else the latest finished turn's (kept with the chat).
  const chatMessages = useChatStore((s) => s.messages)
  const setPanelTab = useWorkspaceStore((s) => s.setPanelTab)
  const shownPlan = plan.length
    ? plan
    : [...(chatMessages || [])].reverse().find((m) => m.role === 'assistant' && m.plan?.length)?.plan || []
  const orchestrationTab = panels.orchestration?.tab || 'plan'
  const orchestrationContent = panels.orchestration?.isOpen && (
    <WorkspacePanel
      id="orchestration"
      title="Plan & Agents"
      icon={Network}
      badge={shownPlan.length ? `${shownPlan.filter((s) => s.status === 'done').length}/${shownPlan.length} steps` : 'No plan yet'}
      badgeTone="accent"
      isFloating={true}
      style={{
        left: panels.orchestration.floatingPos?.x ?? 860,
        top: panels.orchestration.floatingPos?.y ?? 76,
        width: panels.orchestration.width || 560,
        height: panels.orchestration.height || 560,
      }}
    >
      <div className="flex-1 h-full w-full flex flex-col min-h-0">
        <div className="flex items-center gap-1 px-3 py-2 border-b" style={{ borderColor: 'var(--color-border)' }}>
          {[['plan', 'Plan DAG'], ['agents', 'Agent map']].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setPanelTab('orchestration', id)}
              className="px-3 py-1 rounded-md text-[11px] font-semibold cursor-pointer transition-colors"
              style={{
                background: orchestrationTab === id ? 'var(--color-accent-tint)' : 'transparent',
                color: orchestrationTab === id ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
            >
              {label}
            </button>
          ))}
          {orchestrationTab === 'plan' && (
            <Link
              to={`/plan/${encodeURIComponent(chatSessionId)}`}
              className="ml-auto text-[11px] font-medium hover:underline"
              style={{ color: 'var(--color-text-muted)' }}
              title="Open the Plan DAG full screen"
            >
              Full screen
            </Link>
          )}
        </div>
        <div className="flex-1 min-h-0 relative">
          {orchestrationTab === 'plan' ? (
            shownPlan.length ? (
              <PlanGraphView plan={shownPlan} />
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-center px-8" style={{ color: 'var(--color-text-muted)' }}>
                Ask something that needs several steps and its plan appears here as it runs.
              </div>
            )
          ) : (
            <div className="h-full overflow-auto">
              <AgentMapContent compact />
            </div>
          )}
        </div>
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
        orchestrationContent={orchestrationContent}
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
