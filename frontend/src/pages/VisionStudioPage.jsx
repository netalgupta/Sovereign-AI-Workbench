import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Image as ImageIcon,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Eye,
  Scan,
  Maximize2,
  Search,
  ExternalLink,
  Layers,
  Sparkles,
  Info,
} from 'lucide-react'
import { api } from '../lib/pipelineApi'
import { DefectOverlay } from '../integrations/defect-overlay'
import { springs, buttonTapMotion } from '../lib/motion'

export function VisionStudioPage() {
  const [imagesData, setImagesData] = useState([])
  const [selectedImage, setSelectedImage] = useState(null)
  const [filterMode, setFilterMode] = useState('all') // 'all' | 'estimates' | 'verified' | 'scans'
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [overlayActive, setOverlayActive] = useState(true)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)

    api.images()
      .then((res) => {
        if (cancelled) return
        const list = res?.images || []
        setImagesData(list)
        if (list.length > 0) setSelectedImage(list[0])
      })
      .catch((err) => console.warn('Images load error:', err))
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const filteredImages = imagesData.filter((img) => {
    const isEstimate = Boolean(img.description_is_estimate || img.scored?.is_estimate)
    const isScan = (img.filename || '').toLowerCase().includes('checklist') || (img.filename || '').toLowerCase().includes('scan')

    if (filterMode === 'estimates' && !isEstimate) return false
    if (filterMode === 'verified' && isEstimate) return false
    if (filterMode === 'scans' && !isScan) return false

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchName = (img.filename || '').toLowerCase().includes(q)
      const matchDesc = (img.vision_description || '').toLowerCase().includes(q)
      if (!matchName && !matchDesc) return false
    }

    return true
  })

  // Selected image details
  const isSelectedEstimate = Boolean(selectedImage?.description_is_estimate || selectedImage?.scored?.is_estimate)
  const groundTruth = selectedImage?.scored?.ground_truth || selectedImage?.ground_truth
  const fabricatedValues = selectedImage?.scored?.fabricated_values || []

  return (
    <div
      className="flex-1 flex flex-col h-full w-full overflow-hidden select-none"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* ── Studio Header ────────────────────────────────────────────── */}
      <header
        className="h-12 px-6 border-b flex items-center justify-between flex-shrink-0"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center border"
            style={{
              background: 'var(--color-accent-tint)',
              borderColor: 'var(--color-accent-border)',
              color: 'var(--color-accent)',
            }}
          >
            <ImageIcon size={14} strokeWidth={2.2} />
          </div>
          <div>
            <h1 className="text-xs font-bold leading-tight uppercase tracking-wider" style={{ color: 'var(--color-text)' }}>
              Vision Inspection & Trust Studio
            </h1>
            <span className="text-[10px] text-[var(--color-text-muted)] font-mono leading-none">
              Rigorous verification · Model estimates separated from ground truth
            </span>
          </div>
        </div>

        {/* Studio Trust Legend */}
        <div className="hidden md:flex items-center gap-3 text-[11px] font-mono">
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded border bg-[var(--color-warning-tint)] text-[var(--color-warning)] border-[var(--color-border)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)]" />
            ESTIMATE (Vision Reading)
          </span>
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded border bg-[var(--color-success-tint)] text-[var(--color-success)] border-[var(--color-border)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]" />
            VERIFIED (Ground Truth)
          </span>
        </div>
      </header>

      {/* ── Main Layout: Sidebar List + Inspection Stage ─────────────── */}
      <div className="flex-1 flex min-h-0 w-full overflow-hidden">
        {/* Left Thumbnails & Filters Column */}
        <div
          className="w-80 border-r flex flex-col h-full flex-shrink-0 overflow-hidden"
          style={{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-border)',
          }}
        >
          {/* Search & Mode Toggles */}
          <div className="p-3 border-b flex flex-col gap-2" style={{ borderColor: 'var(--color-border)' }}>
            <div className="relative flex items-center">
              <Search size={13} className="absolute left-2.5 text-[var(--color-text-faint)]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search images or OCR..."
                className="w-full pl-8 pr-2 py-1 text-xs rounded-lg border outline-none bg-[var(--color-input-bg)] placeholder:text-[var(--color-text-faint)]"
                style={{ borderColor: 'var(--color-input-border)', color: 'var(--color-text)' }}
              />
            </div>

            <div className="grid grid-cols-4 gap-1 text-[10.5px]">
              {[
                { id: 'all', label: 'All' },
                { id: 'estimates', label: 'Estimates' },
                { id: 'verified', label: 'Verified' },
                { id: 'scans', label: 'Scans' },
              ].map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setFilterMode(m.id)}
                  className={`py-1 rounded-md font-medium transition-fast text-center cursor-pointer ${
                    filterMode === m.id
                      ? 'bg-[var(--color-accent)] text-white shadow-xs'
                      : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Image List */}
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1.5">
            {isLoading ? (
              <div className="py-12 text-center text-xs text-[var(--color-text-muted)]">
                Loading corpus images...
              </div>
            ) : filteredImages.length === 0 ? (
              <div className="py-12 text-center text-xs text-[var(--color-text-muted)]">
                No matching inspection images found.
              </div>
            ) : (
              filteredImages.map((img) => {
                const isSelected = selectedImage?.filename === img.filename
                const isEst = Boolean(img.description_is_estimate || img.scored?.is_estimate)

                return (
                  <div
                    key={img.filename}
                    onClick={() => setSelectedImage(img)}
                    className={`p-2.5 rounded-xl border flex items-center gap-3 cursor-pointer transition-fast ${
                      isSelected
                        ? 'bg-[var(--color-overlay)] border-[var(--color-accent-border)] shadow-xs'
                        : 'border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]'
                    }`}
                  >
                    {/* Thumbnail preview */}
                    <div
                      className="w-12 h-12 rounded-lg border overflow-hidden flex items-center justify-center flex-shrink-0 bg-black/5 dark:bg-white/5"
                      style={{ borderColor: 'var(--color-border)' }}
                    >
                      {img.data_uri || img.url ? (
                        <img
                          src={api.imageSrc(img)}
                          alt={img.filename}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <ImageIcon size={18} className="text-[var(--color-text-faint)]" />
                      )}
                    </div>

                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
                        {img.filename}
                      </span>
                      <span className="text-[10px] text-[var(--color-text-muted)] font-mono">
                        {img.size_kb ? `${img.size_kb} KB` : 'Corpus asset'}
                      </span>

                      <div className="flex items-center gap-1.5 mt-1">
                        {isEst ? (
                          <span
                            className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold uppercase border"
                            style={{
                              background: 'var(--color-warning-tint)',
                              color: 'var(--color-warning)',
                              borderColor: 'var(--color-border)',
                            }}
                          >
                            ESTIMATE
                          </span>
                        ) : (
                          <span
                            className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold uppercase border"
                            style={{
                              background: 'var(--color-success-tint)',
                              color: 'var(--color-success)',
                              borderColor: 'var(--color-border)',
                            }}
                          >
                            VERIFIED
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Right Inspection & Verification Stage */}
        <div className="flex-1 flex flex-col h-full overflow-y-auto p-6 min-w-0 gap-6">
          {selectedImage ? (
            <div className="max-w-4xl w-full mx-auto flex flex-col gap-6">
              {/* Primary Visual Surface with Optional Detection Overlay */}
              <div
                className="rounded-2xl border p-4 shadow-sm flex flex-col items-center justify-center relative overflow-hidden"
                style={{
                  background: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div className="w-full flex items-center justify-between pb-3 border-b mb-3" style={{ borderColor: 'var(--color-border)' }}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold font-mono" style={{ color: 'var(--color-text)' }}>
                      {selectedImage.filename}
                    </span>
                    {isSelectedEstimate ? (
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[var(--color-warning-tint)] text-[var(--color-warning)] border border-[var(--color-border)]">
                        ⚠ MODEL ESTIMATE
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[var(--color-success-tint)] text-[var(--color-success)] border border-[var(--color-border)]">
                        ✓ VERIFIED GROUND TRUTH
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setOverlayActive((v) => !v)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer"
                    style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                  >
                    <Scan size={13} strokeWidth={2} />
                    <span>{overlayActive ? 'Hide OCR Boxes' : 'Show OCR Boxes'}</span>
                  </button>
                </div>

                {/* Image Render */}
                <div className="max-h-[460px] w-full flex items-center justify-center overflow-hidden rounded-xl border bg-black/5 dark:bg-black/20" style={{ borderColor: 'var(--color-border)' }}>
                  {overlayActive && selectedImage.ocr_regions ? (
                    <DefectOverlay
                      imageSrc={api.imageSrc(selectedImage)}
                      findings={selectedImage.ocr_regions}
                    />
                  ) : (
                    <img
                      src={api.imageSrc(selectedImage)}
                      alt={selectedImage.filename}
                      className="max-h-[440px] max-w-full object-contain"
                    />
                  )}
                </div>
              </div>

              {/* Trust & Grounding Assessment Panel */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Vision Model Output */}
                <div
                  className="p-5 rounded-2xl border flex flex-col gap-2.5 shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: isSelectedEstimate ? 'var(--color-accent-border)' : 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider font-mono" style={{ color: 'var(--color-accent)' }}>
                      VISION MODEL INTERPRETATION
                    </span>
                    <span className="text-[10px] font-mono text-[var(--color-text-muted)]">
                      qwen2.5vl:7b
                    </span>
                  </div>

                  <p className="text-xs leading-relaxed select-text" style={{ color: 'var(--color-text)' }}>
                    {selectedImage.vision_description || 'No vision reading generated for this file.'}
                  </p>

                  {isSelectedEstimate && (
                    <div
                      className="mt-2 p-3 rounded-xl border text-[11px] leading-relaxed flex items-start gap-2"
                      style={{
                        background: 'var(--color-warning-tint)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-warning)',
                      }}
                    >
                      <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />
                      <div>
                        <strong>Safety Warning:</strong> Numerical figures read from chart images are visual approximations. They must not be fed into automated control loops without engineer sign-off.
                      </div>
                    </div>
                  )}
                </div>

                {/* Ground Truth & OCR Comparison */}
                <div
                  className="p-5 rounded-2xl border flex flex-col gap-2.5 shadow-xs"
                  style={{
                    background: 'var(--color-surface)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider font-mono text-emerald-700 dark:text-emerald-400">
                      VERIFIED GROUND TRUTH
                    </span>
                    <span className="text-[10px] font-mono text-[var(--color-text-muted)]">
                      Native Data / OCR
                    </span>
                  </div>

                  {groundTruth ? (
                    <div className="flex flex-col gap-1.5 select-text text-xs">
                      {typeof groundTruth === 'object' ? (
                        <pre className="p-3 rounded-xl border font-mono text-[11px] overflow-x-auto bg-[var(--color-overlay)]" style={{ borderColor: 'var(--color-border)' }}>
                          {JSON.stringify(groundTruth, null, 2)}
                        </pre>
                      ) : (
                        <p style={{ color: 'var(--color-text)' }}>{groundTruth}</p>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-[var(--color-text-muted)] italic">
                      No external ground-truth dataset linked. Displaying raw visual evidence.
                    </p>
                  )}

                  {fabricatedValues.length > 0 && (
                    <div
                      className="mt-2 p-3 rounded-xl border text-[11px] leading-relaxed flex items-start gap-2 bg-[var(--color-error-tint)] text-[var(--color-error)]"
                      style={{ borderColor: 'var(--color-error)' }}
                    >
                      <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
                      <div>
                        <strong>Fabricated Values Detected:</strong> The vision model generated ticks as printed data ({fabricatedValues.join(', ')}). Corrected by validation pipeline.
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center text-xs text-[var(--color-text-muted)]">
              <ImageIcon size={32} strokeWidth={1.5} className="text-[var(--color-text-faint)] mb-2" />
              <span>Select an image to inspect</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
