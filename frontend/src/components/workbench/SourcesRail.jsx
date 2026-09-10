import { useState } from 'react'
import {
  Plus,
  Database,
  Link as LinkIcon,
  Plug,
  HardDrive,
} from 'lucide-react'
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

export function SourcesRail() {
  const [activeTab, setActiveTab] = useState('all')
  const [sources, setSources] = useState(INITIAL_SOURCES)

  const toggleSource = (id) => {
    setSources((prev) =>
      prev.map((s) => {
        if (s.id === id) {
          const nextState = !s.enabled
          showToast(
            nextState
              ? `"${s.name}" included in session retrieval scope`
              : `"${s.name}" excluded from session retrieval scope`,
            nextState ? 'success' : 'info'
          )
          return { ...s, enabled: nextState }
        }
        return s
      })
    )
  }

  const activeCount = sources.filter((s) => s.enabled).length
  const totalCount = sources.length

  const filteredSources = sources.filter((s) => {
    if (activeTab === 'all') return true
    if (activeTab === 'documents') return s.category === 'documents'
    if (activeTab === 'data') return s.category === 'data'
    if (activeTab === 'apis') return s.category === 'apis'
    return true
  })

  // Counts for each tab
  const counts = {
    all: sources.length,
    documents: sources.filter((s) => s.category === 'documents').length,
    data: sources.filter((s) => s.category === 'data').length,
    apis: sources.filter((s) => s.category === 'apis').length,
  }

  return (
    <aside
      className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden"
      style={{
        width: 300,
        background: 'var(--color-bg)',
        borderRight: '1px solid var(--color-border)',
      }}
      aria-label="Sources panel"
    >
      {/* ── Header: Title + Add Button ───────────────────────────────── */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <h2
            className="text-base font-bold tracking-tight"
            style={{ color: 'var(--color-text)' }}
          >
            Sources
          </h2>
          <span
            className="px-2 py-0.5 rounded text-[10px] font-semibold"
            style={{ background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }}
          >
            {activeCount}/{totalCount} Active
          </span>
        </div>
        <button
          type="button"
          onClick={() => showToast('Document ingestion pipeline active — Drag and drop supported', 'info')}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-fast shadow-xs cursor-pointer"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text)',
          }}
          title="Add documents or APIs to knowledge base"
        >
          <Plus size={13} strokeWidth={2} />
          <span>Add</span>
        </button>
      </div>

      {/* ── Filter Tabs Segmented Control (All / Documents / Data / APIs) ── */}
      <div className="px-4 pb-2.5 flex-shrink-0">
        <div
          className="flex items-center p-0.5 rounded-md text-xs font-medium"
          style={{ background: 'var(--color-overlay)' }}
        >
          {[
            { id: 'all', label: `All (${counts.all})` },
            { id: 'documents', label: `Docs (${counts.documents})` },
            { id: 'data', label: `Data (${counts.data})` },
            { id: 'apis', label: `APIs (${counts.apis})` },
          ].map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className="flex-1 py-1 rounded text-[11px] transition-fast text-center cursor-pointer"
                style={{
                  background: isActive ? 'var(--color-surface)' : 'transparent',
                  color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                  fontWeight: isActive ? 600 : 500,
                  boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                }}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Source List ──────────────────────────────────────────────── */}
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
            {/* File icon + Name & Subtext */}
            <div className="flex items-center gap-2.5 min-w-0 pr-2">
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0 select-none transition-fast"
                style={{
                  background: source.bg,
                  border: `1px solid ${source.border}`,
                  color: source.color,
                }}
              >
                {source.iconType === 'database' ? (
                  <Database size={15} strokeWidth={2} />
                ) : source.iconType === 'api' ? (
                  <Plug size={15} strokeWidth={2} />
                ) : source.iconType === 'link' ? (
                  <LinkIcon size={15} strokeWidth={2} />
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

                {/* Status / Size row + Relative Timestamp */}
                <div className="flex items-center gap-1.5 mt-0.5 text-[11px] leading-tight flex-wrap">
                  {source.isLive ? (
                    <span className="flex items-center gap-1 font-medium" style={{ color: 'var(--color-success)' }}>
                      <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-success)' }} />
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

            {/* iOS-style toggle switch */}
            <button
              type="button"
              role="switch"
              aria-checked={source.enabled}
              onClick={() => toggleSource(source.id)}
              className="rounded-full transition-base relative flex-shrink-0 cursor-pointer"
              style={{
                width: 32,
                height: 18,
                background: source.enabled
                  ? 'var(--color-accent)'
                  : 'var(--color-border-strong)',
              }}
              title={source.enabled ? 'Included in retrieval' : 'Excluded from retrieval'}
            >
              <span
                className="absolute top-[2px] w-3.5 h-3.5 rounded-full bg-white transition-fast shadow-xs"
                style={{
                  left: source.enabled ? 16 : 2,
                }}
              />
            </button>
          </div>
        ))}
      </div>

      {/* ── Knowledge Base Summary Card ──────────────────────────────── */}
      <div className="px-4 pb-3.5 flex-shrink-0 relative z-10">
        <div
          className="p-3 rounded-md flex flex-col gap-2 transition-fast"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-xs)',
          }}
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--color-text)' }}>
              <HardDrive size={14} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
              <span>Knowledge Base</span>
            </div>
            <span className="text-[11px] font-mono font-medium" style={{ color: 'var(--color-text-muted)' }}>
              {activeCount} / {totalCount} active
            </span>
          </div>

          {/* Storage Meter */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
              <span>Local Storage</span>
              <span className="font-mono">2.4 GB / 10 GB</span>
            </div>
            <div
              className="w-full h-1.5 rounded-sm overflow-hidden"
              style={{ background: 'var(--color-overlay)' }}
            >
              <div
                className="h-full rounded-sm transition-base"
                style={{
                  width: '24%',
                  background: 'var(--color-accent)',
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
