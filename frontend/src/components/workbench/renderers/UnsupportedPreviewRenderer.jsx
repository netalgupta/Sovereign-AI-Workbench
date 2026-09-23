import { FileCode, Download } from 'lucide-react'

export function UnsupportedPreviewRenderer({ file, ext, onDownload }) {
  const name = file?.name || file?.filename || 'File'

  return (
    <div className="flex-1 w-full h-full flex flex-col items-center justify-center p-8 text-center bg-[var(--color-bg)]">
      <div
        className="flex flex-col items-center justify-center p-8 gap-4 max-w-md w-full rounded-2xl border shadow-lg"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="p-4 rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20">
          <FileCode size={40} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-base font-bold" style={{ color: 'var(--color-text)' }}>
            Preview Not Available
          </span>
          <p className="text-xs text-muted leading-relaxed">
            No visual preview adapter registered for <b>.{ext.toLowerCase()}</b> documents in this sovereign environment.
          </p>
        </div>

        <div className="w-full text-left p-3 rounded-lg border bg-[var(--color-bg)] text-xs font-mono space-y-1 text-muted" style={{ borderColor: 'var(--color-border)' }}>
          <div><span className="font-semibold text-[var(--color-text)]">File:</span> {name}</div>
          <div><span className="font-semibold text-[var(--color-text)]">Type:</span> .{ext.toLowerCase()}</div>
          {file?.size && <div><span className="font-semibold text-[var(--color-text)]">Size:</span> {file.size}</div>}
        </div>

        <button
          type="button"
          onClick={onDownload}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-xs text-white bg-[var(--color-accent)] hover:opacity-90 transition-opacity cursor-pointer shadow-sm mt-2"
        >
          <Download size={14} />
          Download File
        </button>
      </div>
    </div>
  )
}
