/**
 * AgentStreamView.jsx — Granular agent thinking UI.
 *
 * Renders the live event stream from POST /api/chat/stream, showing:
 *
 *   • Narration — the agent's reasoning text, token by token
 *   • Route badge — which path the router took (corpus/direct/agentic) and WHY
 *     (explains the latency difference: corpus ~8s vs agentic ~40s)
 *   • Tool call events — tool name + ARGUMENTS (shown before execution)
 *     and result + duration (shown after). This is a SAFETY CONTROL:
 *     the model once called evaluate_expression("-381.95 - 400") for
 *     "381.95 minus 400" and the tool correctly returned -781.95. A human
 *     seeing the arguments is the only thing that catches a wrong input.
 *   • Event timeline — every event in sequence (collapsible)
 *
 * FRONTEND.md §3.3 single-component principle: this component handles every
 * tool in TOOLS.md with one shape, driven by the event schema, never a
 * bespoke block per tool.
 */

import { useState } from 'react'
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight,
  Clock, Cpu, GitMerge, Loader2, MessageSquare, Terminal,
  Zap,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Route badge
// ---------------------------------------------------------------------------

const ROUTE_META = {
  corpus:  { label: 'Corpus retrieval', color: 'var(--color-success, #2f7a52)',   bg: '#2f7a5215' },
  direct:  { label: 'Direct answer',    color: 'var(--color-accent)',             bg: 'var(--color-accent-soft, #f5ede8)' },
  agentic: { label: 'Agentic',          color: 'var(--color-warning, #a8760f)',   bg: '#a8760f15' },
}

