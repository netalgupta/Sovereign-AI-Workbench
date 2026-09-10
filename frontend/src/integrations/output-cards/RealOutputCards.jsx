import React from 'react'
import { Sparkles, Download, CheckCircle2, FileText, FileSpreadsheet, Presentation } from 'lucide-react'
import { CANONICAL_OUTPUTS } from './contract'

const ICONS = {
  docx: FileText,
  xlsx: FileSpreadsheet,
  pptx: Presentation,
}

/**
 * RealOutputCards — Simulated "real" component delivered by teammate Kanishka.
 * Demonstrates zero-wiring plug-and-play integration via single-line swap in index.js.
 *
 * @param {import('./contract').OutputCardsProps} props
 */
export default function RealOutputCards({
  files = CANONICAL_OUTPUTS,
  onDownload,
  _filterType,
  _onFilterChange,
  _layout,
}) {
  return (
    <div className="flex-1 flex flex-col h-full p-6 overflow-y-auto" style={{ background: 'var(--color-bg)' }}>
      <div
        className="p-5 rounded-2xl border mb-6 flex items-center justify-between shadow-sm"
        style={{
          background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(245, 158, 11, 0.1) 100%)',
          borderColor: 'rgba(34, 197, 94, 0.3)',
        }}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-500 flex items-center justify-center">
            <CheckCircle2 size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-emerald-500 tracking-tight">
                Live Teammate Component Integrated: RealOutputCards
              </h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500 text-white">
                SWAP VERIFIED
              </span>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              Authored by Kanishka · Activated via 1-line edit in <code>output-cards/index.js</code>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 font-mono text-xs">
          <Sparkles size={14} />
          <span>Plug-and-Play Active</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-6xl">
        {files.map((file) => {
          const Icon = ICONS[file.fileType] || FileText
          return (
            <div
              key={file.id}
              className="p-5 rounded-xl border flex flex-col justify-between gap-3 shadow-xs"
              style={{
                background: 'var(--color-card-bg)',
                borderColor: 'var(--color-card-border)',
              }}
            >
              <div className="flex items-start gap-3">
                <div className="p-2.5 rounded-lg bg-amber-500/10 text-amber-500">
                  <Icon size={18} />
                </div>
                <div>
                  <h4 className="font-bold text-xs" style={{ color: 'var(--color-text)' }}>
                    {file.filename}
                  </h4>
                  <p className="text-[11px] font-mono text-zinc-400 mt-0.5">
                    {file.fileSize} · {file.citationsCount} verified citations
                  </p>
                </div>
              </div>

              <div className="pt-3 border-t flex items-center justify-between" style={{ borderColor: 'var(--color-border)' }}>
                <span className="text-[10px] font-mono text-zinc-400">{file.generatedAt}</span>
                <button
                  type="button"
                  onClick={() => onDownload && onDownload(file.id)}
                  className="px-3 py-1 rounded bg-amber-500 text-white font-medium text-xs flex items-center gap-1 hover:bg-amber-600 transition-colors"
                >
                  <Download size={12} />
                  <span>Download</span>
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
