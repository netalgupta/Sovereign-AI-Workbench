/**
 * FileCard — a file the system wrote, shown in the chat where it was made.
 *
 * An approved deliverable used to be announced by one line of text naming
 * it; finding it meant going to the Artifacts tab. Now it sits under the
 * message as a card: click it and it opens rendered in the viewer (Word,
 * PDF, Excel and PowerPoint all render there), or download it.
 */

import { motion } from 'framer-motion'
import { Download, Eye, FileArchive, FileCode, FileSpreadsheet, FileText, Presentation } from 'lucide-react'
import { usePreviewStore } from '../../store/previewStore'

const KINDS = {
  docx: { icon: FileText, label: 'Word document', color: '#3b82f6' },
  pdf: { icon: FileText, label: 'PDF', color: '#ef4444' },
  xlsx: { icon: FileSpreadsheet, label: 'Spreadsheet', color: '#10b981' },
  csv: { icon: FileSpreadsheet, label: 'CSV', color: '#10b981' },
  pptx: { icon: Presentation, label: 'Presentation', color: '#f59e0b' },
  zip: { icon: FileArchive, label: 'Zip archive', color: '#a855f7' },
}

function kindOf(ext) {
  return KINDS[ext] || { icon: FileCode, label: (ext || 'file').toUpperCase(), color: 'var(--color-accent)' }
}

export function FileCard({ file }) {
  const openPreview = usePreviewStore((s) => s.openPreview)
  const kind = kindOf(file.ext)
  const Icon = kind.icon
  const open = () =>
    openPreview({ id: file.path, name: file.name, filename: file.name, relativePath: file.path, path: file.path })
  const download = (e) => {
    e.stopPropagation()
    const a = document.createElement('a')
    a.href = `/api/outputs/${encodeURIComponent(file.name)}/download`
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <motion.div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), open())}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -1 }}
      transition={{ duration: 0.16 }}
      className="group flex items-center gap-3 w-full max-w-md rounded-xl border px-3.5 py-3 cursor-pointer text-left focus-visible:outline focus-visible:outline-2"
      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', outlineColor: 'var(--color-accent)' }}
      title={`Open ${file.name}`}
    >
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: `color-mix(in srgb, ${kind.color} 14%, transparent)`, color: kind.color }}
      >
        <Icon size={20} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-semibold truncate select-text" style={{ color: 'var(--color-text)' }}>
          {file.name}
        </div>
        <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
          {kind.label}
          {file.size ? ` · ${file.size}` : ''} · click to open
        </div>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        <span
          className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium opacity-70 group-hover:opacity-100"
          style={{ color: 'var(--color-accent)' }}
        >
          <Eye size={12} /> Open
        </span>
        <button
          type="button"
          onClick={download}
          title="Download"
          aria-label={`Download ${file.name}`}
          className="p-1.5 rounded-md cursor-pointer hover:bg-[var(--color-overlay)]"
          style={{ color: 'var(--color-text-muted)' }}
        >
          <Download size={14} />
        </button>
      </div>
    </motion.div>
  )
}

export function FileCards({ files }) {
  if (!Array.isArray(files) || files.length === 0) return null
  return (
    <div className="flex flex-col gap-2">
      {files.map((f) => (
        <FileCard key={f.path || f.name} file={f} />
      ))}
    </div>
  )
}
