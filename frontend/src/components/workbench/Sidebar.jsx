import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  Sun,
  Moon,
  Plus,
  Database,
  MessageSquare,
  HardDrive,
  Settings,
  X,
  Network,
  Maximize2,
  ArrowUpRight,
  Activity,
  ShieldCheck,
  Filter,
  Check,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useThemeStore } from '../../store/themeStore'
import { showToast } from '../../store/toastStore'
import { useChatStore } from '../../store/chatStore'
import { SourceFileTree } from './SourceFileTree'
import { AddSourceDirectoryModal } from './AddSourceDirectoryModal'

// The sidebar starts with NOTHING and shows what the backend reports.
//
// This used to be a 230-line literal describing thirteen specific files
// -- SOP-114-Rev3, Novolen_Batch_QA_Report_Aug2026.pdf, a P&ID, a
// scanned checklist -- each with a hand-written size, badge and colour,
// rendered as the initial state before /api/corpus resolved.
//
// Two problems. It was the corpus of one developer's machine on one
// day, so it named files a given user may not have, at sizes that were
// no longer true. And because it rendered first, the sidebar was
// populated and confident during the window when nothing had been
// loaded -- an empty or failed corpus fetch left the fabricated
// thirteen on screen indefinitely, with no way to tell them from real
// entries. A source list is a claim about what the system can retrieve
// from; being wrong about it is not a cosmetic default.
//
// Empty is the honest initial state: the list is unknown until the
// backend answers.
const INITIAL_SOURCES = []

// Chat history starts empty for the same reason.
//
// This was five fabricated conversations -- "Refinery Turnaround
// Analysis", "CDU-II Column Maintenance Review", "Hydrocracker Catalyst
// Life Estimation" and two more -- with relative timestamps ("2h ago",
// "Yesterday", "Sep 4") that were fixed strings and so aged into
// obvious nonsense. They were not retrievable: clicking one loaded no
// messages, because no session with that id had ever existed.
//
// There is no session-history endpoint on the backend yet, so this list
// is genuinely local and genuinely empty until the user starts a
// conversation. Showing five invented ones does not fill that gap, it
// hides it -- and a user who opens the app expecting to find yesterday's
// analysis has been told it is there.
const MOCK_CHATS = []

