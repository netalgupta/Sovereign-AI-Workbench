import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Search,
  Sun,
  Moon,
  Plus,
  Database,
  MessageSquare,
  HardDrive,
  Link as LinkIcon,
  Plug,
  Settings,
  X,
  Network,
} from 'lucide-react'
import { useThemeStore } from '../../store/themeStore'
import { showToast } from '../../store/toastStore'

const INITIAL_SOURCES = [
  {
    id: '1',
    name: 'HCU_Operations_Manual.pdf',
    type: 'PDF',
    size: '12 MB',
    addedAgo: 'Added 3d ago',
    category: 'documents',
    color: '#D93829',
    bg: 'rgba(217, 56, 41, 0.12)',
    border: 'rgba(217, 56, 41, 0.28)',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '2',
    name: 'Safety_Guidelines_2024.docx',
    type: 'DOCX',
    size: '2.4 MB',
    addedAgo: 'Added 1w ago',
    category: 'documents',
    color: '#2B6CB0',
    bg: 'rgba(43, 108, 176, 0.12)',
    border: 'rgba(43, 108, 176, 0.28)',
    iconText: 'DOCX',
    enabled: true,
  },
  {
    id: '3',
    name: 'Unit_Performance_Data.xlsx',
    type: 'XLSX',
    size: '1.1 MB',
    addedAgo: 'Added 2w ago',
    category: 'documents',
    color: '#2F855A',
    bg: 'rgba(47, 133, 90, 0.12)',
    border: 'rgba(47, 133, 90, 0.28)',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '4',
    name: 'Emissions_Regulations.pdf',
    type: 'PDF',
    size: '3.8 MB',
    addedAgo: 'Added 5d ago',
    category: 'documents',
    color: '#D93829',
    bg: 'rgba(217, 56, 41, 0.12)',
    border: 'rgba(217, 56, 41, 0.28)',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '5',
    name: 'Historical_Trend_Data.csv',
    type: 'CSV',
    size: '14 MB',
    addedAgo: 'Added 4d ago',
    category: 'data',
    color: 'var(--color-text)',
    bg: 'var(--color-overlay)',
    border: 'var(--color-border)',
    iconType: 'database',
    enabled: true,
  },
  {
    id: '6',
    name: 'Catalyst_Specifications.pdf',
    type: 'PDF',
    size: '2.1 MB',
    addedAgo: 'Added 2w ago',
    category: 'documents',
    color: 'var(--color-text-muted)',
    bg: 'var(--color-overlay)',
    border: 'var(--color-border)',
    iconText: 'PDF',
    enabled: false,
  },
  {
    id: '7',
    name: 'Market_Prices_API',
    type: 'API',
    size: 'Live Data Source',
    addedAgo: 'Added 1d ago',
    category: 'apis',
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-tint)',
    border: 'var(--color-accent-border)',
    iconType: 'api',
    isLive: true,
    enabled: true,
  },
  {
    id: '8',
    name: 'SAP_Plant_Sensors_API',
    type: 'API',
    size: 'Live Data Source',
    addedAgo: 'Added 2d ago',
    category: 'apis',
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-tint)',
    border: 'var(--color-accent-border)',
    iconType: 'api',
    isLive: true,
    enabled: true,
  },
]

const MOCK_CHATS = [
  {
    id: 'session-1',
    title: 'Refinery Turnaround Analysis',
    relativeTime: '2h ago',
    active: true,
    tags: ['Hydrocracker', 'Unit-2'],
  },
  {
    id: 'session-2',
    title: 'CDU-II Column Maintenance Review',
    relativeTime: 'Yesterday',
    active: false,
    tags: ['Crude Unit', 'Distillation'],
  },
  {
    id: 'session-3',
    title: 'Hydrocracker Catalyst Life Estimation',
    relativeTime: '3d ago',
    active: false,
    tags: ['Reactor', 'Catalyst'],
  },
  {
    id: 'session-4',
    title: 'Steam Methane Reformer Efficiency',
    relativeTime: 'Sep 4',
    active: false,
    tags: ['Hydrogen', 'SMR'],
  },
  {
    id: 'session-5',
    title: 'Flare Stack Emission Compliance Audit',
    relativeTime: 'Aug 28',
    active: false,
    tags: ['Environmental', 'EPA-1910'],
  },
]

