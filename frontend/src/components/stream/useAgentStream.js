/**
 * useAgentStream.js — React hook for consuming POST /api/chat/stream.
 *
 * The endpoint sends Server-Sent Events (SSE). Each event has a `type` and
 * associated data. One measured turn = ~173 events. Event types:
 *
 *   { type: 'narration',   token: string }
 *     — one text token of the agent's reasoning/response, accumulate into prose
 *
 *   { type: 'tool_call',   id: string, tool: string, arguments: object, status: 'pending'|'running' }
 *     — a tool the agent is about to run. SHOW THE ARGUMENTS — per the spec,
 *       this is a SAFETY CONTROL: the model once computed evaluate_expression("-381.95-400")
 *       for "381.95 minus 400" and the tool correctly returned -781.95. A human
 *       seeing the arguments is the only thing that catches a wrong input.
 *
 *   { type: 'tool_result', id: string, tool: string, output: any, duration_ms: number, status: 'done'|'failed' }
 *     — the result of a tool call. `id` matches the preceding tool_call.
 *
 *   { type: 'route_event', route: 'corpus'|'direct'|'agentic', reason: string }
 *     — tells you which path the router took. Explains latency difference:
 *       corpus ~8s, agentic ~40s.
 *
 *   { type: 'done' }
 *     — stream ended cleanly.
 *
 *   { type: 'error', message: string }
 *     — stream ended with an error.
 *
 * The hook returns:
 *   events    — array of all events received so far (append-only)
 *   narration — accumulated text so far (narration tokens joined)
 *   route     — { route, reason } | null
 *   status    — 'idle' | 'streaming' | 'done' | 'error'
 *   error     — error message | null
 *   start(message, sessionId) — begin a streaming turn
 *   reset()   — clear all state
 */

import { useCallback, useRef, useState } from 'react'

export function useAgentStream() {
  const [events, setEvents] = useState([])
  const [narration, setNarration] = useState('')
  const [route, setRoute] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setEvents([])
    setNarration('')
    setRoute(null)
    setStatus('idle')
    setError(null)
  }, [])

  const start = useCallback(async (message, sessionId = 'default') => {
    reset()
    setStatus('streaming')

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: ctrl.signal,
      })

      if (!res.ok) {
        throw new Error(`Stream endpoint returned HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })

        // SSE lines: "data: {...}\n\n"
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''

        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const jsonStr = line.slice(5).trim()
          if (!jsonStr) continue
          try {
            const evt = JSON.parse(jsonStr)
            if (evt.type === 'narration') {
              setNarration((prev) => prev + (evt.token ?? ''))
            } else if (evt.type === 'route_event') {
              setRoute({ route: evt.route, reason: evt.reason })
            } else if (evt.type === 'done') {
              setStatus('done')
            } else if (evt.type === 'error') {
              setError(evt.message ?? 'Stream error')
              setStatus('error')
            }
            // Always append to events array for the timeline view
            setEvents((prev) => [...prev, { ...evt, _ts: Date.now() }])
          } catch {
            // malformed JSON line — skip
          }
        }
      }

      if (status !== 'error') setStatus('done')
    } catch (err) {
      if (err?.name === 'AbortError') return
      setError(err?.message ?? 'Unknown stream error')
      setStatus('error')
    }
  }, [reset, status])

  return { events, narration, route, status, error, start, reset }
}
