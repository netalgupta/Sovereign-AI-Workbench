import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, ShieldQuestion } from 'lucide-react'

/**
 * OutputJobsList — every deliverable the workbench is writing or has written.
 *
 * A deck, report or spreadsheet takes minutes on local models, so the work
 * happens in a background job (GET /api/decks). This shows each one: its
 * stage, what it is doing, whether it is waiting for approval, and — when
 * a deck has been reviewed — its quality.
 *
 * Jobs live in the backend's memory. A restart forgets them, and the page
 * says so rather than showing a stale list.
 */

const KIND_LABEL = { deck: 'Presentation', docx: 'Word document', pdf: 'PDF', xlsx: 'Spreadsheet' }

const STATE = {
  awaiting_approval: { icon: ShieldQuestion, text: 'Waiting for your approval' },
  refused: { icon: AlertTriangle, text: 'Refused — nothing written' },
  failed: { icon: AlertTriangle, text: 'Failed' },
}

export function OutputJobsList() {
  const [jobs, setJobs] = useState([])
  const [reachable, setReachable] = useState(true)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const res = await fetch('/api/decks')
        if (!active) return
        if (!res.ok) {
          setReachable(false)
          return
        }
        const data = await res.json()
        setJobs(Array.isArray(data.jobs) ? data.jobs : [])
        setReachable(true)
      } catch {
        if (active) setReachable(false)
      }
    }
    load()
    const timer = setInterval(load, 4000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  if (!reachable || jobs.length === 0) return null

  return (
    <div className="mb-6 max-w-6xl">
      <h3 className="text-xs font-semibold uppercase tracking-wider mb-2"
          style={{ color: 'var(--color-text-muted)' }}>
        Jobs this session
      </h3>
      <div className="space-y-2">
        {jobs.map((job) => {
          const state = STATE[job.status]
          const Icon = state?.icon || Loader2
          const quality = job.quality
          return (
            <div
              key={job.job_id}
              className="rounded-lg border px-3 py-2 text-[12px]"
              style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-border)' }}
            >
              <div className="flex items-center gap-2">
                <Icon size={13} className={state ? '' : 'animate-spin'}
                      style={{ color: 'var(--color-accent)' }} />
                <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
                  {KIND_LABEL[job.kind] || job.kind}
                </span>
                <span className="truncate" style={{ color: 'var(--color-text-muted)' }}>{job.request}</span>
                <span className="ml-auto text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  {Math.round(job.elapsed_seconds || 0)}s
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2" style={{ color: 'var(--color-text-muted)' }}>
                <span>{state?.text || job.detail || job.status}</span>
                {job.writer && <span className="text-[10px]">· written by {job.writer}</span>}
              </div>
              {job.error && (
                <div className="mt-1 text-[11px]" style={{ color: 'var(--color-danger, #C8413B)' }}>
                  {job.error}
                </div>
              )}
              {quality && quality.method !== 'unavailable' && (
                <div className="mt-1.5 flex items-center gap-2">
                  {quality.score !== null && quality.score !== undefined ? (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold border"
                          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}>
                      Design {quality.score}/10 · {quality.grade}
                    </span>
                  ) : (
                    <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                      Design not reviewed
                    </span>
                  )}
                  <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                    {quality.layout_defect_pages
                      ? `${quality.layout_defect_pages} page(s) with measured defects`
                      : `Layout measured clean on ${(quality.pages || []).length} page(s)`}
                  </span>
                  {quality.reviewed_by && (
                    <CheckCircle2 size={11} style={{ color: 'var(--color-accent)' }} />
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
