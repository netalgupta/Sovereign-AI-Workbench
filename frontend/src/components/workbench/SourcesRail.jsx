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

  useEffect(() => {
    fetch('/api/corpus')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.sources && Array.isArray(data.sources)) {
          setSources(data.sources)
        }
      })
      .catch(() => {})
  }, [])

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
              <span>MRPL Engineering Corpus</span>
              <span className="font-mono font-medium">2.50 MB (13 files)</span>
            </div>
            <div
              className="w-full h-1.5 rounded-sm overflow-hidden"
              style={{ background: 'var(--color-overlay)' }}
            >
              <div
                className="h-full rounded-sm transition-base"
                style={{
                  width: '100%',
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
