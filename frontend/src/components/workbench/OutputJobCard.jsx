import { motion } from 'framer-motion'
import { FileSpreadsheet, FileText, Loader2, Presentation, ShieldCheck } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'

/**
 * OutputJobCard — what the background job is doing right now.
 *
 * A deck, report or spreadsheet is written, checked and only then offered
 * for approval, which takes minutes on local models. This is the window
 * into that: the stage, what it is working on, and how long it has taken.
 *
 * Every field comes from the backend's own job record (GET /api/decks/{id}).
 * Nothing here estimates progress or invents a percentage — an unknown
 * stage shows as unknown.
 */

const KIND_META = {
  deck: { icon: Presentation, label: 'Presentation' },
  docx: { icon: FileText, label: 'Word document' },
  pdf: { icon: FileText, label: 'PDF document' },
  xlsx: { icon: FileSpreadsheet, label: 'Spreadsheet' },
}

const STAGES = [
  ['queued', 'Queued'],
  ['writing', 'Writing from the sources'],
  ['artwork', 'Generating artwork'],
  ['reviewing', 'Rendering and reviewing'],
  ['awaiting_approval', 'Ready for approval'],
]

export function OutputJobCard() {
  const job = useChatStore((s) => s.activeJob)
  const openApprovalModal = useChatStore((s) => s.openApprovalModal)
  if (!job) return null

  const meta = KIND_META[job.kind] || KIND_META.deck
  const Icon = meta.icon
  const stages = job.kind === 'deck' ? STAGES : STAGES.filter(([id]) => id !== 'artwork')
  const currentIndex = stages.findIndex(([id]) => id === job.status)
  const ready = job.status === 'awaiting_approval'

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-3 mb-2 rounded-lg border px-3 py-2.5 text-[12px]"
      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      <div className="flex items-center gap-2">
        <Icon size={14} className="text-[var(--color-accent)]" />
        <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
          {meta.label}
        </span>
        <span className="text-[var(--color-text-muted)] truncate">{job.request}</span>
        <span className="ml-auto text-[10px] text-[var(--color-text-muted)]">
          {Math.round(job.elapsed_seconds || 0)}s
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {stages.map(([id, label], i) => {
          const done = currentIndex > i
          const active = currentIndex === i
          return (
            <span
              key={id}
              className="px-1.5 py-0.5 rounded text-[10px] border"
              style={{
                borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                color: done || active ? 'var(--color-text)' : 'var(--color-text-muted)',
                opacity: done || active ? 1 : 0.6,
              }}
            >
              {label}
            </span>
          )
        })}
      </div>

      {job.detail && !ready && (
        <div className="mt-2 flex items-center gap-1.5 text-[var(--color-text-muted)]">
          <Loader2 size={11} className="animate-spin" />
          <span className="truncate">{job.detail}</span>
        </div>
      )}

      {ready && (
        <div className="mt-2 flex items-center gap-2">
          <ShieldCheck size={12} className="text-[var(--color-accent)]" />
          <span style={{ color: 'var(--color-text)' }}>
            Finished and checked — nothing is written until you approve it.
          </span>
          <button
            type="button"
            onClick={openApprovalModal}
            className="ml-auto px-2 py-0.5 rounded border text-[11px] cursor-pointer hover:border-[var(--color-accent)]"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
          >
            Review
          </button>
        </div>
      )}

      {ready && Array.isArray(job.approval?.preview) && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] text-[var(--color-text-muted)]">
          {job.approval.preview.slice(0, 4).map((line, i) => (
            <li key={i} className="truncate">{line}</li>
          ))}
        </ul>
      )}
    </motion.div>
  )
}
