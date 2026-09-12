import React, { useRef } from 'react'
import { Paperclip, UploadCloud, X, FileText, Image as ImageIcon } from 'lucide-react'

/**
 * Placeholder for MultimodalUpload component.
 * Owner: Sahil (FRONTEND.md §3.13)
 *
 * @param {import('./contract').MultimodalUploadProps} props
 */
export default function Placeholder({
  onUpload,
  onRemove,
  pendingFiles = [],
  acceptedTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff'],
  maxSizeBytes = 52428800,
  isCompact = true,
  disabled = false,
}) {
  const fileInputRef = useRef(null)

  const handleFilesChosen = (e) => {
    const fileList = Array.from(e.target.files || [])
    if (fileList.length > 0 && onUpload) {
      onUpload(fileList)
    }
  }

  // ── Compact Mode: Paperclip Trigger Button in Composer ──────────────────────
  if (isCompact) {
    return (
      <div className="relative inline-flex items-center">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={handleFilesChosen}
          className="hidden"
          disabled={disabled}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
          title="Multimodal upload: Drop PDFs, scans, or inspection photos (Integration pending — owned by Sahil)"
          className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors disabled:opacity-40"
        >
          <Paperclip size={16} />
        </button>
      </div>
    )
  }

  // ── Full Dropzone / Modal Mode ──────────────────────────────────────────────
  return (
    <div
      className="p-4 rounded-xl border flex flex-col gap-3 text-xs"
      style={{
        background: 'var(--color-card-bg)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <UploadCloud size={16} style={{ color: 'var(--color-accent)' }} />
          <span className="font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
            Multimodal Ingestion Tray
          </span>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider"
            style={{
              background: 'var(--color-overlay)',
              color: 'var(--color-text-muted)',
            }}
          >
            Integration pending — owned by Sahil
          </span>
        </div>
      </div>

      <div
        onClick={() => fileInputRef.current?.click()}
        className="p-6 border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors hover:border-amber-500 text-center"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={handleFilesChosen}
          className="hidden"
        />
        <ImageIcon size={24} style={{ color: 'var(--color-text-muted)' }} />
        <p className="font-medium" style={{ color: 'var(--color-text)' }}>
          Drop inspection photos, scanned P&amp;IDs, or SOP PDFs here
        </p>
        <p className="text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
          Accepts {acceptedTypes.join(', ')} up to {Math.round(maxSizeBytes / (1024 * 1024))}MB
        </p>
      </div>

      {pendingFiles.length > 0 && (
        <div className="space-y-1.5 pt-2">
          {pendingFiles.map((file) => (
            <div
              key={file.id}
              className="p-2 rounded border flex items-center justify-between font-mono text-[11px]"
              style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
            >
              <div className="flex items-center gap-2 truncate">
                <FileText size={14} style={{ color: 'var(--color-accent)' }} />
                <span className="truncate" style={{ color: 'var(--color-text)' }}>
                  {file.name}
                </span>
                <span style={{ color: 'var(--color-text-muted)' }}>
                  ({Math.round(file.size / 1024)} KB)
                </span>
              </div>
              {onRemove && (
                <button
                  type="button"
                  onClick={() => onRemove(file.id)}
                  className="p-1 hover:text-red-500"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
