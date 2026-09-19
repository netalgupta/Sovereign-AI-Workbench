import React, { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { Paperclip, UploadCloud, X, FileText, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { showToast } from '../../store/toastStore'

/**
 * Real MultimodalUpload (FRONTEND.md §3.13 / CARD 09).
 *
 * - Compact mode: paperclip button + preview tray (drag-and-drop supported),
 *   wired to the chat composer. Tray floats above the composer row.
 * - Expanded mode: full dropzone card + tray.
 *
 * Controlled vs uncontrolled:
 *   - Pass `pendingFiles` (an Array) → parent owns the queue; the component
 *     renders picker + tray from the prop and forwards picks via `onUpload`.
 *   - Omit it → the component owns its queue internally (previews generated
 *     here) and forwards picks via `onUpload`/`onRemove`.
 *   - `ref.clear()` empties the internal queue.
 *
 * File statuses per the contract drive the tray badges: queued → uploading →
 * processing → ready | error. Nothing here fabricates a result — statuses are
 * only ever set by the caller that ran the real upload/OCR step.
 *
 * @param {import('./contract').MultimodalUploadProps} props
 */
const MultimodalUpload = forwardRef(function MultimodalUpload(
  {
    onUpload,
    onRemove,
    onItemsChange,
    pendingFiles,
    acceptedTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.wav', '.mp3', '.m4a', '.ogg', '.docx', '.xlsx', '.csv', '.txt'],
    maxSizeBytes = 52428800,
    isCompact = true,
    disabled = false,
  },
  ref
) {
  const fileInputRef = useRef(null)
  const [internalItems, setInternalItems] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const previewCacheRef = useRef([])

  const controlled = Array.isArray(pendingFiles)
  const items = controlled ? pendingFiles : internalItems

  const isImage = (file) => file?.type?.startsWith('image/')

  const makePreview = (file) => {
    if (!isImage(file)) return null
    const url = URL.createObjectURL(file)
    previewCacheRef.current.push(url)
    return url
  }

  const buildItems = (files) =>
    files.map((file) => {
      const oversized = file.size > maxSizeBytes
      return {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        file,
        name: file.name,
        size: file.size,
        previewUrl: makePreview(file),
        status: oversized ? 'error' : 'queued',
        progress: 0,
      }
    })

  const handleNewFiles = (fileList) => {
    if (!fileList.length || disabled) return
    const matched = []
    for (const f of fileList) {
      const okType = acceptedTypes.some((t) =>
        f.type
          ? f.type.toLowerCase() === t.toLowerCase() ||
            f.type.toLowerCase().endsWith(t.toLowerCase().replace('.', ''))
          : f.name.toLowerCase().endsWith(t.toLowerCase())
      )
      if (okType) matched.push(f)
      else showToast(`Skipped "${f.name}" — unsupported type for this intake`, 'warning')
    }
    if (!matched.length) return
    const newItems = buildItems(matched)
    if (controlled) {
      onUpload?.(newItems)
    } else {
      setInternalItems((prev) => [...prev, ...newItems])
    }
    onItemsChange?.(newItems)
  }

  const handleRemove = (id) => {
    const target = items.find((i) => i.id === id)
    if (target?.previewUrl && !controlled) URL.revokeObjectURL(target.previewUrl)
    if (controlled) {
      onRemove?.(id)
    } else {
      setInternalItems((prev) => prev.filter((i) => i.id !== id))
    }
  }

  useImperativeHandle(ref, () => ({
    clear() {
      internalItems.forEach((i) => i.previewUrl && URL.revokeObjectURL(i.previewUrl))
      setInternalItems([])
    },
  }))

  React.useEffect(() => {
    const cache = previewCacheRef.current
    return () => {
      cache.forEach((u) => URL.revokeObjectURL(u))
    }
  }, [])

  const onPickChange = (e) => {
    handleNewFiles(Array.from(e.target.files || []))
    e.target.value = ''
  }

  const dragProps = {
    onDragOver: (e) => {
      e.preventDefault()
      setDragActive(true)
    },
    onDragLeave: () => setDragActive(false),
    onDrop: (e) => {
      e.preventDefault()
      setDragActive(false)
      handleNewFiles(Array.from(e.dataTransfer.files || []))
    },
  }

  const tray = items.length ? (
    <div className="flex items-center gap-2 overflow-x-auto">
      {items.map((item) => (
        <div
          key={item.id}
          title={`${item.name} — ${Math.round(item.size / 1024)} KB`}
          className="relative group w-14 h-14 rounded-lg border overflow-hidden flex-shrink-0 flex items-center justify-center"
          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-input-border)' }}
        >
          {item.previewUrl ? (
            <img src={item.previewUrl} alt={item.name} className="w-full h-full object-cover" />
          ) : (
            <FileText size={20} style={{ color: 'var(--color-text-muted)' }} />
          )}

          {item.status === 'error' && (
            <div className="absolute inset-0 grid place-items-center" style={{ background: 'rgba(239,68,68,0.85)' }}>
              <AlertCircle size={14} className="text-white" />
            </div>
          )}
          {item.status === 'processing' && (
            <div className="absolute inset-0 grid place-items-center bg-black/40">
              <Loader2 size={14} className="animate-spin text-white" />
            </div>
          )}
          {item.status === 'ready' && (
            <div className="absolute inset-0 grid place-items-center bg-black/30">
              <CheckCircle2 size={14} className="text-emerald-400" />
            </div>
          )}
          {(item.status === 'uploading' || item.status === 'queued') && item.progress > 0 && (
            <div className="absolute inset-x-0 bottom-0 h-0.5" style={{ background: 'var(--color-border)' }}>
              <div
                className="h-full transition-[width] duration-150"
                style={{ background: 'var(--color-accent)', width: `${item.progress}%` }}
              />
            </div>
          )}

          <button
            type="button"
            onClick={() => handleRemove(item.id)}
            className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full grid place-items-center opacity-0 group-hover:opacity-100 transition-opacity text-white"
            style={{ background: 'var(--color-text-muted)' }}
            title={`Remove ${item.name}`}
          >
            <X size={9} strokeWidth={3} />
          </button>

          <span
            className="absolute bottom-0 inset-x-0 text-[8px] font-mono px-1 py-px text-center truncate text-white"
            style={{ background: 'rgba(0,0,0,0.55)' }}
          >
            {item.name.split('.').pop()}
          </span>
        </div>
      ))}
    </div>
  ) : null

  // ── COMPACT: paperclip in the composer with an above-row preview tray ────
  if (isCompact === true) {
    return (
      <div className="relative flex items-center" {...dragProps}>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={onPickChange}
          className="hidden"
          disabled={disabled}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => fileInputRef.current?.click()}
          title="Attach PDFs, scans, inspection photos, or voice notes"
          className={`w-7 h-7 rounded-md flex items-center justify-center transition-fast ${
            disabled ? 'cursor-not-allowed opacity-40' : 'hover:bg-[var(--color-surface-hover)] cursor-pointer'
          }`}
          style={{ color: 'var(--color-text-muted)' }}
        >
          <Paperclip size={15} strokeWidth={2} />
        </button>

        {dragActive && (
          <div
            className="absolute bottom-full left-0 mb-2 z-50 px-6 py-4 rounded-xl border-2 border-dashed text-xs font-mono animate-fade-in"
            style={{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-accent)',
              color: 'var(--color-accent)',
            }}
          >
            Drop to attach
          </div>
        )}
        {items.length > 0 && (
          <div
            className="absolute bottom-full left-0 mb-2 z-50 px-2 py-2 rounded-xl border shadow-lg"
            style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-md)' }}
          >
            {tray}
          </div>
        )}
      </div>
    )
  }

  // ── EXPANDED: full dropzone card + tray ────────────────────────────────────
  return (
    <div
      className="p-4 rounded-xl border flex flex-col gap-3 text-xs"
      style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={acceptedTypes.join(',')}
        onChange={onPickChange}
        className="hidden"
        disabled={disabled}
      />
      <div
        onClick={() => !disabled && fileInputRef.current?.click()}
        {...dragProps}
        className={`p-6 border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-2 text-center transition-colors ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-amber-500'
        } ${dragActive ? 'border-amber-500' : ''}`}
        style={{ borderColor: 'var(--color-border)' }}
      >
        <UploadCloud size={24} style={{ color: 'var(--color-text-muted)' }} />
        <p className="font-medium" style={{ color: 'var(--color-text)' }}>
          Drop inspection photos, scanned P&amp;IDs, or SOP PDFs here
        </p>
        <p className="text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
          Accepts {acceptedTypes.join(', ')} up to {Math.round(maxSizeBytes / (1024 * 1024))}MB
        </p>
      </div>

      {items.length > 0 && tray}
    </div>
  )
})

export default MultimodalUpload