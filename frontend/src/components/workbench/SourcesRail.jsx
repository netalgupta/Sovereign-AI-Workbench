import { useState } from 'react'
import {
  Plus,
  FileText,
  Table,
  Database,
  Link as LinkIcon,
  HardDrive,
} from 'lucide-react'

const INITIAL_SOURCES = [
  {
    id: '1',
    name: 'HCU_Operations_Manual.pdf',
    type: 'PDF',
    size: '12 MB',
    category: 'documents',
    color: '#D93829', // red
    bg: '#FDF0EE',
    border: '#F7CECA',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '2',
    name: 'Safety_Guidelines_2024.docx',
    type: 'DOCX',
    size: '2.4 MB',
    category: 'documents',
    color: '#2B6CB0', // blue
    bg: '#EDF4FC',
    border: '#CDE1F8',
    iconText: 'DOCX',
    enabled: true,
  },
  {
    id: '3',
    name: 'Unit_Performance_Data.xlsx',
    type: 'XLSX',
    size: '1.1 MB',
    category: 'documents',
    color: '#2F855A', // green
    bg: '#EDF8F2',
    border: '#C3E7D5',
    iconText: 'XLSX',
    enabled: true,
  },
  {
    id: '4',
    name: 'Emissions_Regulations.pdf',
    type: 'PDF',
    size: '3.8 MB',
    category: 'documents',
    color: '#D93829',
    bg: '#FDF0EE',
    border: '#F7CECA',
    iconText: 'PDF',
    enabled: true,
  },
  {
    id: '5',
    name: 'Catalyst_Specifications.pdf',
    type: 'PDF',
    size: '2.1 MB',
    category: 'documents',
    color: '#8A7A70', // muted brown/grey
    bg: '#F2EFEA',
    border: '#DFD8CE',
    iconText: 'PDF',
    enabled: false,
  },
  {
    id: '6',
    name: 'Historical_Trend_Data.csv',
    type: 'CSV',
    size: '14 MB',
    category: 'data',
    color: '#2A2724', // charcoal
    bg: '#EAE5DF',
    border: '#D8D1C7',
    iconType: 'database',
    enabled: true,
  },
  {
    id: '7',
    name: 'Vendor_Technical_Note.pdf',
    type: 'PDF',
    size: '1.3 MB',
    category: 'documents',
    color: '#8A7A70',
    bg: '#F2EFEA',
    border: '#DFD8CE',
    iconText: 'PDF',
    enabled: false,
  },
  {
    id: '8',
    name: 'API: Market_Prices',
    type: 'API',
    size: 'Live Data Source',
    category: 'data',
    color: '#1A1816',
    bg: '#E4DDD4',
    border: '#CEBEAD',
    iconType: 'link',
    enabled: true,
  },
]

export function SourcesRail() {
  const [activeTab, setActiveTab] = useState('all')
  const [sources, setSources] = useState(INITIAL_SOURCES)

  const toggleSource = (id) => {
    setSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
    )
  }

  const filteredSources = sources.filter((s) => {
    if (activeTab === 'all') return true
    if (activeTab === 'documents') return s.category === 'documents'
    if (activeTab === 'data') return s.category === 'data'
    return true
  })

  return (
    <aside
      className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden"
      style={{
        width: 290,
        background: 'var(--color-bg)',
        borderRight: '1px solid rgba(42, 39, 36, 0.06)',
      }}
      aria-label="Sources panel"
    >
      {/* ── Header: Title + Add Button ───────────────────────────────── */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 flex-shrink-0">
        <h2
          className="text-base font-bold tracking-tight"
          style={{ color: 'var(--color-text)' }}
        >
          Sources
        </h2>
        <button
          type="button"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-fast shadow-xs"
          style={{
            background: 'white',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text)',
          }}
          title="Add documents to knowledge base"
        >
          <Plus size={13} strokeWidth={2} />
          <span>Add</span>
        </button>
      </div>

      {/* ── Filter Tabs Segmented Control ────────────────────────────── */}
      <div className="px-5 pb-3 flex-shrink-0">
        <div
          className="flex items-center p-1 rounded-xl text-xs font-medium"
          style={{ background: 'var(--color-overlay)' }}
        >
          {[
            { id: 'all', label: 'All (8)' },
            { id: 'documents', label: 'Documents (6)' },
            { id: 'data', label: 'Data (2)' },
          ].map((tab) => {
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className="flex-1 py-1 rounded-lg text-xs transition-fast text-center"
                style={{
                  background: isActive ? '#FFFFFF' : 'transparent',
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
      <div className="flex-1 overflow-y-auto px-4 py-1 flex flex-col gap-1">
        {filteredSources.map((source) => (
          <div
            key={source.id}
            className="flex items-center justify-between p-2.5 rounded-xl transition-fast hover:bg-[#F3ECE4]"
            style={{
              background: 'transparent',
            }}
          >
            {/* File icon + Name & Subtext */}
            <div className="flex items-center gap-2.5 min-w-0 pr-2">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 select-none"
                style={{
                  background: source.bg,
                  border: `1px solid ${source.border}`,
                  color: source.color,
                }}
              >
                {source.iconType === 'database' ? (
                  <Database size={15} strokeWidth={2} />
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
                <span
                  className="text-[11px] truncate leading-tight mt-0.5"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  {source.size.includes('Live')
                    ? source.size
                    : `${source.type} • ${source.size}`}
                </span>
              </div>
            </div>

            {/* iOS-style toggle switch matching reference */}
            <button
              type="button"
              role="switch"
              aria-checked={source.enabled}
              onClick={() => toggleSource(source.id)}
              className="w-8 h-4.5 rounded-full transition-base relative flex-shrink-0 cursor-pointer"
              style={{
                width: 34,
                height: 19,
                background: source.enabled
                  ? 'var(--color-accent)'
                  : 'var(--color-border-strong)',
              }}
              title={source.enabled ? 'Grounded in session' : 'Excluded from retrieval'}
            >
              <span
                className="absolute top-[2px] w-3.5 h-3.5 rounded-full bg-white transition-fast shadow-xs"
                style={{
                  left: source.enabled ? 17 : 2,
                }}
              />
            </button>
          </div>
        ))}
      </div>

      {/* ── Bottom Storage Indicator (Reference Matching) ─────────────── */}
      <div
        className="px-5 py-3.5 flex-shrink-0 flex flex-col gap-1.5"
        style={{
          borderTop: '1px solid rgba(42, 39, 36, 0.05)',
        }}
      >
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5" style={{ color: 'var(--color-text)' }}>
            <Database size={14} strokeWidth={1.8} style={{ color: 'var(--color-text-muted)' }} />
            <span className="font-semibold text-[11px]">Storage</span>
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
            2.4 GB of 10 GB
          </span>
        </div>
        {/* Progress bar */}
        <div
          className="w-full h-1.5 rounded-full overflow-hidden"
          style={{ background: 'var(--color-overlay)' }}
        >
          <div
            className="h-full rounded-full transition-base"
            style={{
              width: '24%',
              background: 'var(--color-accent)',
            }}
          />
        </div>
      </div>
    </aside>
  )
}
