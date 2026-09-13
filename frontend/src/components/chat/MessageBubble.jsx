/**
 * MessageBubble.jsx — Single conversation message with streaming typewriter.
 *
 * FRONTEND.md §3.1:
 *   - User messages: right-aligned, accent-tinted background
 *   - Assistant messages: left-aligned, NO bubble — text on cream surface
 *   - Streaming text reveals token-by-token (even if backend returns full chunk)
 *   - Full markdown rendering: headings, bold, code blocks, tables, citations
 *
 * Streaming reveal architecture:
 *   - message.content   = full target text (grows with each SSE chunk)
 *   - message.displayedContent = what's actually rendered (chases content)
 *   - useTypewriter hook drains the delta at ~18ms/char, works for both
 *     single-chunk mock AND real multi-chunk SSE streams
 */

import { useEffect, useRef, useState } from 'react'
import {
  Terminal,
  Search,
  Calculator,
  Wrench,
  FileText,
  ShieldCheck,
  ListTree,
  CornerDownRight,
  Brain,
  AlertTriangle,
} from 'lucide-react'
import { formatTime } from '../../lib/formatTime'
import { MarkdownBody } from './MarkdownBody'
import { useChatStore } from '../../store/chatStore'
import { getToolsMetadata } from '../../lib/api'
import { DefectOverlay } from '../../integrations/defect-overlay'

const TYPEWRITER_SPEED_MS = 18

/**
 * Typewriter inline hook — lives inside MessageBubble so it has access to
 * the exact message state without prop-drilling.
 *
 * Drains characters from message.content into message.displayedContent
 * at a constant visual speed. Safe for multi-chunk SSE (queue extends,
 * drainer continues uninterrupted).
 */
function useMessageTypewriter(message) {
  const setDisplayedContent = useChatStore((s) => s.setDisplayedContent)
  const revealedRef = useRef(message.displayedContent.length)
  const intervalRef = useRef(null)

  useEffect(() => {
    // Non-streaming or already fully revealed → skip animation
    if (!message.streaming && message.displayedContent === message.content) return
    if (message.role === 'user') return

    const target = message.content

    // Start the drain interval if not already running
    if (!intervalRef.current) {
      intervalRef.current = setInterval(() => {
        if (revealedRef.current >= target.length) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
          return
        }
        revealedRef.current += 1
        setDisplayedContent(message.id, target.slice(0, revealedRef.current))
      }, TYPEWRITER_SPEED_MS)
    }
    // If interval is already running and target grew (new SSE chunk), it will
    // naturally continue draining the newly appended characters.
  }, [message.content, message.streaming, message.displayedContent, message.id, message.role, setDisplayedContent])

  // FAILSAFE: the reveal animation must never be able to hide the answer.
  //
  // The typewriter above is a presentation nicety. It is also the only
  // thing standing between a received reply and the screen, and when it
  // stalls the result is a blank bubble stuck on "streaming..." with no
  // error anywhere -- which is exactly what shipped. The backend was
  // returning 200 OK with a correct grounded answer and the user saw
  // nothing, repeatedly, across several different attempted fixes.
  //
  // Rather than keep guessing at which interaction of batching, refs and
  // effect ordering stalls it, this makes the failure mode impossible:
  // if content exists and nothing has been revealed shortly after it
  // arrived, the whole thing is shown at once. A missing animation is a
  // cosmetic regression; a missing answer is the product not working.
  useEffect(() => {
    if (message.role === 'user') return
    if (!message.content) return
    if (message.displayedContent === message.content) return

    const failsafe = setTimeout(() => {
      // Re-read from the store rather than trusting this closure, which
      // may be describing a render from before the drain started.
      const live = useChatStore.getState().messages.find((m) => m.id === message.id)
      if (!live || !live.content) return
      if (live.displayedContent === live.content) return
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      revealedRef.current = live.content.length
      setDisplayedContent(message.id, live.content)
    }, 1200)

    return () => clearTimeout(failsafe)
  }, [message.content, message.displayedContent, message.id, message.role, setDisplayedContent])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])
}

/**
 * Clean neutral blinking cursor shown while text is being revealed.
 * Matches body text color with no accent glow.
 */
function StreamCursor() {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: '2px',
        height: '13px',
        background: 'var(--color-text)',
        borderRadius: '1px',
        verticalAlign: 'text-bottom',
        marginLeft: '2px',
        animation: 'cursor-blink 0.9s steps(2, start) infinite',
      }}
    />
  )
}

