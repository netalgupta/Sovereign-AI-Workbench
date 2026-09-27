/**
 * AgentMap — who did what in this turn, live, beside the Plan DAG.
 *
 * The DAG shows the PLAN. This shows the WORK as it happens: the turn as the
 * root agent (the model the router picked, the path, elapsed time, tokens),
 * every model call and tool call it made in order, and the background jobs
 * (decks, documents, sheets, books) running for it. Click any node for its
 * detail: arguments, output, tokens, stages.
 *
 * Everything shown is what the backend reported: tokens come from Ollama's
 * own counts (null when it did not report them -- shown as "—", never
 * estimated), times from the stream. Self-contained: it reads the chat store
 * and /api/decks, and needs nothing passed in. Mount <AgentMapButton /> where
 * the layout wants it.
 */

import { useEffect, useMemo, useState } from 'react'
import { Bot, Cpu, Wrench, Layers, X, Network } from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { buildTurnMap } from './agentMapModel'

const fmtSeconds = (s) => (s == null ? '—' : s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)
const fmtTokens = (n) => (n == null ? '—' : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))
const json = (v) => {
  try {
    const text = JSON.stringify(v, null, 2)
    return text && text.length > 6000 ? `${text.slice(0, 6000)}\n… (${text.length - 6000} more characters)` : text
  } catch {
    return String(v)
  }
}

const STATUS_COLOUR = {
  working: 'var(--color-accent)',
  running: 'var(--color-accent)',
  done: '#10b981',
  written: '#10b981',
  awaiting_approval: '#f59e0b',
  failed: '#ef4444',
  refused: '#ef4444',
  declined: '#ef4444',
}

function useTick(active) {
  const [, setNow] = useState(Date.now())
  useEffect(() => {
    if (!active) return undefined
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active])
}

function useJobs(open) {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!open) return undefined
    let alive = true
    const load = async () => {
      try {
        const res = await fetch('/api/decks')
        if (!alive) return
        if (!res.ok) {
          setError(`The backend answered ${res.status} for /api/decks.`)
          return
        }
        const data = await res.json()
        setJobs(Array.isArray(data.jobs) ? data.jobs : [])
        setError(null)
      } catch (err) {
        if (alive) setError(`Could not reach the backend (${err?.message || 'network error'}).`)
      }
    }
    load()
    const t = setInterval(load, 2000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [open])
  return { jobs, error }
}

function NodeCard({ node, selected, onSelect }) {
  const Icon = node.kind === 'root' ? Bot : node.kind === 'model' ? Cpu : node.kind === 'job' ? Layers : Wrench
  const colour = STATUS_COLOUR[node.status] || 'var(--color-text-muted)'
  return (
    <button
      type="button"
      onClick={() => onSelect(node)}
      className="w-full text-left rounded-lg border px-3 py-2 transition-fast cursor-pointer hover:border-[var(--color-accent)]"
      style={{
        background: 'var(--color-surface)',
        borderColor: selected ? 'var(--color-accent)' : 'var(--color-border)',
      }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: colour }} aria-label={node.status} />
        <Icon size={13} className="flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
        <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }} title={node.title}>
          {node.title}
        </span>
      </div>
      <div className="text-[11px] font-mono mt-0.5 truncate" style={{ color: 'var(--color-text-muted)' }}>
        {[node.subtitle, fmtSeconds(node.seconds), node.tokens != null ? `${fmtTokens(node.tokens)} tokens` : null]
          .filter(Boolean)
          .join(' · ')}
      </div>
    </button>
  )
}

function Detail({ node }) {
  if (!node) {
    return (
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        Click an agent or a step for its detail.
      </p>
    )
  }
  const d = node.detail || {}
  const rows =
    node.kind === 'model'
      ? [
          ['Model', d.model],
          ['Read (prompt tokens)', fmtTokens(d.prompt_tokens)],
          ['Wrote (output tokens)', fmtTokens(d.output_tokens)],
          ['Duration', fmtSeconds(d.seconds)],
        ]
      : node.kind === 'tool'
        ? [
            ['Tool', d.name || d.tool_name],
            ['Status', d.status],
            ['Duration', fmtSeconds(node.seconds)],
          ]
        : node.kind === 'job'
          ? [
              ['Job', d.job_id],
              ['Status', d.status],
              ['Stage', d.detail],
              ['Writer', d.writer],
              ['Elapsed', fmtSeconds(d.elapsed_seconds)],
            ]
          : [
              ['Model', d.route?.model || 'none (instant reply)'],
              ['Why this model', d.route?.model_reason],
              ['Path', d.route?.path],
              ['Why this path', d.route?.reason],
              ['Tokens', d.usage ? `${fmtTokens(d.usage.prompt_tokens)} read · ${fmtTokens(d.usage.output_tokens)} written · ${d.usage.llm_calls} call(s)` : '—'],
            ]
  const body =
    node.kind === 'tool'
      ? [
          ['Arguments', d.arguments || d.input_params],
          ['Output', d.output],
          ['Reasoning before the call', d.reasoning],
        ]
      : node.kind === 'job'
        ? [
            ['Request', d.request],
            ['Stage times', d.stage_times],
            ['Error', d.error],
          ]
        : node.kind === 'root'
          ? [
              ['Request', d.request],
              ['Plan', (d.plan || []).map((s) => `${s.step_id}: ${s.description}`)],
            ]
          : []
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-bold break-words" style={{ color: 'var(--color-text)' }}>{node.title}</h3>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[11px]">
        {rows.filter(([, v]) => v != null && v !== '').map(([k, v]) => (
          <div key={k} className="contents">
            <dt style={{ color: 'var(--color-text-muted)' }}>{k}</dt>
            <dd className="font-mono break-words" style={{ color: 'var(--color-text)' }}>{String(v)}</dd>
          </div>
        ))}
      </dl>
      {body
        .filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
        .map(([k, v]) => (
          <div key={k}>
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--color-text-muted)' }}>{k}</div>
            <pre
              className="text-[11px] font-mono rounded-md border p-2 overflow-auto max-h-64 whitespace-pre-wrap break-words"
              style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
            >
              {typeof v === 'string' ? v : json(v)}
            </pre>
          </div>
        ))}
    </div>
  )
}

