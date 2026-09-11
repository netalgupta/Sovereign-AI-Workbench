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
  Settings,
  X,
  Network,
  Maximize2,
  ArrowUpRight,
} from 'lucide-react'
import { useThemeStore } from '../../store/themeStore'
import { showToast } from '../../store/toastStore'
import { SourceFileTree } from './SourceFileTree'
import { AddSourceDirectoryModal } from './AddSourceDirectoryModal'

const INITIAL_SOURCES = [
  {
    id: '01_SOPs_and_Procedures_SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx',
    name: 'SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx',
    type: 'DOCX',
    size: '37.7 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'sops',
    badge: 'SOP & Safety',
    color: '#2563EB',
    bg: 'rgba(37, 99, 235, 0.12)',
    border: 'rgba(37, 99, 235, 0.28)',
    iconText: 'DOCX',
    enabled: true,
  },
  {
    id: '01_SOPs_and_Procedures_Aromatic_Complex_Benzene_Safety_Circular.docx',
    name: 'Aromatic_Complex_Benzene_Safety_Circular.docx',
    type: 'DOCX',
    size: '37.0 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'sops',
    badge: 'SOP & Safety',
    color: '#2563EB',
    bg: 'rgba(37, 99, 235, 0.12)',
    border: 'rgba(37, 99, 235, 0.28)',
    iconText: 'DOCX',
    enabled: true,
  },
  {
    id: '02_Inspection_and_Maintenance_Inspection_Report_CCR1_Regeneration_Cycle.pdf',
    name: 'Inspection_Report_CCR1_Regeneration_Cycle.pdf',
    type: 'PDF',
    size: '38.2 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'inspection',
    badge: 'Inspection & Maintenance',
    color: '#D93829',
    bg: 'rgba(217, 56, 41, 0.12)',
    border: 'rgba(217, 56, 41, 0.28)',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '02_Inspection_and_Maintenance_Maintenance_Log_Q3_2026.xlsx',
    name: 'Maintenance_Log_Q3_2026.xlsx',
    type: 'XLSX',
    size: '11.4 KB',
    addedAgo: 'Ingested on-prem',
    category: 'data',
    subcategory: 'inspection',
    badge: 'Inspection & Maintenance',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)',
    border: 'rgba(5, 150, 105, 0.28)',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '02_Inspection_and_Maintenance_Pipeline_Incident_Report_Hassan_Segment.pdf',
    name: 'Pipeline_Incident_Report_Hassan_Segment.pdf',
    type: 'PDF',
    size: '36.3 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'inspection',
    badge: 'Inspection & Maintenance',
    color: '#D93829',
    bg: 'rgba(217, 56, 41, 0.12)',
    border: 'rgba(217, 56, 41, 0.28)',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '03_Quality_and_Process_Data_Novolen_Batch_QA_Report_Aug2026.pdf',
    name: 'Novolen_Batch_QA_Report_Aug2026.pdf',
    type: 'PDF',
    size: '42.1 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'quality',
    badge: 'QA & Process Data',
    color: '#D93829',
    bg: 'rgba(217, 56, 41, 0.12)',
    border: 'rgba(217, 56, 41, 0.28)',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '03_Quality_and_Process_Data_PSA_Hydrogen_Purity_Trend_Log.xlsx',
    name: 'PSA_Hydrogen_Purity_Trend_Log.xlsx',
    type: 'XLSX',
    size: '11.4 KB',
    addedAgo: 'Ingested on-prem',
    category: 'data',
    subcategory: 'quality',
    badge: 'QA & Process Data',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)',
    border: 'rgba(5, 150, 105, 0.28)',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '03_Quality_and_Process_Data_Sulphur_Spec_Compliance_LabSheet.xlsx',
    name: 'Sulphur_Spec_Compliance_LabSheet.xlsx',
    type: 'XLSX',
    size: '9.8 KB',
    addedAgo: 'Ingested on-prem',
    category: 'data',
    subcategory: 'quality',
    badge: 'QA & Process Data',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)',
    border: 'rgba(5, 150, 105, 0.28)',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '04_SAP_Mock_Exports_SAP_Mock_Materials_Master_Export.xlsx',
    name: 'SAP_Mock_Materials_Master_Export.xlsx',
    type: 'XLSX',
    size: '11.8 KB',
    addedAgo: 'Ingested on-prem',
    category: 'data',
    subcategory: 'sap_mock',
    badge: 'SAP ERP Export',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)',
    border: 'rgba(5, 150, 105, 0.28)',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '05_Correspondence_Correspondence_Depot_HQ_Thread_Kasargod.docx',
    name: 'Correspondence_Depot_HQ_Thread_Kasargod.docx',
    type: 'DOCX',
    size: '36.6 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'correspondence',
    badge: 'Depot Operations',
    color: '#2563EB',
    bg: 'rgba(37, 99, 235, 0.12)',
    border: 'rgba(37, 99, 235, 0.28)',
    iconText: 'DOCX',
    enabled: true,
  },
  {
    id: '06_Diagrams_and_Scans_Hydrocracker_PID_Schematic.png',
    name: 'Hydrocracker_PID_Schematic.png',
    type: 'P&ID',
    size: '93.8 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'diagrams',
    badge: 'Schematics & Scans',
    color: '#0D9488',
    bg: 'rgba(13, 148, 136, 0.12)',
    border: 'rgba(13, 148, 136, 0.28)',
    iconText: 'P&ID',
    enabled: true,
  },
  {
    id: '06_Diagrams_and_Scans_Pipeline_Segment_Map_Mangalore_Hassan.png',
    name: 'Pipeline_Segment_Map_Mangalore_Hassan.png',
    type: 'P&ID',
    size: '59.0 KB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'diagrams',
    badge: 'Schematics & Scans',
    color: '#0D9488',
    bg: 'rgba(13, 148, 136, 0.12)',
    border: 'rgba(13, 148, 136, 0.28)',
    iconText: 'P&ID',
    enabled: true,
  },
  {
    id: '06_Diagrams_and_Scans_Scanned_Inspection_Checklist_CCR1.png',
    name: 'Scanned_Inspection_Checklist_CCR1.png',
    type: 'SCAN',
    size: '1.96 MB',
    addedAgo: 'Ingested on-prem',
    category: 'documents',
    subcategory: 'diagrams',
    badge: 'Schematics & Scans',
    color: '#0D9488',
    bg: 'rgba(13, 148, 136, 0.12)',
    border: 'rgba(13, 148, 136, 0.28)',
    iconText: 'SCAN',
    enabled: true,
  },
  {
    id: 'sap-plant-sensors-api',
    name: 'SAP_Plant_Sensors_API',
    label: 'SAP ERP Local Connector (RFC/BAPI Mock)',
    type: 'API',
    size: 'Live Data Source',
    addedAgo: 'Online (Loopback)',
    category: 'apis',
    subcategory: 'apis',
    badge: 'SAP ERP RFC/BAPI',
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-tint)',
    border: 'var(--color-accent-border)',
    iconType: 'api',
    isLive: true,
    enabled: true,
  },
  {
    id: 'dcs-scada-telemetry-feed',
    name: 'DCS_SCADA_Telemetry_Feed',
    label: 'DCS / SCADA Telemetry Stream (OPC-UA)',
    type: 'API',
    size: 'Live Data Source',
    addedAgo: 'Online (Loopback)',
    category: 'apis',
    subcategory: 'apis',
    badge: 'OPC-UA Real-Time',
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
  const [tree, setTree] = useState([])
  const [directories, setDirectories] = useState([])
  const [totalSizeDisplay, setTotalSizeDisplay] = useState('2.83 MB')
  const [isAddDirModalOpen, setIsAddDirModalOpen] = useState(false)

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
  const fetchCorpus = () => {
    fetch('/api/corpus')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.sources && Array.isArray(data.sources)) {
          setSources(data.sources)
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
      })
      .catch(() => {})
  }

  const handleDeleteSource = async (source) => {
    if (!source) return
    const name = source.name || 'item'
    if (!window.confirm(`Are you sure you want to delete "${name}" from sources and FAISS index?`)) {
      return
    }
    try {
      const targetParam = source.fullPath || source.relPath || source.path || source.id || source.name
      const res = await fetch(`/api/sources?path=${encodeURIComponent(targetParam)}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        showToast(`Source "${name}" removed from knowledge base`, 'info')
        fetchCorpus()
      } else {
        const err = await res.json().catch(() => ({}))
        showToast(err.error || `Failed to delete "${name}"`, 'error')
      }
    } catch {
      showToast(`Failed to delete "${name}"`, 'error')
    }
  }

  useEffect(() => {
    fetchCorpus()
    const handleCorpusUpdated = () => fetchCorpus()
    window.addEventListener('corpus-updated', handleCorpusUpdated)
    return () => window.removeEventListener('corpus-updated', handleCorpusUpdated)
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
        <div className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
          {/* TAB 1: Sources Tab Content */}
          <div
            className="flex-1 min-h-0 flex flex-col overflow-hidden"
            style={{ display: activeTab === 'sources' ? 'flex' : 'none' }}
          >
            {/* Category Filter Pills & Add / Expand Buttons */}
            <div className="px-3 pt-3 pb-2 flex-shrink-0 flex items-center justify-between gap-1.5">
              <div
                className="flex items-center p-0.5 rounded-md text-[10px] font-medium flex-1 min-w-0"
                style={{ background: 'var(--color-overlay)' }}
              >
                {[
                  { id: 'all', label: `All (${counts.all})` },
                  { id: 'documents', label: `Docs (${counts.documents})` },
                  { id: 'data', label: `Data (${counts.data})` },
                  { id: 'charts', label: `Charts (${counts.charts})` },
                  { id: 'apis', label: `APIs (${counts.apis})` },
                ].map((tab) => {
                  const isSelected = sourcesCategory === tab.id
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setSourcesCategory(tab.id)}
                      className="flex-1 py-0.5 rounded text-[9.5px] transition-fast text-center cursor-pointer truncate"
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

              {/* Add Source Directory / Files button */}
              <button
                type="button"
                onClick={() => setIsAddDirModalOpen(true)}
                className="p-1 rounded-md text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex-shrink-0 shadow-xs"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-accent)',
                }}
                title="Browse & add source directories or files"
              >
                <Plus size={13} strokeWidth={2.4} />
              </button>

              {/* Expand to Full Sources Hub button */}
              <Link
                to="/sources"
                className="p-1 rounded-md text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex-shrink-0 shadow-xs"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
                title="Open Sources & Pipeline Internals Hub (/sources)"
              >
                <Maximize2 size={13} strokeWidth={2} />
              </Link>
            </div>

            {/* Hierarchical Tree with Smooth Custom Scrollbar */}
            <div className="flex-1 min-h-0 overflow-y-auto px-2.5 py-1 flex flex-col gap-0.5 custom-scrollbar">
              <SourceFileTree
                tree={tree}
                filterCategory={sourcesCategory}
                onToggleSource={toggleSource}
                onDeleteSource={handleDeleteSource}
                compact={false}
              />
            </div>

            {/* Knowledge Base Summary Card */}
            <div className="px-3.5 py-2 flex-shrink-0">
              <div
                className="p-2.5 rounded-lg flex flex-col gap-1.5 transition-fast"
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
                    <span className="truncate">MRPL Dual-Corpus Storage</span>
                    <span className="font-mono font-medium flex-shrink-0">{totalSizeDisplay}</span>
                  </div>
                  <div
                    className="w-full h-1.5 rounded-xs overflow-hidden"
                    style={{ background: 'var(--color-overlay)' }}
                  >
                    <div
                      className="h-full rounded-xs transition-base"
                      style={{
                        width: '100%',
                        background: 'var(--color-accent)',
                      }}
                    />
                  </div>
                </div>

                {/* Link to full Sources Hub */}
                <Link
                  to="/sources"
                  className="flex items-center justify-between mt-1 pt-1.5 border-t text-[10px] font-semibold hover:underline cursor-pointer"
                  style={{
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <span>Open Sources Hub</span>
                  <ArrowUpRight size={12} />
                </Link>
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

      {/* ── Add Source Directory & Native File/Folder Browser Modal ── */}
      <AddSourceDirectoryModal
        isOpen={isAddDirModalOpen}
        onClose={() => setIsAddDirModalOpen(false)}
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