const ACTIVE_THINKING_WORDS = [
  'Mulling it over',
  'Fathoming',
  'Chewing on it',
  'Percolating',
  'Turning it over',
  'Puzzling through it',
  'Working it out',
  'Sifting through it',
  'Piecing it together',
]

const COMPLETED_THINKING_WORDS = [
  'Deliberated',
  'Traced',
  'Reckoned',
  'Reasoned',
  'Synthesised',
  'Examined',
  'Evaluated',
  'Investigated',
]

function getCompletedWord(messageId = '') {
  let hash = 0
  for (let i = 0; i < messageId.length; i++) {
    hash = (hash * 31 + messageId.charCodeAt(i)) | 0
  }
  return COMPLETED_THINKING_WORDS[Math.abs(hash) % COMPLETED_THINKING_WORDS.length]
}

function truncate(str, maxLen = 40) {
  if (!str || typeof str !== 'string') return ''
  return str.length > maxLen ? `${str.slice(0, maxLen - 1)}…` : str
}

function extractRetrievedSources(tool, citations = []) {
  const sourcesMap = new Map()

  if (tool?.output) {
    let passages = []
    if (typeof tool.output === 'object' && Array.isArray(tool.output.passages)) {
      passages = tool.output.passages
    } else if (typeof tool.output === 'string') {
      try {
        const parsed = JSON.parse(tool.output)
        if (Array.isArray(parsed?.passages)) passages = parsed.passages
      } catch {}
    }

    passages.forEach((p) => {
      const doc = p.source_document || p.doc || p.document_name
      if (doc) {
        const page = p.page_number ? `p. ${p.page_number}` : (p.section || '')
        const key = `${doc}:${page}`
        if (!sourcesMap.has(key)) {
          sourcesMap.set(key, { doc, page })
        }
      }
    })
  }

  if (sourcesMap.size === 0 && citations && citations.length > 0) {
    citations.forEach((c) => {
      const doc = c.doc || c.source_document || c.document_name || 'Document'
      const page = c.section || (c.page_number ? `p. ${c.page_number}` : '')
      const key = `${doc}:${page}`
      if (!sourcesMap.has(key)) {
        sourcesMap.set(key, { doc, page })
      }
    })
  }

  return Array.from(sourcesMap.values())
}

// Tools that compute a number and can show their working. Named
// rather than pattern-matched: a tool added to this set must actually
// return `steps`, and a guess would render an empty derivation that
// looks like the calculation had none.
const CALCULATION_TOOLS = new Set([
  'evaluate_expression',
  'evaluate_unit_expression',
])

function extractToolResult(tool) {
  if (!tool?.output) return null
  let out = tool.output
  if (typeof out === 'object') {
    if (out.result !== undefined) out = out.result
    else if (out.value !== undefined) out = out.value
    else out = JSON.stringify(out)
  }
  // A RESULT IS NOT TRUNCATED THE WAY A LABEL IS. 60 characters is the
  // right budget for a summary line and the wrong one for a number: an
  // answer ending in "..." is unusable, and a reader cannot tell a
  // truncated figure from a precise one.
  const text = String(out).replace(/\s+/g, ' ').trim()
  return text.length <= 120 ? text : truncate(text, 120)
}

/**
 * Hierarchical reasoning tree & live rotating status.
 *
 * Requirements:
 * - Assistant messages start directly with the thinking status line (no brand labels above)
 * - Zero colored badges or pills, zero explainer sentences
 * - Rotating present-participle active word every ~2.4s next to a pulsing dot while in-progress
 * - Settles into deterministic completed word (Deliberated, Traced, etc.) with duration
 * - Expands into a Claude Code-style hierarchical monospace tree with ├─ / └─ connectors
 * - Sub-actions (e.g. retrieved documents) nested one level deeper under tools
 * - Smooth container expand/collapse animation via collapsible-grid
 */
