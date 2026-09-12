import React, { useRef, useState } from 'react'
import { Paperclip, UploadCloud, X, FileText, Image as ImageIcon, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import { uploadAttachment, getAttachmentStatus } from '../../lib/api'
import { useChatStore } from '../../store/chatStore'

/**
 * MultimodalUpload component with attachment state sync.
 *
 * @param {import('./contract').MultimodalUploadProps} props
 */
export default function Placeholder({
  onUpload,
  onRemove,
  pendingFiles = [],
  acceptedTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.docx', '.xlsx', '.txt'],
  maxSizeBytes = 52428800,
  isCompact = true,
  disabled = false,
}) {
  const fileInputRef = useRef(null)
  const [category, setCategory] = useState('temporary')
  const addAttachment = useChatStore((s) => s.addAttachment)
  const sessionId = useChatStore((s) => s.sessionId)

  const handleFilesChosen = async (e) => {
    const fileList = Array.from(e.target.files || [])
    if (fileList.length === 0) return

    for (const file of fileList) {
      const res = await uploadAttachment(file, category, sessionId)
      const attId = res?.attachment_id || `att_${Date.now()}`
      addAttachment({
        attachment_id: attId,
        filename: file.name,
        type: file.type || 'application/octet-stream',
        category: category,
        status: res?.status || 'queued',
        created_at: new Date().toISOString(),
      })
    }

    if (onUpload) {
      onUpload(fileList)
    }
  }

  // ── Compact Mode ────────────────────────────────────────────────────────────
  if (isCompact) {
    return (
      <div className="relative inline-flex items-center gap-1">
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
          title="Multimodal upload: Drop PDFs, scans, or inspection photos"
          className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors disabled:opacity-40"
        >
          <Paperclip size={16} />
        </button>
      </div>
    )
  }

  // ── Full Dropzone Mode ──────────────────────────────────────────────────────
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
            Multimodal Attachment Tray
          </span>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase tracking-wider cursor-pointer"
            style={{
              background: category === 'permanent' ? 'rgba(59, 130, 246, 0.15)' : 'var(--color-overlay)',
              color: category === 'permanent' ? '#2563eb' : 'var(--color-text-muted)',
            }}
            onClick={() => setCategory((c) => (c === 'temporary' ? 'permanent' : 'temporary'))}
            title="Click to toggle category"
          >
            Category: {category}
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
              key={file.id || file.name}
              className="p-2 rounded border flex items-center justify-between font-mono text-[11px]"
              style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
            >
              <div className="flex items-center gap-2 truncate">
                <FileText size={14} style={{ color: 'var(--color-accent)' }} />
                <span className="truncate" style={{ color: 'var(--color-text)' }}>
                  {file.name}
                </span>
                <span style={{ color: 'var(--color-text-muted)' }}>
                  ({Math.round((file.size || 0) / 1024)} KB)
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
