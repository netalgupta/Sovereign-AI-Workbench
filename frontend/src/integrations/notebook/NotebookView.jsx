/**
 * NotebookView — the Notebooks tab: every calculation and program of this
 * chat, as cells you can read and re-run.
 *
 * The tab was a "Coming soon" toast and a promise "scheduled for Day 8".
 * Now each cell is real work the agent did: the tool and its inputs, the
 * working it returned, and the result. A calculation cell re-runs live
 * through /api/tools/call (only ungated tools can run there, so a re-run
 * can never write a file). A program cell shows the code and its output.
 *
 * "Recorded calculations" lists every calculation in the append-only audit
 * log, across chats, with its calculation_id -- the answer to "where did
 * this number come from" after the fact (Review Rule 9).
 */

import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Calculator, Code2, Play, RotateCcw, BookOpen, Loader2, AlertTriangle } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { buildCells } from './notebookModel'
import { CopyButton } from '../../components/common/CopyButton'

const pretty = (v) => {
  if (v == null) return ''
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function Block({ label, children, tone }) {
  if (children == null || children === '') return null
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: tone || 'var(--color-text-muted)' }}>
          {label}
        </span>
        <CopyButton text={String(children)} title={`Copy ${String(label).toLowerCase()}`} size={11} />
      </div>
      <pre
        className="text-[12px] font-mono rounded-lg border p-3 overflow-auto max-h-72 whitespace-pre-wrap break-words"
        style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
      >
        {children}
      </pre>
    </div>
  )
}

