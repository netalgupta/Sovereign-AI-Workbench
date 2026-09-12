import React from 'react'
import { FileText, ExternalLink, ShieldCheck } from 'lucide-react'

/**
 * Placeholder for CitationCard component.
 * Owner: Netal (FRONTEND.md §3.2)
 *
 * Rendered inline directly below the sentence, pushing content down (not overlay).
 *
 * @param {import('./contract').CitationCardProps} props
 */
export default function Placeholder({
  citationId = '1',
  sourceDocName = 'SOP-114-Rev3_Hydrocracker_Catalyst_Changeout.docx',
  pageOrSection = 'Section 4.2 — WABT Trigger & Catalyst Operating Limits',
  passage = 'The design-basis feed rate for Hydrocracker Unit 2 (HCU-2) shall not exceed 110 % of nameplate capacity. Sustained exceedance accelerates bed fouling; WABT trigger limit is 410 °C.',
  sourceUrl = '/sources',
  confidence = 0.94,
  onViewSource,
}) {
  return (
    <div
      className="my-2.5 rounded-lg border text-xs shadow-xs overflow-hidden transition-all duration-150 animate-in fade-in"
      style={{
        background: 'var(--color-surface)',
        borderColor: 'var(--color-card-border)',
        borderLeft: '3px solid var(--color-accent)',
      }}
    >
      {/* Integration Handoff Badge Header */}
      <div
        className="px-3 py-1.5 flex items-center justify-between border-b text-[11px] font-mono"
        style={{
          background: 'var(--color-overlay)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }}
      >
        <div className="flex items-center gap-1.5">
          <FileText size={13} style={{ color: 'var(--color-accent)' }} />
          <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
            Citation [{citationId}]
          </span>
          <span>·</span>
          <span>Integration pending — owned by Netal</span>
        </div>
        <div className="flex items-center gap-1 text-[10px] text-emerald-500 font-sans">
          <ShieldCheck size={12} />
          <span>{Math.round(confidence * 100)}% match</span>
        </div>
      </div>

      {/* Citation Body */}
      <div className="p-3 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-[11px]" style={{ color: 'var(--color-text)' }}>
            {sourceDocName}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            {pageOrSection}
          </span>
        </div>

        <blockquote
          className="font-serif italic text-xs leading-relaxed pl-2.5 py-1 rounded border-l-2"
          style={{
            borderColor: 'var(--color-accent)',
            background: 'var(--color-card-bg)',
            color: 'var(--color-text)',
          }}
        >
          "{passage}"
        </blockquote>

        <div className="flex items-center justify-end pt-1">
          <a
            href={sourceUrl}
            onClick={(e) => {
              if (onViewSource) {
                e.preventDefault()
                onViewSource()
              }
            }}
            className="inline-flex items-center gap-1 text-[11px] font-medium hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            <span>View in Sources panel</span>
            <ExternalLink size={11} />
          </a>
        </div>
      </div>
    </div>
  )
}