function TurnTrace({ message, isStreaming = false }) {
  const [open, setOpen] = useState(false)
  const [activeWordIndex, setActiveWordIndex] = useState(0)

  // Rotate active word every 2.4s while actively in progress
  useEffect(() => {
    if (!isStreaming) return
    const interval = setInterval(() => {
      setActiveWordIndex((prev) => (prev + 1) % ACTIVE_THINKING_WORDS.length)
    }, 2400)
    return () => clearInterval(interval)
  }, [isStreaming])

  // name -> { is_estimate, category }, fetched once from /api/tools so the
  // trace can visibly label model-estimate outputs (e.g. describe_chart_image,
  // measured at 10 fabricated values across 2/6 charts in CHART_STRESS_REPORT.md).
  const [toolMeta, setToolMeta] = useState(null)

  useEffect(() => {
    let mounted = true
    getToolsMetadata().then((meta) => mounted && setToolMeta(meta))
    return () => {
      mounted = false
    }
  }, [])

  const steps = Array.isArray(message.plan) ? message.plan : []
  const tools = Array.isArray(message.toolCallEvents) ? message.toolCallEvents : []
  const verification = message.verification || null
  const citations = Array.isArray(message.citations) ? message.citations : []
  const route = message.route || null
  const duration =
    typeof message.elapsedSeconds === 'number' && message.elapsedSeconds > 0
      ? message.elapsedSeconds
      : null

  // Nothing to render if finished and no trace data was recorded
  if (
    !isStreaming &&
    !steps.length &&
    !tools.length &&
    !verification &&
    !route &&
    !citations.length &&
    // A turn whose only trace data is what memory recalled still has
    // something to show — and it is exactly the turn where the user
    // most needs to know why the answer referred to something they did
    // not mention in it.
    !message.memory?.recalled &&
    !message.memory?.degraded &&
    !duration
  ) {
    return null
  }

  const completedWord = getCompletedWord(message.id)
  const durationText = duration ? `${duration.toFixed(1)}s` : null

  const isEstimatingTool = (name) => Boolean(toolMeta?.[name]?.is_estimate)
  const hasEstimate = tools.some((ev) => isEstimatingTool(ev.tool_name || ev.name))

  // Build Level 1 tree nodes (steps, tools, verification)
  const level1Nodes = []

  // 1. Plan steps
  if (steps.length > 0) {
    steps.forEach((st, idx) => {
      level1Nodes.push({
        id: `step-${st.step_id || idx}`,
        icon: (
          <ListTree
            size={12}
            strokeWidth={1.75}
            className="flex-shrink-0"
            style={{ color: 'var(--color-text-muted)' }}
          />
        ),
        label: `step: ${truncate(st.description || st.step_id || 'unnamed', 48)}`,
        status: st.status || 'pending',
        children: [],
      })
    })
  }

  // 1b. What memory contributed.
  //
  // Placed BEFORE the tools because it is what shaped them: a rewritten
  // follow-up changes the search that the next node runs. Counts and
  // names only -- never the remembered text itself, which contains
  // prior answers, and prior answers contain numbers. Putting those on
  // screen under a heading like "Memory" invites a reader to treat a
  // remembered figure as a current one.
  const memory = message.memory
  if (memory && (memory.recalled || memory.degraded)) {
    const memoryChildren = []

    if (memory.degraded) {
      memoryChildren.push({
        id: 'mem-degraded',
        icon: <AlertTriangle size={11} strokeWidth={1.75} className="flex-shrink-0"
                             style={{ color: 'var(--color-warning, #a8760f)' }} />,
        label: `unavailable — answered without history (${truncate(memory.degraded, 48)})`,
        status: null,
      })
    }
    if (memory.resolved_terms?.length) {
      memoryChildren.push({
        id: 'mem-resolved',
        icon: <CornerDownRight size={11} strokeWidth={1.75} className="flex-shrink-0"
                               style={{ color: 'var(--color-text-muted)' }} />,
        label: `follow-up resolved with: ${memory.resolved_terms.join(', ')}`,
        status: null,
      })
    }
    memory.focus_documents?.slice(0, 3).forEach((doc, i) => {
      memoryChildren.push({
        id: `mem-doc-${i}`,
        icon: <FileText size={11} strokeWidth={1.75} className="flex-shrink-0"
                        style={{ color: 'var(--color-text-muted)' }} />,
        label: `in focus: ${truncate(doc, 44)}`,
        status: null,
      })
    })
    if (memory.focus_entities?.length) {
      memoryChildren.push({
        id: 'mem-entities',
        icon: <CornerDownRight size={11} strokeWidth={1.75} className="flex-shrink-0"
                               style={{ color: 'var(--color-text-muted)' }} />,
        label: `entities: ${memory.focus_entities.slice(0, 4).join(', ')}`,
        status: null,
      })
    }
    if (memory.earlier_turns > 0) {
      memoryChildren.push({
        id: 'mem-digest',
        icon: <CornerDownRight size={11} strokeWidth={1.75} className="flex-shrink-0"
                               style={{ color: 'var(--color-text-muted)' }} />,
        label: `${memory.earlier_turns} earlier turn(s) condensed (questions and documents only)`,
        status: null,
      })
    }
    if (memory.durable_facts > 0) {
      memoryChildren.push({
        id: 'mem-facts',
        icon: <CornerDownRight size={11} strokeWidth={1.75} className="flex-shrink-0"
                               style={{ color: 'var(--color-text-muted)' }} />,
        label: `${memory.durable_facts} durable fact(s) applied to how the answer is written`,
        status: null,
      })
    }

    if (memoryChildren.length > 0) {
      level1Nodes.push({
        id: 'memory',
        icon: <Brain size={12} strokeWidth={1.75} className="flex-shrink-0"
                     style={{ color: 'var(--color-text-muted)' }} />,
        label: 'memory',
        status: memory.degraded ? 'failed' : 'done',
        children: memoryChildren,
      })
    }
  }

  // 2. Tool calls
  if (tools.length > 0) {
    tools.forEach((tool, idx) => {
      const toolName = tool.tool_name || tool.name || 'tool'
      const args = tool.input_params || tool.arguments
      const isRunning = tool.status === 'running'
      const isFailed = tool.status === 'failed'
      const secs = tool.seconds ? `(${tool.seconds}s)` : ''

      let icon = (
        <Wrench
          size={12}
          strokeWidth={1.75}
          className="flex-shrink-0"
          style={{ color: 'var(--color-text-muted)' }}
        />
      )
      let label = toolName
      const children = []

      if (toolName === 'search_documents') {
        icon = (
          <Search
            size={12}
            strokeWidth={1.75}
            className="flex-shrink-0"
            style={{ color: 'var(--color-text-muted)' }}
          />
        )
        const query = args?.query || ''
        label = `search_documents${query ? ` "${truncate(query, 36)}"` : ''}`

        // Level 2: Retrieved documents nested under search_documents
        const retrieved = extractRetrievedSources(tool, citations)
        retrieved.forEach((src, sIdx) => {
          children.push({
            id: `src-${sIdx}-${src.doc}`,
            icon: (
              <FileText
                size={11}
                strokeWidth={1.75}
                className="flex-shrink-0"
                style={{ color: 'var(--color-text-muted)' }}
              />
            ),
            label: `${src.doc}${src.page ? ` (${src.page})` : ''}`,
            status: null,
          })
        })
      } else if (CALCULATION_TOOLS.has(toolName)) {
        icon = (
          <Calculator
            size={12}
            strokeWidth={1.75}
            className="flex-shrink-0"
            style={{ color: 'var(--color-text-muted)' }}
          />
        )
        const expr = args?.expression || ''
        label = `${toolName}${expr ? ` "${truncate(expr, 36)}"` : ''}`

        // NFR-5: "All demoed calculations show the executed code
        // alongside the result."
        //
        // The architectural half was already satisfied -- every number
        // comes from an executed tool (hard constraint #3) -- but the
        // WORKING was discarded before it reached here, so the trace
        // could prove a tool ran and could not show what it did. That
        // is the half a reviewer needs: a tool called with the wrong
        // expression returns a genuine result for a question nobody
        // asked, and only the working reveals it. Measured once
        // already -- the model asked evaluate_expression for
        // "-381.95 - 400" when the user said "381.95 minus 400", and
        // the tool correctly returned -781.95 for what it was given.
        //
        // Steps are rendered in full and never truncated. A derivation
        // cut off at 60 characters is not a derivation.
        const workingSteps = Array.isArray(tool.output?.steps) ? tool.output.steps : []
        workingSteps.forEach((line, sIdx) => {
          children.push({
            id: `calc-step-${idx}-${sIdx}`,
            icon: (
              <CornerDownRight
                size={11}
                strokeWidth={1.75}
                className="flex-shrink-0"
                style={{ color: 'var(--color-text-muted)' }}
              />
            ),
            label: String(line),
            status: null,
          })
        })

        const resultVal = extractToolResult(tool)
        if (resultVal) {
          children.push({
            id: `eval-res-${idx}`,
            icon: (
              <CornerDownRight
                size={11}
                strokeWidth={1.75}
                className="flex-shrink-0"
                style={{ color: 'var(--color-text-muted)' }}
              />
            ),
            label: `= ${resultVal}`,
            status: null,
          })
        }
      } else {
        const firstArg =
          args && typeof args === 'object'
            ? Object.values(args)[0]
            : typeof args === 'string'
            ? args
            : ''
        if (firstArg) {
          label = `${toolName} "${truncate(String(firstArg), 32)}"`
        }
      }

      let statusStr = null
      if (isRunning) {
        statusStr = '● in progress…'
      } else if (isFailed) {
        statusStr = 'failed'
      } else {
        statusStr = `done${secs ? ` ${secs}` : ''}`
      }

      level1Nodes.push({
        id: `tool-${tool.id || idx}`,
        icon,
        label,
        status: statusStr,
        estimate: isEstimatingTool(toolName),
        children,
      })
    })
  } else if (citations.length > 0) {
    // Citations available without explicit tool calls
    const children = citations.map((c, sIdx) => {
      const doc = c.doc || c.source_document || 'Document'
      const page = c.section || (c.page_number ? `p. ${c.page_number}` : '')
      return {
        id: `fallback-src-${sIdx}`,
        icon: (
          <FileText
            size={11}
            strokeWidth={1.75}
            className="flex-shrink-0"
            style={{ color: 'var(--color-text-muted)' }}
          />
        ),
        label: `${doc}${page ? ` (${page})` : ''}`,
        status: null,
      }
    })

    level1Nodes.push({
      id: 'fallback-search',
      icon: (
        <Search
          size={12}
          strokeWidth={1.75}
          className="flex-shrink-0"
          style={{ color: 'var(--color-text-muted)' }}
        />
      ),
      label: `search_documents${message.userRequest ? ` "${truncate(message.userRequest, 36)}"` : ''}`,
      status: `done${durationText ? ` (${durationText})` : ''}`,
      children,
    })
  } else if (isStreaming) {
    // In-flight placeholder while waiting for first tool event
    level1Nodes.push({
      id: 'streaming-pending',
      icon: (
        <Search
          size={12}
          strokeWidth={1.75}
          className="flex-shrink-0"
          style={{ color: 'var(--color-text-muted)' }}
        />
      ),
      label: 'retrieving context',
      status: '● in progress…',
      children: [],
    })
  }

  // 3. Self-check / verification
  if (verification) {
    level1Nodes.push({
      id: 'verification-node',
      icon: (
        <ShieldCheck
          size={12}
          strokeWidth={1.75}
          className="flex-shrink-0"
          style={{ color: 'var(--color-text-muted)' }}
        />
      ),
      label: 'self-check',
      status: verification.passed ? 'confirmed against sources' : 'unverified',
      children: [],
    })
  }

  return (
    <div className="mt-0.5 mb-1 text-xs">
      {/* ── Top-level collapsed status button ────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 cursor-pointer select-none text-left py-0.5 font-mono"
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--color-text-muted)',
        }}
        title={open ? 'Hide reasoning tree' : 'Show reasoning tree'}
      >
        <span
          aria-hidden="true"
          className="inline-block text-[11px] leading-none transition-transform duration-150"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ›
        </span>

        {/* Status dot: continuously breathing/pulsing while in-progress, static/solid when done */}
        <span
          aria-hidden="true"
          className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={
            isStreaming
              ? {
                  background: 'var(--color-text-muted)',
                  animation: 'status-breathe 1.5s ease-in-out infinite',
                }
              : {
                  background: 'var(--color-text-muted)',
                  opacity: 0.65,
                }
          }
        />

        {isStreaming ? (
          <span>{ACTIVE_THINKING_WORDS[activeWordIndex]}…</span>
        ) : (
          <span>
            {completedWord}
            {durationText ? ` for ${durationText}` : ''}
            {verification && !verification.passed ? ' · unverified' : ''}
          </span>
        )}
      </button>

      {/* ── Hierarchical Reasoning Tree (Claude Code style) ──────────── */}
      <div className={`collapsible-grid ${open ? 'is-expanded' : ''}`}>
        <div className="collapsible-inner">
          <div className="pt-1.5 pb-1 pl-1 flex flex-col font-mono text-[11.5px] leading-relaxed">
            {/* Level 0: Turn Root */}
            <div className="flex items-center gap-1.5 py-0.5">
              <Terminal
                size={12}
                strokeWidth={1.75}
                className="flex-shrink-0"
                style={{ color: 'var(--color-text-muted)' }}
              />
              <span style={{ color: 'var(--color-text)' }}>turn</span>
              {route && (
                <span style={{ color: 'var(--color-text-faint)' }}>
                  ({route.path})
                </span>
              )}
              <span style={{ color: 'var(--color-text-muted)' }}>
                · {isStreaming ? 'in progress…' : durationText || 'completed'}
              </span>
            </div>

            {/* Level 1 & Level 2 Nodes */}
            {level1Nodes.map((node, i) => {
              const isLast1 = i === level1Nodes.length - 1
              const connector1 = isLast1 ? '└─ ' : '├─ '
              const childGuide = isLast1 ? '   ' : '│  '

              return (
                <div key={node.id || i} className="flex flex-col">
                  {/* Level 1 Node */}
                  <div className="flex items-center gap-1.5 py-0.5">
                    <span
                      className="whitespace-pre select-none flex-shrink-0"
                      style={{ color: 'var(--color-text-faint)' }}
                    >
                      {connector1}
                    </span>
                    {node.icon}
                    <span className="truncate" style={{ color: 'var(--color-text)' }}>
                      {node.label}
                    </span>
                    {node.estimate && (
                      <span
                        className="ml-1 px-1 py-px rounded text-[9px] font-bold uppercase tracking-wide"
                        style={{ background: '#f59e0b22', color: '#f59e0b' }}
                        title="This output is a vision-model estimate, not a verified measurement (CHART_STRESS_REPORT.md measured fabricated numeric readings)."
                      >
                        estimate
                      </span>
                    )}
                    {node.status && (
                      <span
                        className="flex-shrink-0"
                        style={{ color: 'var(--color-text-muted)' }}
                      >
                        · {node.status}
                      </span>
                    )}
                  </div>

                  {/* Level 2 Sub-actions (e.g. retrieved documents) */}
                  {node.children &&
                    node.children.map((child, j) => {
                      const isLast2 = j === node.children.length - 1
                      const prefix2 = childGuide + (isLast2 ? '└─ ' : '├─ ')
                      return (
                        <div
                          key={child.id || j}
                          className="flex items-center gap-1.5 py-0.5"
                        >
                          <span
                            className="whitespace-pre select-none flex-shrink-0"
                            style={{ color: 'var(--color-text-faint)' }}
                          >
                            {prefix2}
                          </span>
                          {child.icon}
                          <span
                            className="truncate"
                            style={{ color: 'var(--color-text-muted)' }}
                          >
                            {child.label}
                          </span>
                          {child.status && (
                            <span
                              className="flex-shrink-0"
                              style={{ color: 'var(--color-text-faint)' }}
                            >
                              · {child.status}
                            </span>
                          )}
                        </div>
                      )
                    })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      {hasEstimate && (
        <p
          className="mt-1 text-[10px] leading-snug"
          style={{ color: '#b45309', maxWidth: '46ch' }}
        >
          Values above marked <strong>estimate</strong> come from a vision model
          reading the image — treat them as approximate, never as a verified
          measurement.
        </p>
      )}
    </div>
  )
}


/**
 * On-demand self-check for one answer.
 *
 * Verification used to run inline on every turn. It is a second LLM
 * call on a different model, and on an 8 GB card that evicts the
 * generation model and reloads the verifier -- measured at 9s when the
 * verifier happened to be resident and 102s when it did not. Inline,
 * that turned a 70-second turn into 175 seconds for a check nobody had
 * asked for, and the same question cost wildly different amounts
 * depending on what else was loaded.
 *
 * So the answer arrives as soon as it exists, and the check runs when
 * the reader wants it -- which is the right moment anyway, because
 * whether a claim needs verifying is the reader's judgement, not the
 * system's.
 */
function VerifyButton({ message }) {
  const [state, setState] = useState('idle') // idle | running | done | error
  const [result, setResult] = useState(null)

  const request = message.userRequest || ''
  const answer = message.content || ''
  if (!answer || message.role !== 'assistant') return null

  const run = async () => {
    setState('running')
    try {
      const res = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request, answer }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setResult(data)
      setState('done')
    } catch (err) {
      setResult({ reason: String(err?.message || err) })
      setState('error')
    }
  }

  return (
    <div className="mt-1">
      {state === 'idle' && (
        <button
          type="button"
          onClick={run}
          className="text-xs cursor-pointer"
          style={{ background: 'transparent', border: 'none', color: 'var(--color-text-muted)' }}
          title="Check this answer against the cited sources"
        >
          Verify this answer
        </button>
      )}

      {state === 'running' && (
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          Checking against sources… (this loads a second model and can take a while)
        </span>
      )}

      {state === 'error' && (
        <span className="text-xs" style={{ color: 'var(--color-accent)' }}>
          {/* Could not check is NOT checked, and says so. */}
          Could not run the check: {result?.reason}
        </span>
      )}

      {state === 'done' && result && (
        <div
          className="text-xs mt-1 pl-2"
          style={{
            borderLeft: `2px solid ${result.passed ? 'var(--color-border)' : 'var(--color-accent)'}`,
            color: 'var(--color-text-muted)',
          }}
        >
          <span style={{ color: result.passed ? 'var(--color-text)' : 'var(--color-accent)' }}>
            {result.passed ? 'Confirmed against sources' : 'Not confirmed'}
          </span>
          {result.reason ? ` — ${result.reason}` : ''}
          {!result.passed && (
            <div className="mt-0.5" style={{ color: 'var(--color-text-faint)' }}>
              {/* Honest about the checker's known limits: it is a small
                  model that false-negatives on values read from tables. */}
              The checker is a small model and cannot always confirm values read
              from tables — treat this as a prompt to check the cited source, not
              as a finding that the answer is wrong.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Mounts the DefectOverlay viewer for any tool event in this turn whose real
 * output carried `detections` (+ an image). Rendered only from actual backend
 * output; absent detections render nothing here so the overlay's own empty
 * state never appears inside a conversation that has no findings.
 */
function DetectionCards({ message }) {
  const events = Array.isArray(message.toolCallEvents) ? message.toolCallEvents : []
  const withDetections = events.filter(
    (ev) =>
      ev.output &&
      Array.isArray(ev.output.detections) &&
      ev.output.detections.length > 0 &&
      (ev.output.image_url || ev.output.imageUrl)
  )
  if (!withDetections.length) return null

  const seen = new Set()
  return (
    <div className="mt-1">
      {withDetections.map((ev) => {
        const imageUrl = ev.output.image_url || ev.output.imageUrl
        if (seen.has(imageUrl)) return null
        seen.add(imageUrl)
        return (
          <DefectOverlay
            key={imageUrl}
            imageUrl={imageUrl}
            detections={ev.output.detections}
            findings={Array.isArray(ev.output.findings) ? ev.output.findings : []}
            showLabels
          />
        )
      })}
    </div>
  )
}

export function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isStreaming =
    message.streaming || message.displayedContent !== message.content

  // Start typewriter draining for this message
  useMessageTypewriter(message)

  // ── User message ────────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex justify-end px-6 animate-fade-in">
        <div className="flex flex-col items-end gap-1" style={{ maxWidth: '72%' }}>
          <div
            className="px-4 py-3 text-sm leading-relaxed"
            style={{
              background: 'var(--color-accent-tint)',
              border: '1px solid var(--color-accent-border)',
              borderRadius: 'var(--radius-lg)',
              borderBottomRightRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            {/* User messages are plain text — no markdown, no citations */}
            {message.content}
          </div>
          <span className="text-xs px-1" style={{ color: 'var(--color-text-faint)' }}>
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    )
  }

  // ── Assistant message ────────────────────────────────────────────────────
  // No bubble — just text on the cream surface (FRONTEND.md §3.1)
  // No app/assistant name label above response (starts directly with thinking-status line)
  return (
    <div className="flex flex-col gap-2 px-6 animate-fade-in" style={{ maxWidth: '84%' }}>
      {/* 1. Reasoning tree directly at top */}
      <TurnTrace message={message} isStreaming={Boolean(message.streaming)} />

      {/* 2. Markdown body with streaming typewriter reveal */}
      <div className="relative">
        <MarkdownBody
          content={
            typeof message.displayedContent === 'string' && message.displayedContent
              ? message.displayedContent
              : message.content || ''
          }
        />
        {/* Blinking cursor while draining */}
        {isStreaming && <StreamCursor />}
      </div>

      {/* Real detection overlay from tool output (rendered only when the
          backend actually returned detections for an image). */}
      {!isStreaming && <DetectionCards message={message} />}

      {!isStreaming && <VerifyButton message={message} />}

      <span className="text-xs" style={{ color: 'var(--color-text-faint)' }}>
        {formatTime(message.timestamp)}
      </span>
    </div>
  )
}