function Cell({ cell, index }) {
  const [rerun, setRerun] = useState(null) // { status, output, error, seconds }
  const Icon = cell.kind === 'code' ? Code2 : Calculator

  const run = async () => {
    setRerun({ status: 'running' })
    const t0 = performance.now()
    try {
      const res = await fetch('/api/tools/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: cell.tool, arguments: cell.arguments || {} }),
      })
      const data = await res.json().catch(() => ({}))
      const seconds = (performance.now() - t0) / 1000
      if (!res.ok) {
        setRerun({ status: 'failed', error: typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`, seconds })
        return
      }
      setRerun({ status: 'done', output: data.result ?? data, seconds })
    } catch (err) {
      setRerun({ status: 'failed', error: err?.message || 'The backend could not be reached.' })
    }
  }

  const output = rerun?.status === 'done' ? rerun.output : cell.output
  const steps = output && typeof output === 'object' ? output.steps : null
  const result =
    output && typeof output === 'object'
      ? output.result_magnitude != null
        ? `${output.result_magnitude} ${output.result_unit || ''}`.trim()
        : output.result ?? output.value ?? null
      : output

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: Math.min(index * 0.03, 0.3) }}
      className="rounded-xl border p-4 flex flex-col gap-3"
      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      <header className="flex items-center gap-2">
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--color-overlay)', color: 'var(--color-text-muted)' }}>
          [{index + 1}]
        </span>
        <Icon size={14} style={{ color: 'var(--color-accent)' }} />
        <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>{cell.title}</span>
        <span className="text-[11px] font-mono ml-1" style={{ color: 'var(--color-text-muted)' }}>
          {cell.status === 'failed' ? 'failed' : cell.seconds != null ? `${Number(cell.seconds).toFixed(2)}s` : ''}
        </span>
        {cell.kind === 'calc' && (
          <button
            type="button"
            onClick={run}
            disabled={rerun?.status === 'running'}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-semibold cursor-pointer transition-fast hover:border-[var(--color-accent)] disabled:opacity-60"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-accent)', background: 'var(--color-bg)' }}
            title="Run this calculation again, live, through the same tool"
          >
            {rerun?.status === 'running' ? <Loader2 size={12} className="animate-spin" /> : rerun ? <RotateCcw size={12} /> : <Play size={12} />}
            {rerun?.status === 'running' ? 'Running' : rerun ? 'Run again' : 'Re-run'}
          </button>
        )}
      </header>

      {cell.kind === 'code' ? (
        <>
          <Block label="Request">{cell.arguments?.task}</Block>
          <Block label={`Program${output?.model ? ` · written by ${output.model}` : ''}`}>{output?.code}</Block>
          <Block label="Output" tone={output?.stderr ? 'var(--color-danger, #ef4444)' : undefined}>
            {[output?.stdout, output?.stderr].filter(Boolean).join('\n') || (cell.status === 'failed' ? pretty(output?.error) : '')}
          </Block>
        </>
      ) : (
        <>
          <Block label="In">{pretty(cell.arguments)}</Block>
          {Array.isArray(steps) && steps.length > 0 && <Block label="Working">{steps.map((s) => (typeof s === 'string' ? s : pretty(s))).join('\n')}</Block>}
          <Block label="Out" tone="var(--color-accent)">{result != null ? String(result) : pretty(output)}</Block>
        </>
      )}

      <AnimatePresence>
        {rerun?.status === 'done' && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            Re-run live just now in {rerun.seconds.toFixed(2)}s{result != null && cell.result != null && String(result) !== String(cell.result) ? ' — the result differs from the original run' : ' — same result as the original run'}.
          </motion.p>
        )}
        {rerun?.status === 'failed' && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[11px] flex items-center gap-1.5" style={{ color: 'var(--color-danger, #ef4444)' }}>
            <AlertTriangle size={12} /> {rerun.error}
          </motion.p>
        )}
      </AnimatePresence>
    </motion.article>
  )
}

function Recorded() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let alive = true
    fetch('/api/audit?limit=1000')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (!alive) return
        const calcs = (d.entries || []).filter((e) => e.event === 'calculation').reverse()
        setRows(calcs)
      })
      .catch((err) => alive && setError(err.message))
    return () => { alive = false }
  }, [])
  if (error) return <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>The audit log could not be read ({error}).</p>
  if (rows == null) return <p className="text-xs flex items-center gap-2" style={{ color: 'var(--color-text-muted)' }}><Loader2 size={12} className="animate-spin" /> Reading the audit log…</p>
  if (rows.length === 0) return <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>No calculations have been recorded yet.</p>
  return (
    <div className="flex flex-col gap-2">
      {rows.slice(0, 200).map((e, i) => (
        <div key={`${e.request_id}-${i}`} className="rounded-lg border px-3 py-2" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}>
          <div className="flex items-center gap-2 text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
            <span>{String(e.timestamp || '').replace('T', ' ').replace('+00:00', ' UTC')}</span>
            <span>·</span>
            <span title="calculation_id">{e.request_id}</span>
          </div>
          <div className="text-xs font-mono mt-0.5 break-words" style={{ color: 'var(--color-text)' }}>{e.summary}</div>
        </div>
      ))}
    </div>
  )
}

export default function NotebookView() {
  const messages = useChatStore((s) => s.messages)
  const cells = useMemo(() => buildCells(messages), [messages])
  const [view, setView] = useState('chat')

  return (
    <div className="flex-1 overflow-y-auto px-8 py-6">
      <div className="max-w-4xl mx-auto flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'var(--color-accent-tint)', color: 'var(--color-accent)' }}>
            <BookOpen size={18} />
          </div>
          <div className="flex-1">
            <h2 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>Notebook</h2>
            <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
              Every calculation and program in this chat, with its inputs, working and result. Calculations re-run live.
            </p>
          </div>
          <div className="flex p-1 rounded-lg border text-[11px] font-semibold" style={{ borderColor: 'var(--color-border)', background: 'var(--color-overlay)' }}>
            {[['chat', `This chat (${cells.length})`], ['recorded', 'Recorded calculations']].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setView(id)}
                className="px-3 py-1 rounded-md cursor-pointer transition-fast"
                style={{ background: view === id ? 'var(--color-surface)' : 'transparent', color: view === id ? 'var(--color-text)' : 'var(--color-text-muted)' }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {view === 'recorded' ? (
          <Recorded />
        ) : cells.length === 0 ? (
          <div className="rounded-xl border border-dashed p-10 text-center" style={{ borderColor: 'var(--color-border)' }}>
            <p className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>No calculations or programs in this chat yet</p>
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Ask for a conversion, a calculation or a program in Chat — e.g. “Convert 1450 m3/h to barrels per day” — and it appears here as a cell.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {cells.map((c, i) => <Cell key={c.key} cell={c} index={i} />)}
          </div>
        )}
      </div>
    </div>
  )
}