/** The map itself: the modal and the Plan & Agents panel both show this. */
export function AgentMapContent({ compact = false }) {
  const messages = useChatStore((s) => s.messages)
  const { jobs, error } = useJobs(true)
  const [selected, setSelected] = useState(null)
  const map = useMemo(() => buildTurnMap(messages), [messages])
  const jobsRunning = jobs.some((j) => !['awaiting_approval', 'written', 'declined', 'refused', 'failed'].includes(j.status))
  useTick(Boolean(map?.working) || jobsRunning)
  const liveMap = buildTurnMap(messages)
  const jobNodes = jobs.slice(0, 8).map((j) => ({
    key: `job-${j.job_id}`,
    kind: 'job',
    title: j.request || j.job_id,
    subtitle: `${j.kind} · ${j.detail || j.status}`,
    status: j.status,
    seconds: j.elapsed_seconds ?? null,
    tokens: null,
    detail: j,
  }))

  return (
    <div className={`flex-1 grid min-h-0 ${compact ? 'grid-cols-1 overflow-auto' : 'md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]'}`}>
      <div className={`${compact ? 'p-3' : 'p-5'} overflow-auto flex flex-col gap-5`}>
        {!liveMap ? (
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Nothing has run in this chat yet. Ask something and the work appears here as it happens.
          </p>
        ) : (
          <div className={compact ? 'flex flex-col gap-2' : 'grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-x-6 items-start'}>
            <div className={compact ? '' : 'sticky top-0'}>
              <NodeCard node={liveMap.root} selected={selected?.key === 'root'} onSelect={setSelected} />
            </div>
            <div className={`flex flex-col gap-2 ${compact ? 'pl-3 border-l ml-2' : 'border-l pl-4'}`} style={{ borderColor: 'var(--color-border)' }}>
              {liveMap.steps.length === 0 ? (
                <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                  {liveMap.working ? 'Starting…' : 'Answered without a model call or a tool.'}
                </p>
              ) : (
                liveMap.steps.map((s) => (
                  <NodeCard key={s.key} node={s} selected={selected?.key === s.key} onSelect={setSelected} />
                ))
              )}
            </div>
          </div>
        )}

        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--color-text-muted)' }}>
            Background jobs
          </div>
          {error ? (
            <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{error}</p>
          ) : jobNodes.length === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>None this session.</p>
          ) : (
            <div className="grid sm:grid-cols-2 gap-2">
              {jobNodes.map((j) => (
                <NodeCard key={j.key} node={j} selected={selected?.key === j.key} onSelect={setSelected} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className={`${compact ? 'p-3 border-t' : 'p-5 border-t md:border-t-0 md:border-l'} overflow-auto`} style={{ borderColor: 'var(--color-border)' }}>
        <Detail node={selected && (selected.key === 'root' ? liveMap?.root : selected)} />
      </div>
    </div>
  )
}

export default function AgentMap({ onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[10100] flex items-center justify-center p-6" style={{ background: 'rgba(0,0,0,0.35)' }} onClick={onClose}>
      <div
        role="dialog"
        aria-label="Agent map"
        className="w-full max-w-5xl max-h-[85vh] rounded-2xl border shadow-xl flex flex-col overflow-hidden"
        style={{ background: 'var(--color-card-bg, var(--color-surface))', borderColor: 'var(--color-border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
          <div>
            <h2 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>Agent map</h2>
            <p className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>Every model call, tool call and background job of this chat · click one for its detail</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close agent map" className="p-1.5 rounded-md cursor-pointer hover:bg-[var(--color-surface-hover)]">
            <X size={16} style={{ color: 'var(--color-text-muted)' }} />
          </button>
        </div>
        <AgentMapContent />
      </div>
    </div>
  )
}

/** The header button that opens the map. Place it next to the Plan DAG link. */
export function AgentMapButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Agent map: every model call, tool call and background job in this turn"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] font-semibold cursor-pointer transition-fast hover:border-[var(--color-accent)]"
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
      >
        <Network size={13} />
        <span>Agent map</span>
      </button>
      {open && <AgentMap onClose={() => setOpen(false)} />}
    </>
  )
}