function RouteBadge({ route, reason }) {
  const meta = ROUTE_META[route] ?? { label: route, color: 'var(--color-text-muted)', bg: 'var(--color-bg-subtle)' }
  return (
    <div
      className="inline-flex items-start gap-2 px-3 py-2 rounded-lg text-xs mb-4"
      style={{ background: meta.bg, border: `1px solid ${meta.color}44` }}
    >
      <GitMerge size={13} style={{ color: meta.color, flexShrink: 0, marginTop: 1 }} />
      <div>
        <span className="font-semibold" style={{ color: meta.color }}>
          Route: {meta.label}
        </span>
        {reason && (
          <span style={{ color: 'var(--color-text-muted)' }}> — {reason}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tool call event block
// ---------------------------------------------------------------------------

const STATUS_ICON = {
  pending: <Loader2 size={13} className="animate-spin" style={{ color: 'var(--color-text-muted)' }} />,
  running: <Cpu     size={13} className="animate-pulse" style={{ color: 'var(--color-accent)' }} />,
  done:    <CheckCircle2 size={13} style={{ color: 'var(--color-success, #2f7a52)' }} />,
  failed:  <AlertCircle  size={13} style={{ color: 'var(--color-danger, #a63927)' }} />,
}

function ToolCallBlock({ toolCall, result }) {
  const [open, setOpen] = useState(false)
  const status = result ? result.status : (toolCall.status ?? 'pending')
  const icon = STATUS_ICON[status] ?? STATUS_ICON.pending

  // Collapsed: "🔧 tool_name — done ✓  (42ms)"
  // Expanded:  arguments + output
  return (
    <div
      className="rounded-md border my-1.5"
      style={{
        borderColor: status === 'failed' ? 'var(--color-danger, #a63927)44'
          : status === 'done' ? 'var(--color-border)'
          : 'var(--color-accent)55',
        background: 'var(--color-bg-subtle)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left"
        style={{ color: 'var(--color-text)' }}
      >
        {icon}
        <Terminal size={12} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} />
        <span className="font-mono font-semibold" style={{ color: 'var(--color-accent)' }}>
          {toolCall.tool}
        </span>
        <span className="ml-auto flex items-center gap-2" style={{ color: 'var(--color-text-muted)' }}>
          {result?.duration_ms != null && (
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {result.duration_ms}ms
            </span>
          )}
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </button>

      {open && (
        <div className="border-t px-3 pb-3 pt-2 space-y-2.5" style={{ borderColor: 'var(--color-border)' }}>
          {/* Arguments — safety-critical: show before execution */}
          <div>
            <div className="text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1.5"
                 style={{ color: 'var(--color-text-muted)' }}>
              <span
                className="px-1.5 py-0.5 rounded text-[9px] font-semibold"
                style={{ background: 'var(--color-accent-soft, #f5ede8)', color: 'var(--color-accent)' }}
              >
                ARGUMENTS
              </span>
              <span>— verify before trusting the result</span>
            </div>
            <pre
              className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words p-2 rounded overflow-x-auto"
              style={{ background: 'var(--color-bg)', color: 'var(--color-text)', maxHeight: 200 }}
            >
              {JSON.stringify(toolCall.arguments ?? {}, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {result && (
            <div>
              <div className="text-[10px] uppercase tracking-wider mb-1"
                   style={{ color: status === 'failed' ? 'var(--color-danger, #a63927)' : 'var(--color-text-muted)' }}>
                {status === 'failed' ? 'Error' : 'Output'}
              </div>
              <pre
                className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words p-2 rounded overflow-x-auto"
                style={{
                  background: 'var(--color-bg)',
                  color: status === 'failed' ? 'var(--color-danger, #a63927)' : 'var(--color-text)',
                  maxHeight: 300,
                }}
              >
                {typeof result.output === 'string'
                  ? result.output
                  : JSON.stringify(result.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Narration block
// ---------------------------------------------------------------------------

function NarrationBlock({ text }) {
  if (!text) return null
  return (
    <div
      className="flex gap-2.5 my-2"
    >
      <MessageSquare size={14} style={{ color: 'var(--color-text-muted)', flexShrink: 0, marginTop: 2 }} />
      <p
        className="text-sm leading-relaxed"
        style={{ color: 'var(--color-text)' }}
      >
        {text}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main AgentStreamView
// ---------------------------------------------------------------------------

/**
 * @param {object} props
 * @param {object[]} props.events    — from useAgentStream
 * @param {string}   props.narration — accumulated text
 * @param {object|null} props.route  — { route, reason } | null
 * @param {'idle'|'streaming'|'done'|'error'} props.status
 * @param {string|null} props.error
 */
export function AgentStreamView({ events, narration, route, status, error }) {
  const [showRaw, setShowRaw] = useState(false)

  // Build a merged timeline: pair each tool_call with its tool_result by id
  const toolCallMap = {}
  const toolResultMap = {}
  const timeline = []   // { type, data, result? }

  let pendingNarration = ''

  for (const evt of events) {
    if (evt.type === 'narration') {
      pendingNarration += evt.token ?? ''
      continue
    }
    // Flush pending narration before non-narration events
    if (pendingNarration) {
      timeline.push({ type: 'narration', text: pendingNarration })
      pendingNarration = ''
    }
    if (evt.type === 'tool_call') {
      toolCallMap[evt.id] = evt
      timeline.push({ type: 'tool_call', data: evt, id: evt.id })
    } else if (evt.type === 'tool_result') {
      toolResultMap[evt.id] = evt
      // Don't add to timeline — it will be rendered inside the tool_call block
    } else if (evt.type === 'route_event') {
      timeline.push({ type: 'route_event', data: evt })
    }
    // 'done' and 'error' are reflected in status
  }
  if (pendingNarration) {
    timeline.push({ type: 'narration', text: pendingNarration })
  }

  const toolCallCount = Object.keys(toolCallMap).length
  const doneCount = Object.values(toolResultMap).filter((r) => r.status === 'done').length

  if (status === 'idle') {
    return (
      <div className="flex-1 flex items-center justify-center py-12">
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          Send a message to see the agent work in real time.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-0 h-full">
      {/* Header strip */}
      <div
        className="flex items-center gap-3 px-4 py-2 border-b text-xs flex-wrap"
        style={{ borderColor: 'var(--color-border)' }}
      >
        {/* Status dot */}
        <span className="flex items-center gap-1.5 font-medium" style={{
          color: status === 'streaming' ? 'var(--color-accent)'
            : status === 'done' ? 'var(--color-success, #2f7a52)'
            : status === 'error' ? 'var(--color-danger, #a63927)'
            : 'var(--color-text-muted)',
        }}>
          {status === 'streaming' && <Loader2 size={11} className="animate-spin" />}
          {status === 'done' && <CheckCircle2 size={11} />}
          {status === 'error' && <AlertCircle size={11} />}
          {status === 'streaming' ? 'Agent working…'
            : status === 'done' ? 'Turn complete'
            : status === 'error' ? 'Stream error'
            : ''}
        </span>

        {toolCallCount > 0 && (
          <span style={{ color: 'var(--color-text-muted)' }}>
            {doneCount}/{toolCallCount} tools
          </span>
        )}

        <span style={{ color: 'var(--color-text-muted)' }}>
          {events.length} events
        </span>

        <button
          type="button"
          onClick={() => setShowRaw((v) => !v)}
          className="ml-auto text-[10px] px-2 py-0.5 rounded border"
          style={{
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
          }}
        >
          {showRaw ? 'Timeline' : 'Raw events'}
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 min-h-0">
        {status === 'error' && (
          <div
            className="flex gap-2 text-sm p-3 rounded-lg mb-4"
            style={{
              background: 'var(--color-bg-subtle)',
              borderLeft: '3px solid var(--color-danger, #a63927)',
              color: 'var(--color-text)',
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            {error}
          </div>
        )}

        {showRaw ? (
          // Raw event list
          <div className="space-y-1">
            {events.map((e, i) => (
              <div
                key={i}
                className="font-mono text-[11px] py-1 border-b"
                style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
              >
                <span style={{ color: 'var(--color-accent)' }}>{e.type}</span>
                {' '}
                <span style={{ color: 'var(--color-text)' }}>
                  {JSON.stringify({ ...e, _ts: undefined }, null, 0).slice(0, 120)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          // Merged timeline
          <div>
            {timeline.map((item, i) => {
              if (item.type === 'route_event') {
                return <RouteBadge key={i} route={item.data.route} reason={item.data.reason} />
              }
              if (item.type === 'narration') {
                return <NarrationBlock key={i} text={item.text} />
              }
              if (item.type === 'tool_call') {
                return (
                  <ToolCallBlock
                    key={item.id ?? i}
                    toolCall={item.data}
                    result={toolResultMap[item.id]}
                  />
                )
              }
              return null
            })}

            {/* Live narration tail (tokens still arriving) */}
            {status === 'streaming' && (
              <div className="flex items-center gap-2 mt-2">
                <Zap size={13} className="animate-pulse" style={{ color: 'var(--color-accent)' }} />
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  Receiving…
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
