import { useState } from 'react'
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
} from 'lucide-react'
import { showToast } from '../store/toastStore'
import { useThemeStore } from '../store/themeStore'

/**
 * Initial mock data matching models/models.yaml schema exactly:
 * - id: unique model identifier
 * - backend: ollama | vllm | transformers | onnx
 * - model: model artifact identifier or path
 * - task_tags: string array of task capabilities
 */
const INITIAL_MODELS = [
  {
    id: 'coder-model',
    backend: 'ollama',
    model: 'qwen2.5-coder:7b',
    task_tags: ['code_generation', 'code_review', 'debugging'],
    vram_usage: '4.8 GB',
    status: 'active',
  },
  {
    id: 'reasoning-model',
    backend: 'ollama',
    model: 'qwen2.5:14b',
    task_tags: ['summarization', 'drafting', 'approval_notes', 'planning'],
    vram_usage: '6.2 GB',
    status: 'active',
  },
  {
    id: 'vision-model',
    backend: 'ollama',
    model: 'qwen2.5vl:7b',
    task_tags: ['ocr', 'image_understanding', 'diagram_reading'],
    vram_usage: '5.1 GB',
    status: 'active',
  },
  {
    id: 'fast-router',
    backend: 'ollama',
    model: 'phi-3.5-mini',
    task_tags: ['classification', 'routing', 'intent_mapping'],
    vram_usage: '2.2 GB',
    status: 'active',
  },
  {
    id: 'local-llama-safety',
    backend: 'vllm',
    model: 'llama-3.2:3b-instruct',
    task_tags: ['safety_audit', 'compliance_guard', 'interlock_verify'],
    vram_usage: '2.8 GB',
    status: 'active',
  },
]

/**
 * Pre-configured presets for the FR-4 live demo moment.
 */
const MODEL_PRESETS = [
  {
    label: 'DeepSeek-Coder 6.7B',
    id: 'deepseek-coder',
    backend: 'ollama',
    model: 'deepseek-coder:6.7b',
    task_tags: 'code_generation, ast_parsing, unit_tests',
  },
  {
    label: 'Mistral-NeMo 12B',
    id: 'mistral-nemo',
    backend: 'vllm',
    model: 'mistralai/Mistral-Nemo-Instruct-2407',
    task_tags: 'reasoning, multi_turn, long_context',
  },
  {
    label: 'Llama-3.2 Vision 11B',
    id: 'llama-vision-11b',
    backend: 'transformers',
    model: 'meta-llama/Llama-3.2-11B-Vision-Instruct',
    task_tags: 'piping_diagrams, p_and_id_inspection, ocr',
  },
]

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
      safety: true,
      emissions: true,
      telemetry: true,
      market: false,
      audit: false,
    },
  },
  {
    role: 'HSE Specialist',
    badge: 'Safety Compliance Tier',
    description: 'Health, Safety & Environment compliance, runaway prevention guidelines, and safety interlock review.',
    permissions: {
      sops: true,
      safety: true,
      emissions: true,
      telemetry: true,
      market: false,
      audit: true,
    },
  },
  {
    role: 'Superintendent / Approver',
    badge: 'Executive Authorization Tier',
    description: 'Management of Change (MOC) sign-off, critical parameter overrides, and cross-unit economic optimization.',
    permissions: {
      sops: true,
      safety: true,
      emissions: true,
      telemetry: true,
      market: true,
      audit: true,
    },
  },
  {
    role: 'System Administrator',
    badge: 'Infrastructure Tier',
    description: 'Air-gapped model registry orchestration, hardware encryption keys, and network interface security.',
    permissions: {
      sops: true,
      safety: true,
      emissions: true,
      telemetry: true,
      market: true,
      audit: true,
    },
  },
]