export function Sidebar() {
  const { theme, toggleTheme } = useThemeStore()

  // Two-tab accordion switcher: 'sources' | 'chats' (mutually exclusive)
  const [activeTab, setActiveTab] = useState('sources')

  // Sources tab internal filter state
  const [sourcesCategory, setSourcesCategory] = useState('all')
  const [sources, setSources] = useState(INITIAL_SOURCES)

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

  // Expose test automation helpers
  useEffect(() => {
    window.__workbenchSetSidebarTab = (tab) => setActiveTab(tab)
    window.__workbenchOpenSearchModal = (open = true) => setIsSearchOpen(open)
    return () => {
      delete window.__workbenchSetSidebarTab
      delete window.__workbenchOpenSearchModal
    }
  }, [])

  const toggleSource = (id) => {
    setSources((prev) =>
      prev.map((s) => {
        if (s.id === id) {
          const nextState = !s.enabled
          showToast(
            nextState
              ? `"${s.name}" included in retrieval scope`
              : `"${s.name}" excluded from retrieval scope`,
            nextState ? 'success' : 'info'
          )
          return { ...s, enabled: nextState }
        }
        return s
      })
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

  const filteredSources = sources.filter((s) => {
    if (sourcesCategory === 'all') return true
    if (sourcesCategory === 'documents') return s.category === 'documents'
    if (sourcesCategory === 'data') return s.category === 'data'
    if (sourcesCategory === 'apis') return s.category === 'apis'
    return true
  })

  const counts = {
    all: sources.length,
    documents: sources.filter((s) => s.category === 'documents').length,
    data: sources.filter((s) => s.category === 'data').length,
    apis: sources.filter((s) => s.category === 'apis').length,
  }

  return (
    <>
      <aside
        className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden relative"
        style={{
          width: 300,
          background: 'var(--color-bg)',
          borderRight: '1px solid var(--color-border)',
        }}
        aria-label="Sidebar navigation, sources, and past sessions"
      >
        {/* ── 1. Top Header: Brand Lockup + Icon Button Row ──────────── */}
        <div
          className="flex flex-col px-4 pt-3.5 pb-3 flex-shrink-0 gap-3"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="flex items-center justify-between">
            {/* Logo Mark + Wordmark Lockup */}
            <div className="flex items-center gap-2.5 min-w-0">
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
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {/* Search Icon Trigger */}
              <button
                type="button"
                onClick={() => setIsSearchOpen(true)}
                className="w-7 h-7 rounded-md flex items-center justify-center transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
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
                className="w-7 h-7 rounded-md flex items-center justify-center transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
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
            className="flex items-center p-0.5 rounded-md text-xs font-medium"
            style={{ background: 'var(--color-overlay)' }}
          >
            <button
              type="button"
              onClick={() => setActiveTab('sources')}
              className="flex-1 py-1 rounded text-xs transition-fast text-center flex items-center justify-center gap-1.5 cursor-pointer"
              style={{
                background: activeTab === 'sources' ? 'var(--color-surface)' : 'transparent',
                color: activeTab === 'sources' ? 'var(--color-text)' : 'var(--color-text-muted)',
                fontWeight: activeTab === 'sources' ? 600 : 500,
                boxShadow: activeTab === 'sources' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              <Database size={13} strokeWidth={2} />
              <span>Sources</span>
              <span
                className="text-[10px] font-mono px-1 rounded"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {activeCount}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('chats')}
              className="flex-1 py-1 rounded text-xs transition-fast text-center flex items-center justify-center gap-1.5 cursor-pointer"
              style={{
                background: activeTab === 'chats' ? 'var(--color-surface)' : 'transparent',
                color: activeTab === 'chats' ? 'var(--color-text)' : 'var(--color-text-muted)',
                fontWeight: activeTab === 'chats' ? 600 : 500,
                boxShadow: activeTab === 'chats' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              <MessageSquare size={13} strokeWidth={2} />
              <span>Chats</span>
              <span
                className="text-[10px] font-mono px-1 rounded"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {chats.length}
              </span>
            </button>
          </div>
        </div>

        {/* ── 3. Mutually Exclusive Accordion Body (Smooth Height Transition) ── */}
        <div className="flex-1 overflow-hidden flex flex-col relative">
          {/* TAB 1: Sources Tab Content */}
          <div
            className={`collapsible-grid flex-1 ${activeTab === 'sources' ? 'is-expanded' : ''}`}
            style={{ display: activeTab === 'sources' ? 'flex' : 'none', flexDirection: 'column' }}
          >
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              {/* Category Filter Pills & Add Button */}
              <div className="px-4 pt-3 pb-2 flex-shrink-0 flex items-center justify-between gap-2">
                <div
                  className="flex items-center p-0.5 rounded-md text-[11px] font-medium flex-1 min-w-0"
                  style={{ background: 'var(--color-overlay)' }}
                >
                  {[
                    { id: 'all', label: `All (${counts.all})` },
                    { id: 'documents', label: `Docs (${counts.documents})` },
                    { id: 'data', label: `Data (${counts.data})` },
                    { id: 'apis', label: `APIs (${counts.apis})` },
                  ].map((tab) => {
                    const isSelected = sourcesCategory === tab.id
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setSourcesCategory(tab.id)}
                        className="flex-1 py-0.5 rounded text-[10px] transition-fast text-center cursor-pointer truncate"
                        style={{
                          background: isSelected ? 'var(--color-surface)' : 'transparent',
                          color: isSelected ? 'var(--color-text)' : 'var(--color-text-muted)',
                          fontWeight: isSelected ? 600 : 500,
                        }}
                      >
                        {tab.label}
                      </button>
                    )
                  })}
                </div>

                <button
                  type="button"
                  onClick={() =>
                    showToast('Document ingestion pipeline ready — drag & drop supported', 'info')
                  }
                  className="p-1 rounded-md text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex-shrink-0 shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-accent)',
                  }}
                  title="Add document or API connection"
                >
                  <Plus size={13} strokeWidth={2.4} />
                </button>
              </div>

              {/* Sources List */}
              <div className="flex-1 overflow-y-auto px-3.5 py-1 flex flex-col gap-1.5">
                {filteredSources.map((source) => (
                  <div
                    key={source.id}
                    className="flex items-center justify-between p-2 rounded-md transition-fast hover:bg-[var(--color-surface-hover)] group"
                    style={{
                      background: 'transparent',
                      opacity: source.enabled ? 1 : 0.65,
                    }}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 pr-2">
                      <div
                        className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 select-none transition-fast"
                        style={{
                          background: source.bg,
                          border: `1px solid ${source.border}`,
                          color: source.color,
                        }}
                      >
                        {source.iconType === 'database' ? (
                          <Database size={13} strokeWidth={2} />
                        ) : source.iconType === 'api' ? (
                          <Plug size={13} strokeWidth={2} />
                        ) : source.iconType === 'link' ? (
                          <LinkIcon size={13} strokeWidth={2} />
                        ) : (
                          <span className="text-[9px] font-bold tracking-tighter uppercase font-mono">
                            {source.iconText}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-col min-w-0">
                        <span
                          className="text-xs font-semibold truncate leading-tight"
                          style={{ color: 'var(--color-text)' }}
                          title={source.name}
                        >
                          {source.name}
                        </span>
                        <div className="flex items-center gap-1.5 mt-0.5 text-[10px] leading-tight flex-wrap">
                          {source.isLive ? (
                            <span
                              className="flex items-center gap-1 font-medium"
                              style={{ color: 'var(--color-success)' }}
                            >
                              <span
                                className="w-1.5 h-1.5 rounded-full animate-pulse"
                                style={{ background: 'var(--color-success)' }}
                              />
                              Connected
                            </span>
                          ) : (
                            <span style={{ color: 'var(--color-text-muted)' }}>
                              {source.type} • {source.size}
                            </span>
                          )}
                          <span style={{ color: 'var(--color-text-faint)' }}>•</span>
                          <span style={{ color: 'var(--color-text-faint)' }}>
                            {source.addedAgo}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Toggle Switch */}
                    <button
                      type="button"
                      role="switch"
                      aria-checked={source.enabled}
                      onClick={() => toggleSource(source.id)}
                      className="rounded-full transition-base relative flex-shrink-0 cursor-pointer"
                      style={{
                        width: 30,
                        height: 16,
                        background: source.enabled
                          ? 'var(--color-accent)'
                          : 'var(--color-border-strong)',
                      }}
                      title={source.enabled ? 'Included in retrieval' : 'Excluded from retrieval'}
                    >
                      <span
                        className="absolute top-[2px] w-3 h-3 rounded-full bg-white transition-fast shadow-xs"
                        style={{
                          left: source.enabled ? 15 : 2,
                        }}
                      />
                    </button>
                  </div>
                ))}
              </div>

              {/* Knowledge Base Summary Card */}
              <div className="px-4 py-2.5 flex-shrink-0">
                <div
                  className="p-2.5 rounded-md flex flex-col gap-1.5 transition-fast"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-xs)',
                  }}
                >
                  <div className="flex items-center justify-between text-xs">
                    <div
                      className="flex items-center gap-1.5 font-semibold"
                      style={{ color: 'var(--color-text)' }}
                    >
                      <HardDrive size={13} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
                      <span className="text-[11px]">Knowledge Base</span>
                    </div>
                    <span
                      className="text-[10px] font-mono font-medium"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {activeCount} / {totalCount} active
                    </span>
                  </div>

                  {/* Storage Meter */}
                  <div className="flex flex-col gap-1">
                    <div
                      className="flex items-center justify-between text-[9px]"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      <span>Local Storage</span>
                      <span className="font-mono">2.4 GB / 10 GB</span>
                    </div>
                    <div
                      className="w-full h-1.5 rounded-xs overflow-hidden"
                      style={{ background: 'var(--color-overlay)' }}
                    >
                      <div
                        className="h-full rounded-xs transition-base"
                        style={{
                          width: '24%',
                          background: 'var(--color-accent)',
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* TAB 2: Chats Tab Content (ChatGPT-history style) */}
          <div
            className={`collapsible-grid flex-1 ${activeTab === 'chats' ? 'is-expanded' : ''}`}
            style={{ display: activeTab === 'chats' ? 'flex' : 'none', flexDirection: 'column' }}
          >
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              {/* Pinned "+ New chat" button */}
              <div className="px-4 pt-3 pb-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-md text-xs font-semibold shadow-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)]"
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
              <div className="flex-1 overflow-y-auto px-3.5 py-1 flex flex-col gap-1">
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
                      className="w-full flex items-center justify-between p-2 rounded-md text-left transition-fast cursor-pointer group"
                      style={{
                        background: isActive ? 'var(--color-surface)' : 'transparent',
                        border: isActive
                          ? '1px solid var(--color-border)'
                          : '1px solid transparent',
                      }}
                      title={session.title}
                    >
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <MessageSquare
                          size={13}
                          strokeWidth={2}
                          className="flex-shrink-0"
                          style={{
                            color: isActive ? 'var(--color-accent)' : 'var(--color-text-muted)',
                          }}
                        />
                        <div className="flex flex-col min-w-0 flex-1">
                          <span
                            className={`text-xs truncate leading-tight ${
                              isActive ? 'font-semibold' : 'font-medium'
                            }`}
                            style={{
                              color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                            }}
                          >
                            {session.title}
                          </span>
                          <span
                            className="text-[10px] font-mono mt-0.5 leading-tight"
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
          </div>
        </div>

        {/* ── 4. User Account Footer (Pinned at Bottom, Always Visible) ─ */}
        <div
          className="px-4 py-3 flex-shrink-0 flex items-center justify-between"
          style={{
            borderTop: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
          }}
        >
          <div
            className="flex items-center gap-2.5 min-w-0 cursor-pointer select-none"
            onClick={() => showToast('Authenticated session: Advay Chavan (Lead Plant Engineer)', 'info')}
            title="User Profile"
          >
            {/* Initials Badge */}
            <div
              className="w-8 h-8 rounded-md flex items-center justify-center font-semibold text-xs transition-fast flex-shrink-0 shadow-xs"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border-strong)',
                color: 'var(--color-accent)',
              }}
            >
              AC
            </div>

            {/* Name + Role */}
            <div className="flex flex-col min-w-0">
              <span
                className="text-xs font-semibold truncate leading-tight"
                style={{ color: 'var(--color-text)' }}
              >
                Advay Chavan
              </span>
              <span
                className="text-[10px] truncate leading-tight mt-0.5"
                style={{ color: 'var(--color-text-muted)' }}
              >
                Plant Operations Lead
              </span>
            </div>
          </div>

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
                placeholder="Type a command or search documents..."
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
                  label: 'Search 8 local documents & plant APIs',
                  icon: Database,
                  action: () => showToast('Indexing 8 local sources in Milvus collection', 'info'),
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
