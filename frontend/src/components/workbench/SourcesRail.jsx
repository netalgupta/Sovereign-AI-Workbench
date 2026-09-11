import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus,
  HardDrive,
  Maximize2,
  ArrowUpRight,
} from 'lucide-react'
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

export function SourcesRail() {
  const [activeTab, setActiveTab] = useState('all')
  const [sources, setSources] = useState(INITIAL_SOURCES)
  const [tree, setTree] = useState([])
  const [directories, setDirectories] = useState([])
  const [totalSizeDisplay, setTotalSizeDisplay] = useState('2.83 MB')
  const [isAddDirModalOpen, setIsAddDirModalOpen] = useState(false)

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

  useEffect(() => {
    fetchCorpus()
    const handleCorpusUpdated = () => fetchCorpus()
    window.addEventListener('corpus-updated', handleCorpusUpdated)
    return () => window.removeEventListener('corpus-updated', handleCorpusUpdated)
  }, [])

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
        className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden"
        style={{
          width: 300,
          background: 'var(--color-bg)',
          borderRight: '1px solid var(--color-border)',
        }}
        aria-label="Sources panel"
      >
        {/* ── Header: Title + Add Button + Expand Link ───────────────── */}
        <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5 flex-shrink-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
              Sources
            </h2>
            <span
              className="px-1.5 py-0.2 rounded text-[10px] font-semibold"
              style={{ background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }}
            >
              {activeCount}/{totalCount}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setIsAddDirModalOpen(true)}
              className="p-1 rounded-md text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] shadow-xs"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-accent)',
              }}
              title="Add source directories or files"
            >
              <Plus size={13} strokeWidth={2.4} />
            </button>

            <Link
              to="/sources"
              className="p-1 rounded-md text-xs transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] shadow-xs"
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
        </div>

        {/* ── Filter Tabs Segmented Control ───────────────────────────── */}
        <div className="px-3 pb-2 flex-shrink-0">
          <div
            className="flex items-center p-0.5 rounded-md text-[10px] font-medium"
            style={{ background: 'var(--color-overlay)' }}
          >
            {[
              { id: 'all', label: `All (${counts.all})` },
              { id: 'documents', label: `Docs (${counts.documents})` },
              { id: 'data', label: `Data (${counts.data})` },
              { id: 'charts', label: `Charts (${counts.charts})` },
              { id: 'apis', label: `APIs (${counts.apis})` },
            ].map((tab) => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className="flex-1 py-0.5 rounded text-[9.5px] transition-fast text-center cursor-pointer truncate"
                  style={{
                    background: isActive ? 'var(--color-surface)' : 'transparent',
                    color: isActive ? 'var(--color-text)' : 'var(--color-text-muted)',
                    fontWeight: isActive ? 600 : 500,
                  }}
                >
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* ── Hierarchical Tree with Smooth Custom Scrollbar ──────────── */}
        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-1 flex flex-col gap-0.5 custom-scrollbar">
          <SourceFileTree
            tree={tree}
            filterCategory={activeTab}
            onToggleSource={toggleSource}
            onDeleteSource={handleDeleteSource}
            compact={false}
          />
        </div>

        {/* ── Knowledge Base Summary Card ──────────────────────────────── */}
        <div className="px-3.5 pb-3 flex-shrink-0 relative z-10">
          <div
            className="p-2.5 rounded-lg flex flex-col gap-1.5 transition-fast"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 font-semibold" style={{ color: 'var(--color-text)' }}>
                <HardDrive size={13} strokeWidth={2} style={{ color: 'var(--color-accent)' }} />
                <span className="text-[11px]">Knowledge Base</span>
              </div>
              <span className="text-[10px] font-mono font-medium" style={{ color: 'var(--color-text-muted)' }}>
                {activeCount} / {totalCount} active
              </span>
            </div>

            {/* Storage Meter */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-[9px]" style={{ color: 'var(--color-text-muted)' }}>
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
      </aside>

      {/* Add Directory Modal */}
      <AddSourceDirectoryModal
        isOpen={isAddDirModalOpen}
        onClose={() => setIsAddDirModalOpen(false)}
        onDirectoriesUpdated={fetchCorpus}
        currentDirectories={directories}
      />
    </>
  )
}