const RBAC_CATEGORIES = [
  { id: 'sops', label: 'Operating Manuals & SOPs' },
  { id: 'safety', label: 'Catalyst Runaway Prevention' },
  { id: 'emissions', label: 'Emissions & Environmental Regs' },
  { id: 'telemetry', label: 'Sensor Telemetry & DCS APIs' },
  { id: 'market', label: 'Market Prices & Economics' },
  { id: 'audit', label: 'System & Air-Gap Audit Logs' },
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
  const [models, setModels] = useState(INITIAL_MODELS)

  // Add Model Form State
  const [formData, setFormData] = useState({
    id: '',
    backend: 'ollama',
    model: '',
    task_tags: '',
  })

  const handleApplyPreset = (preset) => {
    setFormData({
      id: preset.id,
      backend: preset.backend,
      model: preset.model,
      task_tags: preset.task_tags,
    })
    showToast(`Preset loaded: ${preset.label}`, 'info')
  }

  const handleAddModel = (e) => {
    e.preventDefault()

    if (!formData.id.trim() || !formData.model.trim()) {
      showToast('Please provide both a Model ID and a Model name/path', 'warning')
      return
    }

    const tagsArray = formData.task_tags
      .split(',')
      .map((t) => t.trim().toLowerCase().replace(/\s+/g, '_'))
      .filter(Boolean)

    const newModel = {
      id: formData.id.trim(),
      backend: formData.backend,
      model: formData.model.trim(),
      task_tags: tagsArray.length > 0 ? tagsArray : ['general_inference'],
      vram_usage: '3.4 GB (Estimated)',
      status: 'active',
    }

    setModels((prev) => [...prev, newModel])
    setFormData({ id: '', backend: 'ollama', model: '', task_tags: '' })

    showToast(
      `FR-4 Live Reload: Model '${newModel.model}' registered to models.yaml & loaded into memory`,
      'success'
    )
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
                  {models.map((m) => (
                    <tr
                      key={m.id}
                      className="transition-fast hover:bg-[var(--color-surface-hover)]"
                    >
                      <td className="py-3 px-4 font-mono font-semibold" style={{ color: 'var(--color-text)' }}>
                        {m.id}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className="font-mono text-[10px] px-2 py-0.5 rounded font-medium uppercase"
                          style={{
                            background:
                              m.backend === 'ollama'
                                ? 'rgba(234, 88, 12, 0.12)'
                                : m.backend === 'vllm'
                                ? 'rgba(59, 130, 246, 0.12)'
                                : 'rgba(168, 85, 247, 0.12)',
                            color:
                              m.backend === 'ollama'
                                ? 'var(--color-accent)'
                                : m.backend === 'vllm'
                                ? '#2563EB'
                                : '#9333EA',
                            border: '1px solid var(--color-border)',
                          }}
                        >
                          {m.backend}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                        {m.model}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {m.task_tags.map((tag) => (
                            <span
                              key={tag}
                              className="inline-block text-[10px] px-2 py-0.5 rounded font-medium"
                              style={{
                                background: 'var(--color-overlay)',
                                color: 'var(--color-text-muted)',
                              }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
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
                          Loaded
                        </span>
                      </td>
                    </tr>
                  ))}
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
                    {RBAC_CATEGORIES.map((cat) => (
                      <th key={cat.id} className="py-2.5 px-3 text-center">
                        {cat.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
                  {RBAC_TIERS.map((tier) => (
                    <tr
                      key={tier.role}
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
                      {RBAC_CATEGORIES.map((cat) => {
                        const hasAccess = tier.permissions[cat.id]
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
            SECTION 3: Portable Drive & Encryption Status (NFR-2 / NFR-3)
           ───────────────────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-4">
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
                Hardware isolation, BitLocker/LUKS2 encryption, and localized offline storage gauge (NFR-2, NFR-3).
              </p>
            </div>
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
                      Portable Drive: Mounted &amp; Encrypted
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
                    <span>Device: <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>/dev/mapper/sovereign-storage</strong></span>
                    <span>· Mount: <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>/media/sovereign-data</strong></span>
                  </div>
                </div>
              </div>

              {/* Encryption Pills — Wraps properly on narrower viewports without clipping */}
              <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
                <div
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap"
                  style={{
                    background: 'var(--color-error-tint)',
                    border: '1px solid var(--color-accent-border)',
                    color: 'var(--color-accent)',
                  }}
                >
                  <Lock size={12} strokeWidth={2.4} />
                  <span>LUKS2 / AES-256-XTS</span>
                </div>
                <div
                  className="px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap"
                  style={{
                    background: 'var(--color-overlay)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  FIPS 140-3 Validated
                </div>
              </div>
            </div>

            {/* Storage Meter Bar (matching Knowledge Base card pattern) */}
            <div className="flex flex-col gap-2 pt-1 min-w-0">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-xs min-w-0">
                <span className="font-medium whitespace-nowrap" style={{ color: 'var(--color-text)' }}>
                  Total Encrypted Storage Capacity
                </span>
                <span className="font-mono font-semibold break-words text-left sm:text-right" style={{ color: 'var(--color-accent)' }}>
                  246.8 GB used / 512.0 GB <span className="opacity-80 font-normal">(48.2% utilized · 265.2 GB free)</span>
                </span>
              </div>

              {/* Segmented Progress Bar */}
              <div
                className="w-full h-3 rounded-md overflow-hidden flex"
                style={{ background: 'var(--color-overlay)' }}
              >
                <div
                  style={{ width: '22%', background: 'var(--color-accent)' }}
                  title="Model Weights (GGUF / Safetensors): 112.4 GB"
                />
                <div
                  style={{ width: '13%', background: '#2563EB' }}
                  title="Milvus Vector DB (Dense + BM25): 64.2 GB"
                />
                <div
                  style={{ width: '9%', background: '#059669' }}
                  title="Engineering Document Corpus: 48.8 GB"
                />
                <div
                  style={{ width: '4.2%', background: '#D97706' }}
                  title="Audit Trails & System Cache: 21.4 GB"
                />
              </div>

              {/* Segment Legend */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {[
                  { label: 'Model Weights (GGUF)', size: '112.4 GB', color: 'var(--color-accent)' },
                  { label: 'Milvus Vector DB', size: '64.2 GB', color: '#2563EB' },
                  { label: 'Document Corpus', size: '48.8 GB', color: '#059669' },
                  { label: 'Audit Logs & Cache', size: '21.4 GB', color: '#D97706' },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-2 p-2 rounded-lg border text-left"
                    style={{
                      background: 'var(--color-surface)',
                      borderColor: 'var(--color-border)',
                    }}
                  >
                    <div className="w-2 h-2 rounded-xs flex-shrink-0" style={{ background: item.color }} />
                    <div className="min-w-0">
                      <div className="text-[10px] truncate leading-tight" style={{ color: 'var(--color-text-muted)' }}>
                        {item.label}
                      </div>
                      <div className="font-mono text-xs font-bold leading-tight mt-0.5" style={{ color: 'var(--color-text)' }}>
                        {item.size}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Hardware Isolation Checklist */}
            <div
              className="p-3.5 rounded-xl border flex flex-col gap-2"
              style={{
                background: 'var(--color-surface)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-faint)' }}>
                Air-Gapped Sovereign Security Envelope
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                {[
                  'AES-256-XTS hardware block encryption active on mount',
                  'Zero outbound sockets: Loopback bound only (CARD 07 verified)',
                  'Read-only model weight partition prevents run-time tampering',
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