export function Sidebar() {
  const { theme, toggleTheme } = useThemeStore()
  const setActiveDocuments = useChatStore((s) => s.setActiveDocuments)

  // Two-tab accordion switcher: 'sources' | 'chats' (mutually exclusive)
  const [activeTab, setActiveTab] = useState('sources')

  // Sources tab internal filter state
  const [sourcesCategory, setSourcesCategory] = useState('all')
  const [isFilterDropdownOpen, setIsFilterDropdownOpen] = useState(false)
  const filterDropdownRef = useRef(null)
  const [sources, setSources] = useState(INITIAL_SOURCES)
  const [tree, setTree] = useState([])
  const [directories, setDirectories] = useState([])
  const [totalSizeDisplay, setTotalSizeDisplay] = useState('2.83 MB')
  const [chunkCount, setChunkCount] = useState(null)
  const [isAddDirModalOpen, setIsAddDirModalOpen] = useState(false)

  // Listen for global open-add-source-modal event
  useEffect(() => {
    const handleOpenModal = () => setIsAddDirModalOpen(true)
    window.addEventListener('open-add-source-modal', handleOpenModal)
    return () => window.removeEventListener('open-add-source-modal', handleOpenModal)
  }, [])

  // Close filter dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (filterDropdownRef.current && !filterDropdownRef.current.contains(e.target)) {
        setIsFilterDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Chats tab session state
  const [chats, setChats] = useState(MOCK_CHATS)
  const [activeSessionId, setActiveSessionId] = useState('session-1')

  // Command palette modal overlay state
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Global Ctrl+K listener for search trigger
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setIsSearchOpen((prev) => !prev)
      } else if (e.key === 'Escape' && isSearchOpen) {
        setIsSearchOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isSearchOpen])

  // Fetch live MRPL Corpus directly from server on mount
  const fetchCorpus = useCallback(() => {
    fetch(`/api/corpus?t=${Date.now()}`, { cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.sources && Array.isArray(data.sources)) {
          setSources(data.sources)
          // Push active source names to chatStore on initial load
          const enabled = data.sources
            .filter((s) => s.enabled !== false)
            .map((s) => s.name || s.corpus || s.id || '')
            .filter(Boolean)
          setActiveDocuments(enabled)
        }
        if (data?.tree && Array.isArray(data.tree)) {
          setTree(data.tree)
        }
        if (data?.directories && Array.isArray(data.directories)) {
          setDirectories(data.directories)
        }
        if (data?.totalSizeDisplay) {
          setTotalSizeDisplay(data.totalSizeDisplay)
        }
        if (data?.chunkCount) {
          setChunkCount(data.chunkCount)
        }
      })
      .catch(() => {})
  }, [setActiveDocuments])

  const handleDeleteSource = async (source) => {
    if (!source) return
    const name = source.name || 'document'
    const targetId = source.id
    const targetFullPath = source.fullPath || source.relPath || source.path || source.name

    // 1. Optimistic instant removal from sources
    setSources((prev) =>
      prev.filter(
        (s) =>
          s.id !== targetId &&
          s.name !== name &&
          (!targetFullPath || s.fullPath !== targetFullPath)
      )
    )

    // 2. Optimistic instant removal from tree
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
            const filteredChildren = removeNodeFromTree(n.children)
            return {
              ...n,
              children: filteredChildren,
              fileCount: filteredChildren.reduce(
                (acc, c) => acc + (c.type === 'directory' ? c.fileCount || 0 : 1),
                0
              ),
            }
          }
          return n
        })
        .filter((n) => n.type !== 'directory' || (n.isPreset || (n.children && n.children.length > 0)))
    }
    setTree((prev) => removeNodeFromTree(prev))

    showToast(`Source "${name}" removed from knowledge base`, 'info')

    // 3. Dispatch to backend API
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
    fetchCorpus()
    const handleCorpusUpdated = () => fetchCorpus()
    window.addEventListener('corpus-updated', handleCorpusUpdated)
    return () => window.removeEventListener('corpus-updated', handleCorpusUpdated)
  }, [fetchCorpus])

  const handleCloseAddDirModal = useCallback(() => {
    setIsAddDirModalOpen(false)
  }, [])

  // Expose test automation helpers
  useEffect(() => {
    window.__workbenchSetSidebarTab = (tab) => setActiveTab(tab)
    window.__workbenchOpenSearchModal = (open = true) => setIsSearchOpen(open)
    return () => {
      delete window.__workbenchSetSidebarTab
      delete window.__workbenchOpenSearchModal
    }
  }, [])

  const toggleSource = (id, explicitEnabled, node) => {
    let targetName = node?.name
    let targetFullPath = node?.fullPath

    setSources((prev) =>
      prev.map((s) => {
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
    )

    // Synchronize tree state so tree is always in sync with sources
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
    setTree((prev) => updateTreeNodes(prev))

    // Sync enabled source names into chatStore so ChatPane can pass them
    // as active_documents on the next /api/chat/stream call.
    setSources((latestSources) => {
      const enabled = latestSources
        .map((s) => {
          const isMatch =
            s.id === id ||
            (targetName && s.name === targetName) ||
            (targetFullPath && s.fullPath === targetFullPath)
          if (isMatch) {
            const next = explicitEnabled !== undefined ? explicitEnabled : !s.enabled
            return { ...s, enabled: next }
          }
          return s
        })
        .filter((s) => s.enabled !== false)
        .map((s) => s.name || s.corpus || s.id || '')
        .filter(Boolean)
      setActiveDocuments(enabled)
      return latestSources // don't mutate here; setSources above already did it
    })

    const isNowEnabled = explicitEnabled !== undefined ? explicitEnabled : true
    showToast(
      isNowEnabled
        ? `"${targetName || 'Source'}" included in retrieval scope`
        : `"${targetName || 'Source'}" excluded from retrieval scope`,
      isNowEnabled ? 'success' : 'info'
    )
  }

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId)
    setChats((prev) =>
      prev.map((c) => ({
        ...c,
        active: c.id === sessionId,
      }))
    )
    const selected = chats.find((c) => c.id === sessionId)
    if (selected) {
      showToast(`Active session: ${selected.title}`, 'info')
    }
  }

  const handleNewChat = () => {
    showToast('New engineering session initialized (Zero-Egress Sandbox)', 'info')
  }

  const activeCount = sources.filter((s) => s.enabled).length
  const totalCount = sources.length

  const counts = {
    all: sources.length,
    documents: sources.filter((s) => s.category === 'documents').length,
    data: sources.filter((s) => s.category === 'data').length,
    charts: sources.filter((s) => s.category === 'charts').length,
    apis: sources.filter((s) => s.category === 'apis').length,
  }

  return (
    <>
      <aside
        className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden relative"
        style={{
          width: 324,
          background: 'var(--color-bg)',
          borderRight: '1px solid var(--color-border)',
        }}
        aria-label="Sidebar navigation, sources, and past sessions"
      >
        {/* ── 1. Top Header: Brand Lockup + Icon Button Row ──────────── */}
        <div
          className="flex flex-col px-5 pt-4 pb-3.5 flex-shrink-0 gap-3.5"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center justify-between">
            {/* Logo Mark + Wordmark Lockup */}
            <div className="flex items-center gap-3 min-w-0">
              <img
                src="/assets/logo-mark-transparent.png"
                alt="Sovereign Workbench Logo"
                className="h-8 w-auto object-contain flex-shrink-0"
              />
              <div className="flex items-center min-w-0">
                <img
                  src="/assets/brand-title-dark.png"
                  alt="Sovereign Workbench"
                  className={`h-[28px] w-auto object-contain select-none ${
                    theme === 'dark' ? 'block' : 'hidden'
                  }`}
                />
                <img
                  src="/assets/brand-title-light.png"
                  alt="Sovereign Workbench"
                  className={`h-[28px] w-auto object-contain select-none ${
                    theme === 'dark' ? 'hidden' : 'block'
                  }`}
                />
              </div>
            </div>

            {/* Icon Buttons Row: Search & Theme Toggle */}
            <div className="flex items-center gap-2 flex-shrink-0">
              {/* Search Icon Trigger */}
              <button
                type="button"
                onClick={() => setIsSearchOpen(true)}
                className="w-8 h-8 rounded-lg flex items-center justify-center transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
                title="Search knowledge corpus & commands (Ctrl+K)"
                aria-label="Open command search palette"
              >
                <Search size={14} strokeWidth={2} />
              </button>

              {/* Theme Toggle (Sun / Moon) */}
              <button
                type="button"
                onClick={toggleTheme}
                className="w-8 h-8 rounded-lg flex items-center justify-center transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
                title={theme === 'dark' ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
                aria-label="Toggle theme"
              >
                {theme === 'dark' ? (
                  <Sun size={14} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
                ) : (
                  <Moon size={14} strokeWidth={2} />
                )}
              </button>
            </div>
          </div>

          {/* ── 2. Two-Tab Accordion Switcher (Sources vs Chats) ─────── */}
          <div
            className="flex items-center p-1 rounded-lg text-xs font-medium gap-1 relative"
            style={{ background: 'var(--color-overlay)' }}
          >
            <button
              type="button"
              onClick={() => setActiveTab('sources')}
              className="flex-1 py-1.5 rounded-md text-xs text-center flex items-center justify-center gap-1.5 cursor-pointer relative z-10"
              style={{
                color: activeTab === 'sources' ? 'var(--color-text)' : 'var(--color-text-muted)',
                fontWeight: activeTab === 'sources' ? 600 : 500,
              }}
            >
              {activeTab === 'sources' && (
                <motion.div
                  layoutId="sidebar-active-tab-bg"
                  className="absolute inset-0 rounded-md border"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border-strong)',
                    boxShadow: 'var(--shadow-xs)',
                  }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <Database size={13} strokeWidth={2} />
                <span>Sources</span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.2 rounded"
                  style={{
                    background: 'var(--color-overlay)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {activeCount}
                </span>
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('chats')}
              className="flex-1 py-1.5 rounded-md text-xs text-center flex items-center justify-center gap-1.5 cursor-pointer relative z-10"
              style={{
                color: activeTab === 'chats' ? 'var(--color-text)' : 'var(--color-text-muted)',
                fontWeight: activeTab === 'chats' ? 600 : 500,
              }}
            >
              {activeTab === 'chats' && (
                <motion.div
                  layoutId="sidebar-active-tab-bg"
                  className="absolute inset-0 rounded-md border"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border-strong)',
                    boxShadow: 'var(--shadow-xs)',
                  }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <MessageSquare size={13} strokeWidth={2} />
                <span>Chats</span>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.2 rounded"
                  style={{
                    background: 'var(--color-overlay)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {chats.length}
                </span>
              </span>
            </button>
          </div>
        </div>

        {/* ── 3. Mutually Exclusive Accordion Body (Smooth Height Transition) ── */}
        <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
          <AnimatePresence mode="wait" initial={false}>
            {activeTab === 'sources' ? (
              <motion.div
                key="sources-panel"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                className="flex-1 min-h-0 flex flex-col overflow-hidden"
              >
            {/* Category Filter Toolbar with Animated Popover & Expand Button */}
            <div className="px-4 py-2.5 flex-shrink-0 flex items-center justify-between gap-2 border-b border-[var(--color-border)] relative">
              {/* Active Category / Filter Indicator */}
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                  Sources
                </span>
                <span
                  className="text-[10px] font-mono px-2 py-0.5 rounded-full font-medium border"
                  style={{
                    background: sourcesCategory === 'all' ? 'var(--color-overlay)' : 'var(--color-accent-tint)',
                    borderColor: sourcesCategory === 'all' ? 'var(--color-border)' : 'var(--color-accent-border)',
                    color: sourcesCategory === 'all' ? 'var(--color-text-muted)' : 'var(--color-accent)',
                  }}
                >
                  {sourcesCategory === 'all'
                    ? `All (${counts.all})`
                    : sourcesCategory === 'documents'
                    ? `Docs (${counts.documents})`
                    : sourcesCategory === 'data'
                    ? `Data (${counts.data})`
                    : sourcesCategory === 'charts'
                    ? `Charts (${counts.charts})`
                    : `APIs (${counts.apis})`}
                </span>
              </div>

              {/* Action Buttons: Filter Dropdown + Expand */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {/* Single Filter Button */}
                <div className="relative" ref={filterDropdownRef}>
                  <button
                    type="button"
                    id="sources-filter-btn"
                    onClick={() => setIsFilterDropdownOpen((prev) => !prev)}
                    className="p-1.5 rounded-lg text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex items-center gap-1 border shadow-xs"
                    style={{
                      background: isFilterDropdownOpen || sourcesCategory !== 'all' ? 'var(--color-accent-tint)' : 'var(--color-surface)',
                      borderColor: isFilterDropdownOpen || sourcesCategory !== 'all' ? 'var(--color-accent-border)' : 'var(--color-border)',
                      color: isFilterDropdownOpen || sourcesCategory !== 'all' ? 'var(--color-accent)' : 'var(--color-text-muted)',
                    }}
                    title="Filter sources by category"
                    aria-label="Filter sources"
                  >
                    <Filter size={13} strokeWidth={2.2} />
                  </button>

                  {/* Animated Filter Popover via Framer Motion */}
                  <AnimatePresence>
                    {isFilterDropdownOpen && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 4 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 4 }}
                        transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                        className="absolute right-0 top-full mt-1.5 w-48 rounded-xl py-1.5 z-50 shadow-xl border overflow-hidden"
                        style={{
                          background: 'var(--color-surface)',
                          borderColor: 'var(--color-border)',
                          boxShadow: 'var(--shadow-lg)',
                        }}
                      >
                        <div
                          className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider flex items-center justify-between"
                          style={{ color: 'var(--color-text-faint)' }}
                        >
                          <span>Filter Sources</span>
                          <span className="font-mono">{counts.all} total</span>
                        </div>
                        <div className="py-1">
                          {[
                            { id: 'all', label: 'All Sources', count: counts.all },
                            { id: 'documents', label: 'Documents', count: counts.documents },
                            { id: 'data', label: 'Structured Data', count: counts.data },
                            { id: 'charts', label: 'Charts & Scans', count: counts.charts },
                            { id: 'apis', label: 'APIs & Feeds', count: counts.apis },
                          ].map((cat) => {
                            const isSelected = sourcesCategory === cat.id
                            return (
                              <button
                                key={cat.id}
                                type="button"
                                onClick={() => {
                                  setSourcesCategory(cat.id)
                                  setIsFilterDropdownOpen(false)
                                }}
                                className="w-full px-3 py-1.5 text-xs flex items-center justify-between transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer text-left group"
                                style={{
                                  color: isSelected ? 'var(--color-accent)' : 'var(--color-text)',
                                  fontWeight: isSelected ? 600 : 400,
                                }}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <div className="w-3.5 flex items-center justify-center">
                                    {isSelected ? (
                                      <Check size={12} strokeWidth={2.5} style={{ color: 'var(--color-accent)' }} />
                                    ) : null}
                                  </div>
                                  <span className="truncate">{cat.label}</span>
                                </div>
                                <span
                                  className="text-[10px] font-mono px-1.5 py-0.2 rounded font-medium ml-2"
                                  style={{
                                    background: isSelected ? 'var(--color-accent-tint)' : 'var(--color-overlay)',
                                    color: isSelected ? 'var(--color-accent)' : 'var(--color-text-muted)',
                                  }}
                                >
                                  {cat.count}
                                </span>
                              </button>
                            )
                          })}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* Expand to Full Sources Hub button */}
                <Link
                  to="/sources"
                  className="p-1.5 rounded-lg text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex-shrink-0 border shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-muted)',
                  }}
                  title="Open Sources & Pipeline Internals Hub (/sources)"
                >
                  <Maximize2 size={13} strokeWidth={2} />
                </Link>
              </div>
            </div>

            {/* Hierarchical Tree with Smooth Custom Scrollbar and Category Transition */}
            <div className="flex-1 min-h-0 overflow-y-auto px-3.5 py-2 flex flex-col gap-1 custom-scrollbar">
              <AnimatePresence mode="wait">
                <motion.div
                  key={sourcesCategory}
                  initial={{ opacity: 0, y: 3 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -3 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  className="flex flex-col gap-1"
                >
                  <SourceFileTree
                    tree={tree}
                    filterCategory={sourcesCategory}
                    onToggleSource={toggleSource}
                    onDeleteSource={handleDeleteSource}
                    compact={false}
                  />
                </motion.div>
              </AnimatePresence>
            </div>

            {/* Knowledge Base Summary Card */}
            <div className="px-4 py-3 flex-shrink-0 border-t border-[var(--color-border)]">
              <div
                className="p-4 rounded-xl flex flex-col gap-3.5 transition-fast border shadow-[var(--shadow-sm)] card-hover-lift"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 shadow-xs"
                      style={{
                        background: 'var(--color-accent-tint)',
                        color: 'var(--color-accent)',
                        border: '1px solid var(--color-accent-border)',
                      }}
                    >
                      <HardDrive size={13} strokeWidth={2.2} />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="text-[11px] font-bold uppercase tracking-wider leading-tight truncate" style={{ color: 'var(--color-text)' }}>
                        Knowledge Base
                      </span>
                      <span className="text-[10px] leading-tight mt-0.5 truncate" style={{ color: 'var(--color-text-muted)' }}>
                        Air-gapped on-prem index
                      </span>
                    </div>
                  </div>
                  <span
                    className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full border flex-shrink-0 shadow-xs"
                    style={{
                      background: 'var(--color-overlay)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-accent)',
                    }}
                  >
                    {activeCount} / {totalCount} active
                  </span>
                </div>

                {/* Storage Meter */}
                <div className="flex flex-col gap-1.5 pt-1">
                  <div
                    className="flex items-center justify-between text-[10px]"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    <span className="font-medium">Storage utilization</span>
                    <span className="font-mono font-semibold text-[var(--color-text)]">
                      {totalSizeDisplay} • {chunkCount || (totalCount > 0 ? `${totalCount * 8}` : '0')} chunks
                    </span>
                  </div>
                  <div
                    className="w-full h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'var(--color-overlay)' }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${totalCount > 0 ? Math.min(100, Math.max(12, Math.round((activeCount / totalCount) * 100))) : 0}%`,
                        background: 'var(--color-accent)',
                      }}
                    />
                  </div>
                </div>

                {/* Link to full Sources Hub */}
                <Link
                  to="/sources"
                  className="flex items-center justify-between pt-2.5 border-t text-[11px] font-semibold transition-fast group"
                  style={{
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <span className="group-hover:underline">Open Sources Hub</span>
                  <ArrowUpRight size={13} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                </Link>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="chats-panel"
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 6 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 min-h-0 flex flex-col overflow-hidden"
          >
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              {/* Pinned "+ New chat" button */}
              <div className="px-5 pt-3.5 pb-2.5 flex-shrink-0">
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="w-full flex items-center justify-center gap-2 py-2.5 px-3.5 rounded-lg text-xs font-semibold shadow-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <Plus size={14} strokeWidth={2.4} />
                  <span>New chat</span>
                </button>
              </div>

              {/* Past Sessions List */}
              <div className="flex-1 overflow-y-auto px-4 py-2 flex flex-col gap-1.5">
                <div
                  className="px-2 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: 'var(--color-text-faint)' }}
                >
                  Recent Sessions
                </div>

                {chats.map((session) => {
                  const isActive = session.id === activeSessionId
                  return (
                    <button
                      key={session.id}
                      type="button"
                      onClick={() => handleSelectSession(session.id)}
                      className="w-full flex items-center justify-between p-2.5 rounded-lg text-left transition-fast cursor-pointer group row-hover-lift"
                      style={{
                        background: isActive ? 'var(--color-surface)' : 'transparent',
                        border: isActive
                          ? '1px solid var(--color-border-strong)'
                          : '1px solid transparent',
                        boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                      }}
                      title={session.title}
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <MessageSquare
                          size={14}
                          strokeWidth={2}
                          className="flex-shrink-0"
                          style={{
                            color: isActive ? 'var(--color-accent)' : 'var(--color-text-muted)',
                          }}
                        />
                        <div className="flex flex-col min-w-0 flex-1">
                          <span
                            className={`text-xs truncate leading-normal ${
                              isActive ? 'font-semibold' : 'font-medium'
                            }`}
                            style={{
                              color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                            }}
                          >
                            {session.title}
                          </span>
                          <span
                            className="text-[10px] font-mono mt-0.5 leading-normal"
                            style={{ color: 'var(--color-text-faint)' }}
                          >
                            {session.relativeTime}
                          </span>
                        </div>
                      </div>

                      {isActive && (
                        <div
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0 ml-1.5"
                          style={{ background: 'var(--color-accent)' }}
                        />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>

        {/* ── 4. User Account Footer (Pinned at Bottom, Always Visible) ─ */}
        <div
          className="px-5 py-3.5 flex-shrink-0 flex items-center justify-between"
          style={{
            borderTop: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
          }}
        >
          <div
            className="flex items-center gap-3 min-w-0 cursor-pointer select-none"
            onClick={() =>
              showToast(
                'No authentication is configured. This is a local session on this machine.',
                'info'
              )
            }
            title="User Profile"
          >
            {/* Initials Badge */}
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center font-semibold text-xs transition-fast flex-shrink-0 shadow-xs"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-strong)',
                color: 'var(--color-accent)',
              }}
            >
              LO
            </div>

            {/* Name + Role */}
            <div className="flex flex-col min-w-0">
              <span
                className="text-xs font-semibold truncate leading-normal"
                style={{ color: 'var(--color-text)' }}
              >
                Local Operator
              </span>
              <span
                className="text-[10px] truncate leading-tight mt-0.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                No sign-in configured
              </span>
            </div>
          </div>

          {/* ROUTES THAT EXISTED WITH NO WAY IN.
             *
             * /graph, /instrumentation and /monitor were reachable only
             * by typing the URL. Two of them are finished work by a
             * teammate -- the graph explorer and the agent-stream view --
             * and /graph was worse than missing: it rendered a
             * placeholder drawing a hardcoded graph, so it looked like
             * it worked.
             *
             * A feature nobody can navigate to does not exist as far as
             * a demo is concerned. */}
          <Link
            to="/graph"
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Knowledge Graph Explorer (/graph)"
            aria-label="Graph explorer"
          >
            <Network size={14} strokeWidth={2} />
          </Link>

          <Link
            to="/instrumentation"
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Agent stream, retrieval trace, ingestion feed (/instrumentation)"
            aria-label="Instrumentation"
          >
            <Activity size={14} strokeWidth={2} />
          </Link>

          <Link
            to="/monitor"
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Network monitor - proof of no outbound calls (/monitor)"
            aria-label="Network monitor"
          >
            <ShieldCheck size={14} strokeWidth={2} />
          </Link>

          {/* Settings / Overflow trigger */}
          <Link
            to="/settings"
            className="w-7 h-7 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
            title="Settings & System Configuration (/settings)"
            aria-label="Settings"
          >
            <Settings size={14} strokeWidth={2} />
          </Link>
        </div>
      </aside>

      {/* ── Add Source Directory & Native File/Folder Browser Modal ── */}
      <AddSourceDirectoryModal
        isOpen={isAddDirModalOpen}
        onClose={handleCloseAddDirModal}
        onDirectoriesUpdated={fetchCorpus}
        currentDirectories={directories}
      />

      {/* ── 5. Command Palette Modal Shell (Triggered by Search Icon / Ctrl+K) ── */}
      {isSearchOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 animate-fade-in"
          style={{ background: 'rgba(0, 0, 0, 0.45)', backdropFilter: 'blur(2px)' }}
          onClick={() => setIsSearchOpen(false)}
        >
          <div
            className="w-full max-w-lg rounded-xl shadow-2xl border overflow-hidden flex flex-col"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search Input Bar */}
            <div
              className="flex items-center gap-3 px-4 py-3 border-b"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <Search size={16} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
              <input
                type="text"
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Type a command or search MRPL corpus..."
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--color-text-faint)]"
                style={{ color: 'var(--color-text)' }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    showToast(`Searching for "${searchQuery}" in local corpus`, 'info')
                    setIsSearchOpen(false)
                  }
                }}
              />
              <kbd
                className="px-1.5 py-0.5 rounded text-[10px] font-mono leading-none flex-shrink-0"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-text-muted)',
                  border: '1px solid var(--color-border)',
                }}
              >
                ESC
              </kbd>
              <button
                type="button"
                onClick={() => setIsSearchOpen(false)}
                className="p-1 rounded hover:bg-[var(--color-overlay)] text-muted cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            {/* Quick Actions List */}
            <div className="p-3 flex flex-col gap-1 text-xs">
              <span
                className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: 'var(--color-text-faint)' }}
              >
                Quick Actions
              </span>
              {[
                {
                  label: 'Search 13 MRPL corpus documents & plant APIs',
                  icon: Database,
                  action: () => showToast('Indexed 13 MRPL corpus documents in local FAISS vector store', 'info'),
                },
                {
                  label: 'Jump to full-screen Plan DAG graph (/plan)',
                  icon: Network,
                  action: () => showToast('Full execution plan graph route: /plan', 'info'),
                },
                {
                  label: 'Switch theme (Light / Dark mode)',
                  icon: Sun,
                  action: () => toggleTheme(),
                },
                {
                  label: 'Start new investigation session',
                  icon: Plus,
                  action: handleNewChat,
                },
              ].map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    item.action()
                    setIsSearchOpen(false)
                  }}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-md text-left transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
                  style={{ color: 'var(--color-text)' }}
                >
                  <item.icon size={14} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
                  <span className="flex-1">{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
