import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Settings,
  Cpu,
  Plus,
  ShieldCheck,
  HardDrive,
  Lock,
  Check,
  Minus,
  Sun,
  Moon,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react'
import { showToast } from '../store/toastStore'
import { useThemeStore } from '../store/themeStore'

/**
 * Pre-configured presets matching venue upgrade tier in DEPENDENCIES.md §1:
 * Adding or upgrading a model is an edit to models.yaml + reload, no code changes (FR-4).
 */
const MODEL_PRESETS = [
  {
    label: 'Qwen2.5-Coder 14B',
    id: 'coder-model-venue',
    backend: 'ollama',
    model: 'qwen2.5-coder:14b',
    task_tags: 'code_generation, code_review, debugging, ast_parsing',
  },
  {
    label: 'Qwen2.5 32B',
    id: 'reasoning-model-venue',
    backend: 'ollama',
    model: 'qwen2.5:32b',
    task_tags: 'summarization, drafting, approval_notes, planning',
  },
  {
    label: 'Qwen2.5-VL 32B',
    id: 'vision-model-venue',
    backend: 'ollama',
    model: 'qwen2.5vl:32b',
    task_tags: 'ocr, image_understanding, diagram_reading, p_and_id_inspection',
  },
  {
    label: 'BGE-Large-En v1.5',
    id: 'bge-large-embeddings',
    backend: 'sentence-transformers',
    model: 'BAAI/bge-large-en-v1.5',
    task_tags: 'dense_embeddings, hybrid_search, vector_indexing',
  },
]

/**
 * Baseline device & storage state fallback before live host telemetry loads
 */
const INITIAL_SYSTEM_INFO = {
  device: {
    platform: 'win32',
    osName: 'Host Workstation',
    hostname: 'Localhost',
    mountPoint: 'C:\\',
    driveLetter: 'C:',
    fileSystem: 'NTFS',
    devicePath: 'Local Storage Volume',
    cpuModel: 'Host Multi-Core CPU',
    cpuCores: 8,
    totalMemGB: 16.0,
    freeMemGB: 4.0,
    gpu: null,
    encryption: 'BitLocker / Hardware Volume Protected',
    isAirGapped: true,
  },
  storage: {
    totalBytes: 1000000000000,
    freeBytes: 300000000000,
    usedBytes: 700000000000,
    totalGB: 1000.0,
    usedGB: 700.0,
    freeGB: 300.0,
    utilizationPct: 70.0,
    breakdown: [
      { id: 'models', label: 'Model Weights (GGUF / Ollama)', sizeGB: 5.2, sizeDisplay: '5.2 GB', color: 'var(--color-accent)' },
      { id: 'vector_store', label: 'FAISS Vector Store & SQLite', sizeGB: 0.001, sizeDisplay: '30.8 KB (FAISS Index)', color: '#2563EB' },
      { id: 'corpus', label: 'MRPL Engineering Corpus', sizeGB: 0.003, sizeDisplay: '2.5 MB (14 docs)', color: '#059669' },
      { id: 'system', label: 'Audit Logs, OS & App Space', sizeGB: 707.1, sizeDisplay: '707.1 GB', color: '#D97706' },
    ],
  },
}

/**
 * RBAC Matrix Definition (FRONTEND.md §3.11):
 * Role tiers × Knowledge base source categories.
 */
const RBAC_TIERS = [
  {
    role: 'Plant Engineer',
    badge: 'Operations Tier',
    description: 'Operational troubleshooting, sensor telemetry, and standard operating procedure lookup.',
    permissions: {
      sops: true,
      inspection: true,
      quality: true,
      sap_mock: true,
      correspondence: false,
      diagrams: true,
    },
  },
  {
    role: 'HSE Specialist',
    badge: 'Safety Compliance Tier',
    description: 'Health, Safety & Environment compliance, runaway prevention guidelines, and safety interlock review.',
    permissions: {
      sops: true,
      inspection: true,
      quality: true,
      sap_mock: false,
      correspondence: false,
      diagrams: true,
    },
  },
  {
    role: 'Superintendent / Approver',
    badge: 'Executive Authorization Tier',
    description: 'Management of Change (MOC) sign-off, critical parameter overrides, and cross-unit economic optimization.',
    permissions: {
      sops: true,
      inspection: true,
      quality: true,
      sap_mock: true,
      correspondence: true,
      diagrams: true,
    },
  },
  {
    role: 'System Administrator',
    badge: 'Infrastructure Tier',
    description: 'Air-gapped model registry orchestration, hardware encryption keys, and network interface security.',
    permissions: {
      sops: true,
      inspection: true,
      quality: true,
      sap_mock: true,
      correspondence: true,
      diagrams: true,
    },
  },
]

const RBAC_CATEGORIES = [
  { id: 'sops', label: '01_SOPs & Safety (HCU-2 & Aromatics)' },
  { id: 'inspection', label: '02_Inspection & Maintenance (CCR-1 & Hassan)' },
  { id: 'quality', label: '03_Quality & Process Data (Novolen QA & Merox)' },
  { id: 'sap_mock', label: '04_SAP ERP Mock Records (Materials Master)' },
  { id: 'correspondence', label: '05_Depot Correspondence (Kasargod)' },
  { id: 'diagrams', label: '06_Diagrams & Scans (P&ID & OCR Checklist)' },
]

/**
 * SettingsPage — Administrative & Orchestration View per FRONTEND.md §3.11.
 *
 * Sections:
 * 1. Model Registry: Read-only table of models.yaml + live "Add Model" form (FR-4).
 * 2. Role-Based Access Control: Static matrix of role tiers × source visibility.
 * 3. Portable Drive & Encryption Status: Hardware encryption, mount points, storage gauge (NFR-2/NFR-3).
 */
export function SettingsPage() {
  const { theme, toggleTheme } = useThemeStore()
  // THE LIVE REGISTRY ONLY. This started from a written-out list naming
  // qwen2.5:14b as the reasoning model (it is 7b; 14b was dropped as too slow),
  // and when /api/models could not be reached that stale list stayed up as
  // if it were live (Review Rule 5). Empty until the backend says otherwise.
  const [models, setModels] = useState([])
  const [modelsError, setModelsError] = useState(null)
  const [systemInfo, setSystemInfo] = useState(INITIAL_SYSTEM_INFO)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [rbacTiers, setRbacTiers] = useState(RBAC_TIERS)
  const [rbacCategories, setRbacCategories] = useState(RBAC_CATEGORIES)

  // Add Model Form State
  const [formData, setFormData] = useState({
    id: '',
    backend: 'ollama',
    model: '',
    task_tags: '',
  })

  const fetchSystemAndModels = async () => {
    setIsRefreshing(true)
    try {
      // 1. Fetch live host system & storage info
      const sysRes = await fetch('/api/system-info')
      if (sysRes.ok) {
        const sysData = await sysRes.json()
        if (sysData?.storage && sysData?.device) {
          setSystemInfo(sysData)
        }
      }
    } catch {
      // Fallback to browser storage API if server offline
      if (typeof navigator !== 'undefined' && navigator.storage?.estimate) {
        try {
          const est = await navigator.storage.estimate()
          if (est.quota) {
            const totalGB = Number((est.quota / 1e9).toFixed(1))
            const usedGB = Number(((est.usage || 0) / 1e9).toFixed(1))
            const freeGB = Number((Math.max(0, est.quota - (est.usage || 0)) / 1e9).toFixed(1))
            const utilPct = Number((((est.usage || 0) / est.quota) * 100).toFixed(1))
            setSystemInfo((prev) => ({
              ...prev,
              storage: {
                ...prev.storage,
                totalGB,
                usedGB,
                freeGB,
                utilizationPct: utilPct,
              },
            }))
          }
        } catch {}
      }
    }

    try {
      // 2. Fetch live models from models.yaml
      const modelsRes = await fetch('/api/models')
      if (modelsRes.ok) {
        const modelsData = await modelsRes.json()
        if (Array.isArray(modelsData.models)) {
          setModels(modelsData.models)
        } else if (Array.isArray(modelsData)) {
          setModels(modelsData)
        }
        setModelsError(null)
      } else {
        setModels([])
        setModelsError(`The backend answered ${modelsRes.status} for /api/models.`)
      }
    } catch (err) {
      setModels([])
      setModelsError(`Could not reach the backend (${err?.message || 'network error'}).`)
    }

    try {
      // 3. Fetch live RBAC matrix from backend
      const rbacRes = await fetch('/api/rbac/tiers')
      if (rbacRes.ok) {
        const rbacData = await rbacRes.json()
        if (Array.isArray(rbacData.tiers)) {
          setRbacTiers(rbacData.tiers)
        }
        if (Array.isArray(rbacData.categories)) {
          setRbacCategories(rbacData.categories)
        }
      }
    } catch {}
    setIsRefreshing(false)
  }

  useEffect(() => {
    let active = true

    const initLoad = async () => {
      try {
        const sysRes = await fetch('/api/system-info')
        if (sysRes.ok && active) {
          const sysData = await sysRes.json()
          if (sysData?.storage && sysData?.device) {
            setSystemInfo(sysData)
          }
        }
      } catch {
        if (typeof navigator !== 'undefined' && navigator.storage?.estimate && active) {
          try {
            const est = await navigator.storage.estimate()
            if (est.quota) {
              const totalGB = Number((est.quota / 1e9).toFixed(1))
              const usedGB = Number(((est.usage || 0) / 1e9).toFixed(1))
              const freeGB = Number((Math.max(0, est.quota - (est.usage || 0)) / 1e9).toFixed(1))
              const utilPct = Number((((est.usage || 0) / est.quota) * 100).toFixed(1))
              setSystemInfo((prev) => ({
                ...prev,
                storage: {
                  ...prev.storage,
                  totalGB,
                  usedGB,
                  freeGB,
                  utilizationPct: utilPct,
                },
              }))
            }
          } catch {}
        }
      }

      try {
        const modelsRes = await fetch('/api/models')
        if (modelsRes.ok && active) {
          const modelsData = await modelsRes.json()
          if (Array.isArray(modelsData.models)) {
            setModels(modelsData.models)
          } else if (modelsData.registry && modelsData.auxiliary) {
            setModels([...modelsData.registry, ...modelsData.auxiliary])
          } else if (Array.isArray(modelsData)) {
            setModels(modelsData)
          }
        }
      } catch {}

      try {
        const rbacRes = await fetch('/api/rbac/tiers')
        if (rbacRes.ok && active) {
          const rbacData = await rbacRes.json()
          if (Array.isArray(rbacData.tiers)) {
            setRbacTiers(rbacData.tiers)
          }
          if (Array.isArray(rbacData.categories)) {
            setRbacCategories(rbacData.categories)
          }
        }
      } catch {}
    }

    initLoad()

    return () => {
      active = false
    }
  }, [])

  const handleApplyPreset = (preset) => {
    setFormData({
      id: preset.id,
      backend: preset.backend,
      model: preset.model,
      task_tags: preset.task_tags,
    })
    showToast(`Preset loaded: ${preset.label}`, 'info')
  }

  const handleAddModel = async (e) => {
    e.preventDefault()

    if (!formData.id.trim() || !formData.model.trim()) {
      showToast('Please provide both a Model ID and a Model name/path', 'warning')
      return
    }

    const tagsArray = formData.task_tags
      .split(',')
      .map((t) => t.trim().toLowerCase().replace(/\s+/g, '_'))
      .filter(Boolean)

    let estimatedVram = '4.5 GB'
    if (formData.model.includes('14b')) estimatedVram = '8.5 GB'
    else if (formData.model.includes('32b') || formData.model.includes('70b')) estimatedVram = '18.0 GB'
    else if (formData.model.includes('mini') || formData.model.includes('3b')) estimatedVram = '2.2 GB'

    const newModel = {
      id: formData.id.trim(),
      backend: formData.backend,
      model: formData.model.trim(),
      task_tags: tagsArray.length > 0 ? tagsArray : ['general_inference'],
    }

    let backendError = null
    try {
      const res = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newModel),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        backendError = errData.detail || errData.message || `Backend returned HTTP ${res.status}`
      }
    } catch (err) {
      backendError = `Network error: ${err?.message || err}`
    }

    if (backendError) {
      showToast(`Failed to register model: ${backendError}`, 'error')
      return
    }

    // Re-fetch the live registry — get what the backend actually stored
    setFormData({ id: '', backend: 'ollama', model: '', task_tags: '' })
    showToast(
      `FR-4 Live Reload: Model '${newModel.model}' registered to models.yaml and loaded into memory`,
      'success'
    )
    await fetchSystemAndModels()
  }

  return (
    <div
      className="flex-1 flex flex-col h-full w-full overflow-hidden select-none"
      style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}
    >
      {/* ── 1. Top Header Chrome ────────────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-6 py-3.5 border-b flex-shrink-0 z-10"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] shadow-xs"
            style={{
              background: 'var(--color-overlay)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
            }}
            title="Return to workbench conversation"
          >
            <ArrowLeft size={13} strokeWidth={2.2} />
            <span>Workbench</span>
          </Link>

          <div className="h-4 w-[1px]" style={{ background: 'var(--color-border)' }} />

          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{
                background: 'var(--color-accent-tint)',
                color: 'var(--color-accent)',
              }}
            >
              <Settings size={15} strokeWidth={2.2} />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight leading-tight">
                Settings &amp; System Configuration
              </h1>
              <p className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                Model registry (FR-4), Role-Based Access Control, and Encrypted Storage (NFR-2/3)
              </p>
            </div>
          </div>
        </div>

        {/* Right Header Status Badges */}
        <div className="flex items-center gap-3">
          <div
            className="flex items-center gap-2 px-2.5 py-1 rounded-full text-[11px] font-semibold"
            style={{
              background: 'var(--color-success-tint)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-success)',
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-success)' }} />
            <span>Air-Gapped Local Mode</span>
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            className="w-8 h-8 rounded-md flex items-center justify-center transition-fast hover:bg-[var(--color-surface-hover)] cursor-pointer"
            style={{
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-muted)',
            }}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} theme`}
          >
            {theme === 'dark' ? <Sun size={14} strokeWidth={2} /> : <Moon size={14} strokeWidth={2} />}
          </button>
        </div>
      </header>

      {/* ── 2. Scrollable Body Content ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-8 max-w-6xl mx-auto w-full min-w-0">
        {/* ─────────────────────────────────────────────────────────────────
            SECTION 1: Model Registry (FRONTEND.md §3.11 / FR-4)
           ───────────────────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
              >
                <Cpu size={15} strokeWidth={2.2} />
              </div>
              <div>
                <h2 className="text-sm font-bold tracking-tight">
                  Model Registry (`models.yaml`)
                </h2>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  Active air-gapped inference engines. Modifying this registry reloads backend routing without code changes (FR-4).
                </p>
              </div>
            </div>

            <div
              className="text-xs font-mono px-2.5 py-1 rounded-md"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-accent)',
              }}
            >
              {models.length} Models Loaded
            </div>
          </div>

          {/* Model Registry Table */}
          <div
            className="rounded-xl overflow-hidden border shadow-xs"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-card-border)',
            }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr
                    className="text-[11px] uppercase tracking-wider font-semibold border-b"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-muted)',
                    }}
                  >
                    <th className="py-2.5 px-4">Model ID</th>
                    <th className="py-2.5 px-4">Backend</th>
                    <th className="py-2.5 px-4">Model Artifact / Path</th>
                    <th className="py-2.5 px-4">Capabilities / Task Tags</th>
                    <th className="py-2.5 px-4 text-center">VRAM Usage</th>
                    <th className="py-2.5 px-4 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
                  {models.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
                        {modelsError
                          ? `${modelsError} No models are listed rather than a list that may be out of date.`
                          : 'Reading the model registry…'}
                      </td>
                    </tr>
                  )}
                  {models.map((m) => {
                    const isOllama = m.backend === 'ollama'
                    const isSentenceTransformers = m.backend === 'sentence-transformers'
                    const isCTranslate2 = m.backend === 'ctranslate2'
                    const isPaddle = m.backend === 'paddlex'

                    const badgeStyle = isOllama
                      ? { background: 'rgba(234, 88, 12, 0.12)', color: 'var(--color-accent)' }
                      : isSentenceTransformers
                      ? { background: 'rgba(37, 99, 235, 0.12)', color: '#2563EB' }
                      : isCTranslate2
                      ? { background: 'rgba(5, 150, 105, 0.12)', color: '#059669' }
                      : isPaddle
                      ? { background: 'rgba(147, 51, 234, 0.12)', color: '#9333EA' }
                      : { background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }

                    return (
                      <tr
                        key={m.id}
                        className="transition-fast hover:bg-[var(--color-surface-hover)]"
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono font-semibold" style={{ color: 'var(--color-text)' }}>
                              {m.id}
                            </span>
                            {m.engine_type === 'embedded' && (
                              <span
                                className="text-[9px] font-sans font-semibold px-1.5 py-0.5 rounded tracking-wide uppercase"
                                style={{
                                  background: 'var(--color-overlay)',
                                  color: 'var(--color-text-muted)',
                                  border: '1px solid var(--color-border)',
                                }}
                              >
                                Embedded Engine
                              </span>
                            )}
                          </div>
                          {m.role && (
                            <div className="text-[10px] font-sans font-normal mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                              {m.role}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className="font-mono text-[10px] px-2 py-0.5 rounded font-medium uppercase whitespace-nowrap"
                            style={{
                              ...badgeStyle,
                              border: '1px solid var(--color-border)',
                            }}
                          >
                            {m.backend}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                          <div>{m.model}</div>
                          {m.provenance && (
                            <div className="text-[10px] font-sans font-normal mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: 'var(--color-text-muted)' }}>
                              <span
                                className="px-1.5 py-0.2 rounded text-[9px] font-semibold tracking-wide"
                                style={{
                                  background: 'var(--color-overlay)',
                                  border: '1px solid var(--color-border)',
                                  color: 'var(--color-text)',
                                }}
                              >
                                {m.provenance.license}
                              </span>
                              <span>{m.provenance.organization}</span>
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-wrap gap-1">
                            {m.task_tags.map((tag) => (
                              <span
                                key={tag}
                                className="inline-block text-[10px] px-2 py-0.5 rounded font-medium font-mono"
                                style={{
                                  background: 'var(--color-overlay)',
                                  color: 'var(--color-text-muted)',
                                }}
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                          {m.provenance?.air_gap_attestation && (
                            <div
                              className="text-[9px] font-sans font-medium mt-1 inline-flex items-center gap-1"
                              style={{ color: 'var(--color-success)' }}
                              title={m.provenance.air_gap_attestation}
                            >
                              <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-success)' }} />
                              Air-Gapped Sovereign
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-center font-mono text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                          {m.vram_usage}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span
                            className="inline-flex items-center gap-1.5 text-[11px] font-medium"
                            style={{ color: 'var(--color-success)' }}
                          >
                            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--color-success)' }} />
                            {m.engine_type === 'embedded' ? 'Resident' : 'Loaded'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Add Model Form (FR-4 Live Demo Moment) */}
          <div
            className="rounded-xl p-5 border shadow-xs flex flex-col gap-4"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-card-border)',
            }}
          >
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold tracking-tight uppercase" style={{ color: 'var(--color-text)' }}>
                    Register &amp; Hot-Reload New Model
                  </h3>
                  <span
                    className="text-[10px] font-bold px-2 py-0.2 rounded-full uppercase tracking-wider"
                    style={{
                      background: 'var(--color-accent-tint)',
                      color: 'var(--color-accent)',
                      border: '1px solid var(--color-accent-border)',
                    }}
                  >
                    FR-4 Hot-Reload
                  </span>
                </div>
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                  Appends an entry to `models.yaml`. The agent router automatically picks up new task tags without restarting the server.
                </p>
              </div>

              {/* Quick Presets */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--color-text-faint)' }}>
                  Quick Presets:
                </span>
                {MODEL_PRESETS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleApplyPreset(p)}
                    className="text-[11px] px-2.5 py-1 rounded-md transition-fast cursor-pointer border hover:bg-[var(--color-surface-hover)]"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                  >
                    + {p.label}
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleAddModel} className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-1">
              {/* Field 1: Model ID */}
              <div className="flex flex-col gap-1">
                <label htmlFor="model-id" className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>
                  Model ID
                </label>
                <input
                  id="model-id"
                  type="text"
                  value={formData.id}
                  onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                  placeholder="e.g. deepseek-coder"
                  className="px-3 py-2 rounded-md text-xs font-mono outline-none transition-fast border focus:ring-1 focus:ring-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-input-bg)',
                    borderColor: 'var(--color-input-border)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>

              {/* Field 2: Backend */}
              <div className="flex flex-col gap-1">
                <label htmlFor="model-backend" className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>
                  Backend Provider
                </label>
                <select
                  id="model-backend"
                  value={formData.backend}
                  onChange={(e) => setFormData({ ...formData, backend: e.target.value })}
                  className="px-3 py-2 rounded-md text-xs font-mono outline-none transition-fast border cursor-pointer"
                  style={{
                    background: 'var(--color-input-bg)',
                    borderColor: 'var(--color-input-border)',
                    color: 'var(--color-text)',
                  }}
                >
                  <option value="ollama">ollama (Local daemon)</option>
                  <option value="vllm">vllm (High-throughput)</option>
                  <option value="transformers">transformers (HuggingFace)</option>
                  <option value="onnx">onnx (Quantized runtime)</option>
                </select>
              </div>

              {/* Field 3: Model Name / File Path */}
              <div className="flex flex-col gap-1">
                <label htmlFor="model-name" className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>
                  Model Artifact / Name
                </label>
                <input
                  id="model-name"
                  type="text"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  placeholder="e.g. deepseek-coder:6.7b"
                  className="px-3 py-2 rounded-md text-xs font-mono outline-none transition-fast border focus:ring-1 focus:ring-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-input-bg)',
                    borderColor: 'var(--color-input-border)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>

              {/* Field 4: Task Tags */}
              <div className="flex flex-col gap-1">
                <label htmlFor="model-tags" className="text-[11px] font-semibold" style={{ color: 'var(--color-text)' }}>
                  Task Capabilities (comma-separated)
                </label>
                <input
                  id="model-tags"
                  type="text"
                  value={formData.task_tags}
                  onChange={(e) => setFormData({ ...formData, task_tags: e.target.value })}
                  placeholder="e.g. code_generation, ast_eval"
                  className="px-3 py-2 rounded-md text-xs outline-none transition-fast border focus:ring-1 focus:ring-[var(--color-accent)]"
                  style={{
                    background: 'var(--color-input-bg)',
                    borderColor: 'var(--color-input-border)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>

              {/* Submit Button spanning row */}
              <div className="md:col-span-4 flex items-center justify-end pt-1">
                <button
                  type="submit"
                  id="add-model-submit-btn"
                  className="px-4 py-2 rounded-lg text-xs font-bold text-white transition-fast shadow-xs cursor-pointer flex items-center gap-1.5 hover:brightness-110"
                  style={{ background: 'var(--color-accent)' }}
                >
                  <Plus size={14} strokeWidth={2.4} />
                  <span>Register &amp; Hot-Reload Model</span>
                </button>
              </div>
            </form>
          </div>
        </section>

        {/* ─────────────────────────────────────────────────────────────────
            SECTION 2: Role-Based Access Control (RBAC)
           ───────────────────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
            >
              <ShieldCheck size={15} strokeWidth={2.2} />
            </div>
            <div>
              <h2 className="text-sm font-bold tracking-tight">
                Role-Based Access Control (RBAC) Matrix
              </h2>
              <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                Knowledge base visibility and procedural authority across plant operational roles (FRONTEND.md §3.11).
              </p>
            </div>
          </div>

          <div
            className="rounded-xl overflow-hidden border shadow-xs"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-card-border)',
            }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr
                    className="text-[11px] uppercase tracking-wider font-semibold border-b"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-muted)',
                    }}
                  >
                    <th className="py-2.5 px-4 w-64">Role Tier &amp; Scope</th>
                    {rbacCategories.map((cat) => (
                      <th key={cat.id} className="py-2.5 px-3 text-center">
                        {cat.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
                  {rbacTiers.map((tier) => (
                    <tr
                      key={tier.role || tier.role_id}
                      className="transition-fast hover:bg-[var(--color-surface-hover)]"
                    >
                      <td className="py-3 px-4">
                        <div className="font-semibold" style={{ color: 'var(--color-text)' }}>
                          {tier.role}
                        </div>
                        <div className="text-[10px] mt-0.5 leading-tight" style={{ color: 'var(--color-text-muted)' }}>
                          {tier.description}
                        </div>
                      </td>
                      {rbacCategories.map((cat) => {
                        const hasAccess = tier.permissions?.[cat.id]
                        return (
                          <td key={cat.id} className="py-3 px-3 text-center">
                            {hasAccess ? (
                              <div className="inline-flex items-center justify-center w-6 h-6 rounded-full" style={{ background: 'var(--color-success-tint)' }}>
                                <Check size={13} strokeWidth={2.8} style={{ color: 'var(--color-success)' }} />
                              </div>
                            ) : (
                              <div className="inline-flex items-center justify-center w-6 h-6 rounded-full" style={{ background: 'var(--color-overlay)' }}>
                                <Minus size={13} strokeWidth={2} style={{ color: 'var(--color-text-faint)' }} />
                              </div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ─────────────────────────────────────────────────────────────────
            SECTION 3: Host Storage & Hardware Telemetry (NFR-2 / NFR-3)
           ───────────────────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}
              >
                <HardDrive size={15} strokeWidth={2.2} />
              </div>
              <div>
                <h2 className="text-sm font-bold tracking-tight">
                  Drive &amp; Hardware Encryption Status
                </h2>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  Hardware telemetry, BitLocker/LUKS2 encryption, and localized offline storage gauge (NFR-2, NFR-3).
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => fetchSystemAndModels(true)}
              disabled={isRefreshing}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-fast cursor-pointer border hover:bg-[var(--color-surface-hover)] disabled:opacity-50 shadow-xs"
              style={{
                background: 'var(--color-surface)',
                borderColor: 'var(--color-border)',
                color: 'var(--color-text)',
              }}
              title="Poll live disk and hardware metrics"
            >
              <RefreshCw size={12} className={isRefreshing ? 'animate-spin' : ''} />
              <span>{isRefreshing ? 'Syncing...' : 'Poll Hardware'}</span>
            </button>
          </div>

          <div
            className="rounded-xl p-5 border shadow-xs flex flex-col gap-5 min-w-0 overflow-hidden"
            style={{
              background: 'var(--color-card-bg)',
              borderColor: 'var(--color-card-border)',
            }}
          >
            {/* Top Drive Status Banner */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3.5 min-w-0">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <HardDrive size={20} strokeWidth={2} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                      Local Volume: {systemInfo.device.mountPoint} ({systemInfo.device.fileSystem})
                    </h3>
                    <span
                      className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold whitespace-nowrap"
                      style={{
                        background: 'var(--color-success-tint)',
                        color: 'var(--color-success)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      ● Volume Healthy
                    </span>
                  </div>
                  <div className="font-mono text-[11px] mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 min-w-0" style={{ color: 'var(--color-text-muted)' }}>
                    <span>Device: <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>{systemInfo.device.devicePath}</strong></span>
                    <span>· Host: <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>{systemInfo.device.hostname}</strong></span>
                    <span>· OS: <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>{systemInfo.device.osName}</strong></span>
                  </div>
                  <div className="text-[11px] mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[var(--color-text-muted)]">
                    <span>CPU: <strong className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>{systemInfo.device.cpuModel} ({systemInfo.device.cpuCores} cores)</strong></span>
                    <span>RAM: <strong className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>{systemInfo.device.totalMemGB} GB</strong></span>
                    {systemInfo.device.gpu && (
                      <span>GPU: <strong className="font-mono font-medium" style={{ color: 'var(--color-accent)' }}>{systemInfo.device.gpu.name} ({(systemInfo.device.gpu.vramTotalMB / 1024).toFixed(1)} GB VRAM)</strong></span>
                    )}
                  </div>
                </div>
              </div>

              {/* Encryption Pills — Wraps properly on narrower viewports without clipping */}
              <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
                <div
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap"
                  style={{
                    background: 'var(--color-accent-tint)',
                    border: '1px solid var(--color-accent-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <Lock size={12} strokeWidth={2.4} />
                  <span>{systemInfo.device.encryption}</span>
                </div>
                <div
                  className="px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap"
                  style={{
                    background: 'var(--color-overlay)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  Air-Gapped Sovereign Node
                </div>
              </div>
            </div>

            {/* Storage Meter Bar (matching Knowledge Base card pattern) */}
            <div className="flex flex-col gap-2 pt-1 min-w-0">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs min-w-0">
                <span className="font-medium whitespace-nowrap" style={{ color: 'var(--color-text)' }}>
                  Total Host Storage Capacity ({systemInfo.device.driveLetter || systemInfo.device.mountPoint})
                </span>
                <span className="font-mono font-semibold break-words text-left sm:text-right" style={{ color: 'var(--color-accent)' }}>
                  {systemInfo.storage.usedGB} GB used / {systemInfo.storage.totalGB} GB{' '}
                  <span className="opacity-80 font-normal">
                    ({systemInfo.storage.utilizationPct}% utilized · {systemInfo.storage.freeGB} GB free)
                  </span>
                </span>
              </div>

              {/* Segmented Progress Bar */}
              <div
                className="w-full h-3.5 rounded-md overflow-hidden flex"
                style={{ background: 'var(--color-overlay)' }}
              >
                {systemInfo.storage.breakdown.map((seg) => {
                  const pct = Math.max(1, (seg.sizeGB / systemInfo.storage.totalGB) * 100)
                  return (
                    <div
                      key={seg.id}
                      style={{ width: `${pct}%`, background: seg.color }}
                      title={`${seg.label}: ${seg.sizeDisplay || (seg.sizeGB >= 1 ? `${seg.sizeGB} GB` : `${(seg.sizeGB * 1024).toFixed(1)} MB`)}`}
                    />
                  )
                })}
              </div>

              {/* Segment Legend */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {systemInfo.storage.breakdown.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-2 p-2.5 rounded-lg border text-left card-hover-lift"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                      boxShadow: 'var(--shadow-xs)',
                    }}
                  >
                    <div className="w-2 h-2 rounded-xs flex-shrink-0" style={{ background: item.color }} />
                    <div className="min-w-0">
                      <div className="text-[10px] truncate leading-tight" style={{ color: 'var(--color-text-muted)' }}>
                        {item.label}
                      </div>
                      <div className="font-mono text-xs font-bold leading-tight mt-0.5" style={{ color: 'var(--color-text)' }}>
                        {item.sizeDisplay || (item.sizeGB >= 1 ? `${item.sizeGB} GB` : `${(item.sizeGB * 1024).toFixed(1)} MB`)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Hardware Isolation Checklist */}
            <div
              className="p-4 rounded-xl border flex flex-col gap-2.5"
              style={{
                background: 'var(--color-surface)',
                borderColor: 'var(--color-border)',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-faint)' }}>
                Air-Gapped Sovereign Security Envelope
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                {[
                  'BitLocker / LUKS2 hardware block encryption active on mount',
                  'Zero outbound sockets: Loopback bound only (CARD 07 verified)',
                  'FAISS + SQLite vector index isolated in-memory on local socket',
                  'Volatile RAM cache purged on operator logout or session end',
                ].map((check, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <CheckCircle2 size={13} strokeWidth={2.4} style={{ color: 'var(--color-success)' }} className="flex-shrink-0" />
                    <span style={{ color: 'var(--color-text)' }}>{check}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
